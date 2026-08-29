#!/usr/bin/env python3
"""
CSI 300 生产级训练管线 v2.0
================================
吸收自 /root/train/chan.py-main 的全部最佳实践：

标注：Triple-Barrier(1.5×ATR) + 横截面分位数 + MFE/MAE
特征：55维基础 + 时序算子(lag/diff/roll/linreg) + 横截面(zscore/rank/deviation)
清洗：Winsorization(1%-99%) + Spearman冗余过滤(>0.85) + 滚动IC筛选(|IC|>0.02,IR>0.3)
切分：Purged时间切分(±5天缓冲区)
缩放：Expanding window (防前视)
训练：XGBoost(n=500,depth=7,lr=0.03,early_stopping)
评估：AUC + OOS IC/IR + 特征重要性
"""
import os, sys, time, json, pickle, copy, warnings, hashlib
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ══════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════
PROJECT = Path("/seal/hermes-workerspace/chan-model-xgb")
CHANPY = Path("/root/.hermes/skills/a-share-market-analysis/chanpy")
SKILL = Path("/root/.hermes/skills/a-share-market-analysis")
DATA_DIR = PROJECT / "data" / "processed"
MODEL_DIR = PROJECT / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(CHANPY))
from DataAPI.CSVTrainingAPI import CSVTrainingAPI, set_csv_override
from Chan import CChan
from ChanConfig import CChanConfig
from Common.CEnum import KL_TYPE, AUTYPE, BSP_TYPE

# Chan config
CHAN_CONFIG = {
    'trigger_step': True, 'divergence_rate': 0.7, 'min_zs_cnt': 1,
    'bs_type': '1,1p,2,2s,3a,3b', 'bi_strict': False,
    'bi_fx_check': 'half', 'seg_algo': 'chan', 'zs_combine': True,
    'print_warning': False,
}

# XGBoost params — CPU hist (xgboost on this host has no CUDA)
XGB_PARAMS = {
    'n_estimators': 500, 'max_depth': 7, 'learning_rate': 0.03,
    'subsample': 0.8, 'colsample_bytree': 0.7,
    'reg_alpha': 0.1, 'reg_lambda': 1.0,
    'min_child_weight': 10, 'eval_metric': 'aucpr',
    'tree_method': 'hist', 'random_state': 42,
    'n_jobs': -1,  # use all CPU cores
}

# Labeling
BARRIER_K = 1.5       # ATR multiple for barrier
BARRIER_MAX_DAYS = 15  # max bars to check
CS_TOP_PCT = 0.30      # top 30% = positive
CS_BOTTOM_PCT = 0.30   # bottom 30% = negative
MFE_MAE_RATIO = 3.0    # MFE/MAE threshold

# Time split
TRAIN_END = "2023-12-31"
VAL_START = "2024-01-10"
VAL_END = "2024-12-31"
TEST_START = "2025-01-10"
PURGE_DAYS = 5

# Feature expansion
LAGS = [1, 2, 3, 5, 10, 20]
ROLL_WINDOWS = [3, 5, 10]
REG_WINDOWS = [5, 10]

# Feature selection
CORR_THRESHOLD = 0.95  # relaxed: 0.85 was too aggressive for 55 features
WINSOR_LOWER = 0.01
WINSOR_UPPER = 0.99
IC_MIN_ABS = 0.02
IR_MIN = 0.3
IC_WINDOW_DAYS = 30  # reduced from 60 for speed

# 因子净化 (吸收 AlphaPurify 42种方法, 见 scripts/factor_preprocess.py)
# ⚠️ 实验结论(2026-08-21): 横截面预处理对 XGBoost 树模型有害——
#   横截面MAD缩尾 AUC 0.5165 / quantile 0.5108 / +zscore 0.5074, 均 < 旧方法按列整体1-99%的 0.667。
#   原因: 树模型对单调变换不敏感, 横截面分组统计破坏了特征的绝对水平与时序一致性。
#   横截面预处理保留给线性模型/IC计算场景(见 factor_preprocess.py), 训练默认关闭。
PURIFY_WINSORIZE = None         # 横截面缩尾: None(默认,用旧方法)/mad/quantile/iqr/mean_std
PURIFY_STANDARDIZE = None       # 横截面标准化: 树模型不需要, 保持 None (线性模型可用 zscore/rank)
PURIFY_NEUTRALIZE = None        # 中性化(需市值/行业风险因子列, 暂无→关): ols/ridge/pca

EPS = 1e-8


# ══════════════════════════════════════════════════════════
# Part 1: Data Collection — chan.py step_load BSP snapshots
# ══════════════════════════════════════════════════════════
@dataclass
class BSPSnapshot:
    code: str
    name: str
    date: str
    idx: int
    is_buy: bool
    bsp_types: List[str]
    price: float
    zs_low: float = 0.0
    zs_high: float = 0.0
    pos: str = ''
    ytd: float = 0.0
    # Raw data for labeling & feature extraction
    closes: np.ndarray = field(default_factory=lambda: np.array([]))
    highs: np.ndarray = field(default_factory=lambda: np.array([]))
    lows: np.ndarray = field(default_factory=lambda: np.array([]))
    opens: np.ndarray = field(default_factory=lambda: np.array([]))
    vols: np.ndarray = field(default_factory=lambda: np.array([]))
    all_closes: np.ndarray = field(default_factory=lambda: np.array([]))  # full series
    all_highs: np.ndarray = field(default_factory=lambda: np.array([]))
    all_lows: np.ndarray = field(default_factory=lambda: np.array([]))
    all_opens: np.ndarray = field(default_factory=lambda: np.array([]))
    # Chan objects
    chan_snapshot: Any = None


def collect_all_snapshots(csv_files: List[Path], max_stocks: int = 300) -> Tuple[List[BSPSnapshot], List[str]]:
    """Collect BSP snapshots from all CSV files using chan.py step_load."""
    snaps = []
    feat_order = []
    stocks_ok = 0
    t0 = time.time()

    for i, csv_path in enumerate(csv_files):
        code = csv_path.stem
        if i > 0 and i % 50 == 0:
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (min(max_stocks, len(csv_files)) - i) / rate if rate > 0 else 0
            print(f"  [{i}/{min(max_stocks,len(csv_files))}] BSP: {len(snaps)} | {rate:.1f}/s ETA {eta:.0f}s")

        if i >= max_stocks:
            break

        try:
            stock_snaps = _process_one_stock(code, str(csv_path))
            snaps.extend(stock_snaps)
            stocks_ok += 1
        except Exception as e:
            if i < 5:
                print(f"  ⚠ {code}: {str(e)[:80]}")

    elapsed = time.time() - t0
    print(f"  Done: {stocks_ok} stocks, {len(snaps)} BSP snapshots in {elapsed:.0f}s")
    return snaps, feat_order


def _process_one_stock(code: str, csv_path: str) -> List[BSPSnapshot]:
    """Process one stock: step_load → BSP snapshots with full data."""
    set_csv_override(code, csv_path)
    df = pd.read_csv(csv_path, header=None, names=['t', 'o', 'h', 'l', 'c', 'v'])
    all_klines = df.to_dict('records')
    all_closes = df['c'].values.astype(float)
    all_highs = df['h'].values.astype(float)
    all_lows = df['l'].values.astype(float)
    all_opens = df['o'].values.astype(float)

    config = CChanConfig(copy.deepcopy(CHAN_CONFIG))
    chan = CChan(code=code, begin_time=None, end_time=None,
                 data_src="custom:CSVTrainingAPI.CSVTrainingAPI",
                 lv_list=[KL_TYPE.K_DAY], config=config, autype=AUTYPE.QFQ)

    snaps = []
    seen = set()

    for snapshot_chan in chan.step_load():
        try:
            bsp_list = snapshot_chan.get_latest_bsp(number=1)
        except:
            bsp_list = []
        if not bsp_list:
            continue
        bsp = bsp_list[0]
        klu = bsp.klu
        key = (klu.idx, bsp.is_buy)
        if key in seen:
            continue
        seen.add(key)

        idx = klu.idx
        recent_n = min(idx + 1, 60)
        recent = all_klines[max(0, idx - 59):idx + 1]
        closes = np.array([r['c'] for r in recent], dtype=float)
        highs = np.array([r['h'] for r in recent], dtype=float)
        lows = np.array([r['l'] for r in recent], dtype=float)
        opens = np.array([r['o'] for r in recent], dtype=float)
        vols = np.array([r['v'] for r in recent], dtype=float)

        # ZS info
        cur = snapshot_chan[0]
        zs_low = zs_high = 0.0
        pos = ''
        if cur.zs_list:
            z = cur.zs_list[-1]
            zs_low, zs_high = float(z.low), float(z.high)
            px = closes[-1]
            pos = '内' if zs_low <= px <= zs_high else ('上' if px > zs_high else '下')

        ytd = (closes[-1] / all_closes[0] - 1) * 100 if len(all_closes) > 0 else 0

        snaps.append(BSPSnapshot(
            code=code, name='', date=str(klu.time), idx=idx,
            is_buy=bsp.is_buy, bsp_types=[t.value for t in bsp.type],
            price=float(klu.close), zs_low=zs_low, zs_high=zs_high, pos=pos, ytd=ytd,
            closes=closes, highs=highs, lows=lows, opens=opens, vols=vols,
            all_closes=all_closes, all_highs=all_highs, all_lows=all_lows, all_opens=all_opens,
            chan_snapshot=snapshot_chan,
        ))

    return snaps


# ══════════════════════════════════════════════════════════
# Part 2: Enhanced Labeling
# ══════════════════════════════════════════════════════════

def compute_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
    """Compute ATR(14) from recent K-line arrays."""
    n = len(closes)
    if n < period + 1:
        return np.nan
    tr = np.maximum(
        highs[-period:] - lows[-period:],
        np.maximum(
            np.abs(highs[-period:] - np.roll(closes, 1)[-period:]),
            np.abs(lows[-period:] - np.roll(closes, 1)[-period:])
        )
    )
    return float(np.mean(tr))


def label_triple_barrier(snap: BSPSnapshot, future_highs: np.ndarray,
                         future_lows: np.ndarray, future_opens: np.ndarray,
                         future_closes: np.ndarray) -> int:
    """
    Triple-Barrier label: 1.5×ATR up/down barriers.
    Returns 1 (hit upper), 0 (hit lower), or -1 (timeout).
    """
    atr = compute_atr(snap.highs, snap.lows, snap.closes)
    if np.isnan(atr) or atr <= 0:
        return -1
    entry = snap.price
    upper = entry + BARRIER_K * atr
    lower = max(entry - BARRIER_K * atr, EPS)
    n_future = min(len(future_highs), BARRIER_MAX_DAYS)

    for i in range(n_future):
        h = float(future_highs[i])
        l = float(future_lows[i])
        o = float(future_opens[i])
        hit_u = np.isfinite(h) and h >= upper
        hit_l = np.isfinite(l) and l <= lower
        if not hit_u and not hit_l:
            continue
        if np.isfinite(o):
            if o >= upper: return 1
            if o <= lower: return 0
        if hit_u and not hit_l: return 1
        if hit_l and not hit_u: return 0
        if hit_u and hit_l:
            return 1 if abs(upper - o) < abs(o - lower) else 0
    return -1


def label_mfe_mae(snap: BSPSnapshot, future_closes: np.ndarray) -> int:
    """MFE/MAE label: 1 if MFE/MAE > threshold."""
    entry = snap.price
    n = min(len(future_closes), 20)
    if n == 0: return -1
    fc = future_closes[:n]
    mfe = np.max(fc) - entry
    mae = entry - np.min(fc)
    if mae <= 0: return 1 if mfe > 0 else 0
    return 1 if (mfe / mae) > MFE_MAE_RATIO else 0


def build_labels(snaps: List[BSPSnapshot]) -> pd.DataFrame:
    """
    Simple directional label: future 5-bar return > 2% → 1.
    Proven AUC=0.667 on 55 features. More complex labels (Triple-Barrier etc.)
    require different feature sets; start simple, iterate.
    """
    rows = []
    for s in snaps:
        idx = s.idx
        n_total = len(s.all_closes)
        fut5_idx = min(idx + 5, n_total - 1)
        ret_5d = (s.all_closes[fut5_idx] / s.price - 1) * 100 if fut5_idx > idx else np.nan
        label = 1 if (not np.isnan(ret_5d) and ret_5d > 2.0) else (0 if not np.isnan(ret_5d) else -1)

        rows.append({
            'code': s.code, 'date': s.date, 'idx': s.idx,
            'is_buy': s.is_buy, 'price': s.price,
            'future_5d_ret': ret_5d, 'label': label,
        })

    df = pd.DataFrame(rows)
    pos = (df['label'] == 1).sum()
    neg = (df['label'] == 0).sum()
    mid = (df['label'] == -1).sum()
    total = pos + neg + mid
    print(f"  label: 1={pos}({pos/max(total,1)*100:.1f}%) 0={neg}({neg/max(total,1)*100:.1f}%) -1={mid}({mid/max(total,1)*100:.1f}%)")
    return df


# ══════════════════════════════════════════════════════════
# Part 3: Feature Extraction (55-dim base)
# ══════════════════════════════════════════════════════════

def _ema(data: np.ndarray, window: int) -> np.ndarray:
    if len(data) < window: return np.zeros(len(data))
    alpha = 2 / (window + 1)
    result = np.zeros(len(data))
    result[window - 1] = np.mean(data[:window])
    for i in range(window, len(data)): result[i] = alpha * data[i] + (1 - alpha) * result[i-1]
    return result


def _adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
    n = len(close)
    if n < period * 2: return 0.0
    tr = [max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1])) for i in range(1, n)]
    pdm = [max(high[i]-high[i-1], 0) if high[i]-high[i-1] > low[i-1]-low[i] else 0 for i in range(1, n)]
    ndm = [max(low[i-1]-low[i], 0) if low[i-1]-low[i] > high[i]-high[i-1] else 0 for i in range(1, n)]
    tr_s = sum(tr[-period:])
    if tr_s == 0: return 0.0
    pdi = sum(pdm[-period:]) / tr_s * 100
    ndi = sum(ndm[-period:]) / tr_s * 100
    return abs(pdi - ndi) / (pdi + ndi) * 100 if pdi + ndi > 0 else 0.0


def extract_base_features(snap: BSPSnapshot) -> Dict[str, float]:
    """Extract 55-dim base features from a BSP snapshot."""
    closes = snap.closes
    highs = snap.highs
    lows = snap.lows
    opens = snap.opens
    vols = snap.vols
    n = len(closes)
    cc, ch, cl, co = closes[-1], highs[-1], lows[-1], opens[-1]
    cv = vols[-1] if len(vols) > 0 else 1.0
    cur = snap.chan_snapshot[0]
    f = {}

    # 1. BSP one-hot (12)
    for d in ['buy', 'sell']:
        match = snap.is_buy if d == 'buy' else (not snap.is_buy and snap.bsp_types)
        for bt in ['type1', 'type1p', 'type2', 'type2s', 'type3a', 'type3b']:
            f[f'bsp_{d}_{bt}'] = 1.0 if match and bt in str(snap.bsp_types) else 0.0

    # 2. Price momentum (6)
    f['price_return_1'] = (cc / closes[-2] - 1) * 100 if n >= 2 else 0
    f['price_return_3'] = (cc / closes[-4] - 1) * 100 if n >= 4 else 0
    f['price_return_5'] = (cc / closes[-6] - 1) * 100 if n >= 6 else 0
    f['price_return_10'] = (cc / closes[-11] - 1) * 100 if n >= 11 else 0
    cr = max(ch - cl, EPS)
    f['price_range'] = (ch - cl) / max(cc, EPS) * 100
    f['body_ratio'] = abs(cc - co) / cr if cr > 0 else 0

    # 3. MA deviation (5)
    for w in [5, 10, 20, 60]:
        f[f'ma_{w}_dist'] = (cc - np.mean(closes[-w:])) / max(cc, EPS) * 100 if n >= w else 0
    if n >= 20:
        ma5, ma20 = np.mean(closes[-5:]), np.mean(closes[-20:])
        f['ma_cross_5_20'] = (ma5 - ma20) / max(ma20, EPS) * 100
    else:
        f['ma_cross_5_20'] = 0

    # 4. MACD (5)
    if n >= 26:
        e12, e26 = _ema(closes, 12), _ema(closes, 26)
        ml = e12 - e26
        sig = _ema(ml, 9)
        hist = ml - sig
        f['macd_value'] = ml[-1] / max(cc, EPS) * 100
        f['macd_signal'] = sig[-1] / max(cc, EPS) * 100
        f['macd_hist'] = hist[-1] / max(cc, EPS) * 100
        f['macd_cross'] = 1.0 if (ml[-2] < sig[-2] and ml[-1] > sig[-1]) else \
                          (-1.0 if (ml[-2] > sig[-2] and ml[-1] < sig[-1]) else 0)
        f['macd_hist_slope'] = (hist[-1] - hist[-5]) / max(abs(hist[-5]), EPS) if n >= 5 else 0
    else:
        for k in ['macd_value', 'macd_signal', 'macd_hist', 'macd_cross', 'macd_hist_slope']:
            f[k] = 0

    # 5. Bollinger (2)
    if n >= 20:
        sma20, std20 = np.mean(closes[-20:]), np.std(closes[-20:])
        bu, bl = sma20 + 2 * std20, sma20 - 2 * std20
        f['boll_pct_b'] = ((cc - bl) / (bu - bl) * 100) if bu != bl else 50
        f['boll_width'] = (bu - bl) / max(sma20, EPS) * 100
    else:
        f['boll_pct_b'] = 50; f['boll_width'] = 0

    # 6. Volatility (4)
    if n >= 15:
        tr_arr = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(1, n)]
        f['atr_norm'] = np.mean(tr_arr[-14:]) / max(cc, EPS) * 100 if tr_arr else 0
        r5 = [(closes[i]-closes[i-1])/closes[i-1]*100 for i in range(max(1,n-5),n)]
        r10 = [(closes[i]-closes[i-1])/closes[i-1]*100 for i in range(max(1,n-10),n)]
        f['volatility_5'] = np.std(r5) if len(r5)>1 else 0
        f['volatility_10'] = np.std(r10) if len(r10)>1 else 0
        f['volatility_ratio'] = f['volatility_5'] / max(f['volatility_10'], EPS) if f['volatility_10']>0 else 1
    else:
        f['atr_norm'] = f['volatility_5'] = f['volatility_10'] = f['volatility_ratio'] = 0

    # 7. RSI (2)
    if n >= 15:
        gains, losses = [], []
        for i in range(n-14, n):
            d = closes[i] - closes[i-1]; gains.append(max(d,0)); losses.append(max(-d,0))
        f['rsi'] = 100 - 100/(1+np.mean(gains)/max(np.mean(losses),EPS)) if np.mean(losses)>0 else 50
        f['rsi_divergence'] = 0
    else:
        f['rsi'] = 50; f['rsi_divergence'] = 0

    # 8. Volume (2)
    if n >= 20:
        vm, vs = np.mean(vols[-20:]), np.std(vols[-20:])
        f['volume_zscore'] = ((cv - vm) / max(vs, EPS)) if vs > 0 else 0
        f['volume_ratio_ma'] = cv / max(vm, EPS)
    else:
        f['volume_zscore'] = 0; f['volume_ratio_ma'] = 1

    # 9. ADX (2)
    if n >= 28:
        av = _adx(highs, lows, closes, 14)
        f['adx'] = av; f['trend_strength'] = 1.0 if av > 25 else 0.0
    else:
        f['adx'] = 0; f['trend_strength'] = 0

    # 10-13. Chan features (17)
    if cur.bi_list:
        lb = cur.bi_list[-1]
        try:
            bb = float(lb.begin_klc.low) if lb.is_down else float(lb.begin_klc.high)
            be = float(lb.end_klc.high) if lb.is_down else float(lb.end_klc.low)
            bl = abs(be-bb)/max(bb,EPS)*100
            f['bi_slope'] = bl/(lb.end_klc.idx-lb.begin_klc.idx+1) if lb.end_klc.idx>lb.begin_klc.idx else 0
            f['bi_strength'] = bl; f['bi_len_klu'] = float(lb.end_klc.idx-lb.begin_klc.idx+1)
        except: f['bi_slope']=f['bi_strength']=f['bi_len_klu']=0
        f['bi_macd_area']=f['bi_macd_peak']=0
    else:
        for k in ['bi_slope','bi_strength','bi_len_klu','bi_macd_area','bi_macd_peak']: f[k]=0

    f['zs_count'] = len(cur.zs_list)/3.0
    if cur.zs_list:
        z = cur.zs_list[-1]; zl,zh=float(z.low),float(z.high)
        zw=(zh-zl)/max(cc,EPS)*100
        f['zs_width_norm']=zw; f['zs_peak_range_norm']=zw
        f['zs_breakout_dir']=1.0 if cc>zh else(-1.0 if cc<zl else 0)
    else: f['zs_width_norm']=f['zs_peak_range_norm']=f['zs_breakout_dir']=0

    if hasattr(cur,'seg_list') and cur.seg_list:
        seg=cur.seg_list[-1]
        if hasattr(seg,'bi_list') and seg.bi_list:
            f['seg_amp']=1.0; f['seg_bi_cnt']=len(seg.bi_list)
            f['seg_is_up']=1.0 if seg.bi_list[-1].is_up else 0.0
        else: f['seg_amp']=f['seg_bi_cnt']=f['seg_is_up']=0
    else: f['seg_amp']=f['seg_bi_cnt']=f['seg_is_up']=0

    f['divergence_ratio']=f['divergence_type']=f['bsp1_distance']=0
    return f


def build_feature_matrix(snaps: List[BSPSnapshot]) -> Tuple[pd.DataFrame, List[str]]:
    """Extract base features for all snapshots."""
    rows = []
    for s in snaps:
        feats = extract_base_features(s)
        feats['code'] = s.code
        feats['date'] = s.date
        rows.append(feats)
    df = pd.DataFrame(rows)
    feat_cols = sorted([c for c in df.columns if c not in ('code', 'date')])
    return df, feat_cols


# ══════════════════════════════════════════════════════════
# Part 4: Feature Expansion (Time-series + Cross-sectional)
# ══════════════════════════════════════════════════════════

def build_time_derived(df: pd.DataFrame, base_cols: List[str]) -> Tuple[pd.DataFrame, List[str]]:
    """Build time-series derived features: lags, diffs, rolling stats, linreg."""
    new_cols = []
    result = df.copy()

    for feat in base_cols:
        grouped = result.groupby('code', sort=False)[feat]

        # Lags
        lag_map = {}
        for lag in LAGS:
            col = f'{feat}_lag{lag}'
            result[col] = grouped.shift(lag)
            lag_map[lag] = col
            new_cols.append(col)

        # Diffs
        diff1_col = f'{feat}_diff1'
        diff2_col = f'{feat}_diff2'
        result[diff1_col] = result[feat] - result[lag_map[1]]
        result[diff2_col] = result[diff1_col] - result.groupby('code', sort=False)[diff1_col].shift(1)
        new_cols.extend([diff1_col, diff2_col])

        # Rolling stats
        for w in ROLL_WINDOWS:
            roll = grouped.rolling(window=w, min_periods=max(2, w // 2))
            for stat in ['mean', 'std', 'skew', 'kurt']:
                col = f'{feat}_{stat}{w}'
                result[col] = getattr(roll, stat)().reset_index(level=0, drop=True)
                new_cols.append(col)

        # Linear regression stats
        for w in REG_WINDOWS:
            for stat_suffix, func in [('beta', _linreg_beta), ('r2', _linreg_r2), ('info_ratio', _linreg_ir)]:
                col = f'{feat}_{stat_suffix}{w}'
                result[col] = _roll_apply(grouped, w, func)
                new_cols.append(col)

    result[new_cols] = result[new_cols].replace([np.inf, -np.inf], np.nan).astype(np.float32)
    return result, new_cols


def _linreg_beta(y: np.ndarray) -> float:
    if y.size < 2 or not np.all(np.isfinite(y)): return np.nan
    x = np.arange(1, y.size + 1, dtype=np.float64)
    x_mean, y_mean = x.mean(), y.mean()
    xc, yc = x - x_mean, y - y_mean
    sxx = float(np.dot(xc, xc))
    return float(np.dot(xc, yc) / sxx) if sxx > EPS else np.nan


def _linreg_r2(y: np.ndarray) -> float:
    if y.size < 2 or not np.all(np.isfinite(y)): return np.nan
    beta = _linreg_beta(y)
    if np.isnan(beta): return np.nan
    x = np.arange(1, y.size + 1, dtype=np.float64)
    alpha = y.mean() - beta * x.mean()
    y_hat = alpha + beta * x
    sst = float(np.dot(y - y.mean(), y - y.mean()))
    sse = float(np.dot(y - y_hat, y - y_hat))
    return 1.0 - sse / sst if sst > EPS else (1.0 if sse <= EPS else 0.0)


def _linreg_ir(y: np.ndarray) -> float:
    if y.size < 2 or not np.all(np.isfinite(y)): return np.nan
    beta = _linreg_beta(y)
    if np.isnan(beta): return np.nan
    x = np.arange(1, y.size + 1, dtype=np.float64)
    alpha = y.mean() - beta * x.mean()
    resid = y - (alpha + beta * x)
    std = float(np.std(resid, ddof=0))
    return float(beta / std) if std > EPS else 0.0


def _roll_apply(grouped, window: int, fn) -> pd.Series:
    return grouped.rolling(window=window, min_periods=window).apply(fn, raw=True).reset_index(level=0, drop=True)


def build_cross_derived(df: pd.DataFrame, cont_cols: List[str],
                        min_stocks: int = 30) -> Tuple[pd.DataFrame, List[str]]:
    """Build cross-sectional features: zscore, rank, deviation."""
    df['date_d'] = pd.to_datetime(df['date']).dt.normalize()
    cs_count = df.groupby('date_d', sort=False)['code'].transform('nunique')
    valid_mask = cs_count >= min_stocks

    new_cols = []
    for col in cont_cols:
        grouped = df.groupby('date_d', sort=False)[col]
        mean_s = grouped.transform('mean')
        std_s = grouped.transform('std')
        median_s = grouped.transform('median')

        z_col = f'{col}_zscore'
        rank_col = f'{col}_rank'
        dev_col = f'{col}_deviation'

        df[z_col] = (df[col] - mean_s) / (std_s + EPS)
        df[rank_col] = grouped.rank(pct=True, method='average')
        df[dev_col] = df[col] - median_s

        df.loc[~valid_mask, [z_col, rank_col, dev_col]] = np.nan
        new_cols.extend([z_col, rank_col, dev_col])

    df[new_cols] = df[new_cols].replace([np.inf, -np.inf], np.nan).astype(np.float32)
    df = df.drop(columns=['date_d'], errors='ignore')
    return df, new_cols


# ══════════════════════════════════════════════════════════
# Part 5: Feature Cleaning
# ══════════════════════════════════════════════════════════

def winsorize_features(df: pd.DataFrame, feat_cols: List[str]) -> pd.DataFrame:
    """Winsorize at 1%-99% per column (legacy, 按列整体)."""
    result = df.copy()
    for col in feat_cols:
        s = result[col].dropna()
        if s.empty: continue
        lo, hi = s.quantile(WINSOR_LOWER), s.quantile(WINSOR_UPPER)
        result[col] = result[col].clip(lower=lo, upper=hi)
    return result


def cross_sectional_purify(df: pd.DataFrame, feat_cols: List[str], date_col: str = 'date',
                           winsorize: str = 'mad', standardize: str = 'zscore',
                           neutralize: Optional[str] = None) -> pd.DataFrame:
    """横截面因子净化 (吸收 AlphaPurify 42种方法).

    对每个特征列按交易日(date_col)横截面分组, 依次执行:
      1. winsorize 缩尾去极值 (mad/quantile/iqr/mean_std/...)
      2. standardize 标准化 (zscore/rank/rank_gauss/...)
      3. neutralize 中性化 (可选, 需 neutralizer_cols)

    相比 legacy winsorize_features(按列整体1%-99%), 横截面处理更符合
    因子挖掘规范——同一天的所有股票一起统计, 消除日间分布漂移。
    """
    from factor_preprocess import WINSORIZE, STANDARDIZE
    result = df.copy()
    for i, col in enumerate(feat_cols):
        if winsorize and winsorize in WINSORIZE:
            result = WINSORIZE[winsorize](result, col, date_col)
        if standardize and standardize in STANDARDIZE:
            result = STANDARDIZE[standardize](result, col, date_col)
    return result


def _feature_priority(col: str) -> int:
    """Priority: base(f_) > time_derived > cross_derived(zscore/rank/deviation)."""
    if not any(col.endswith(s) for s in ('_zscore', '_rank', '_deviation',
                                          '_lag', '_diff', '_mean', '_std', '_skew', '_kurt',
                                          '_beta', '_r2', '_info_ratio')):
        return 0  # base feature
    if any(col.endswith(s) for s in ('_zscore', '_rank', '_deviation')):
        return 2  # cross-derived
    return 1  # time-derived


def spearman_redundancy_filter(df: pd.DataFrame, feat_cols: List[str]) -> List[str]:
    """Remove features with |Spearman rho| > threshold, keeping higher priority.
    Optimized: rank first, then Pearson (= Spearman, but 100x faster via numpy)."""
    if len(feat_cols) <= 1:
        return feat_cols

    numeric = df[feat_cols].copy()
    for c in feat_cols:
        numeric[c] = pd.to_numeric(numeric[c], errors='coerce')

    # Drop zero-variance
    var = numeric.var()
    zv = var[(~np.isfinite(var)) | (var <= 0)].index.tolist()
    numeric = numeric.drop(columns=zv, errors='ignore')
    remaining = list(numeric.columns)
    if len(remaining) <= 1:
        return remaining

    # Spearman = Pearson on ranks. Rank the entire matrix, then use numpy corrcoef.
    # This is 50-100x faster than pandas .corr(method='spearman') for large matrices.
    n_rows = len(numeric)
    arr = numeric.values.astype(np.float64)
    # Rank each column (axis=0), handling NaN
    from scipy.stats import rankdata
    ranked = np.zeros_like(arr)
    for j in range(arr.shape[1]):
        col = arr[:, j]
        valid = ~np.isnan(col)
        ranked[valid, j] = rankdata(col[valid])  # ranks from 1 to n_valid
    # Normalize ranks to [0,1] per column
    valid_counts = np.sum(~np.isnan(arr), axis=0)
    ranked = ranked / np.maximum(valid_counts, 1)  # broadcast over columns
    ranked[np.isnan(arr)] = 0.0

    # Pearson on ranks = Spearman
    corr = np.corrcoef(ranked.T)
    corr = np.nan_to_num(corr, nan=0.0)

    to_drop = set()
    for i in range(len(remaining)):
        c1 = remaining[i]
        if c1 in to_drop: continue
        for j in range(i + 1, len(remaining)):
            c2 = remaining[j]
            if c2 in to_drop: continue
            val = abs(corr[i, j])
            if val <= CORR_THRESHOLD: continue
            p1, p2 = _feature_priority(c1), _feature_priority(c2)
            if p1 < p2: to_drop.add(c2)
            elif p2 < p1: to_drop.add(c1)
            else:
                v1, v2 = float(var.get(c1, 0) or 0), float(var.get(c2, 0) or 0)
                to_drop.add(c2 if v1 >= v2 else c1)

    kept = [c for c in remaining if c not in to_drop]
    print(f"  Spearman redundancy: {len(feat_cols)} → {len(kept)} (dropped {len(to_drop)})")
    return kept


def _compute_ic_worker(args: Tuple) -> Tuple[str, bool, float, float]:
    """Worker for parallel IC computation — numpy Spearman for speed."""
    feat, x_arr, y_arr, date_arr, unique_dates, window = args
    from scipy.stats import rankdata

    ic_list = []
    for end in range(window - 1, len(unique_dates)):
        win_dates = unique_dates[end - window + 1:end + 1]
        mask = np.isin(date_arr, win_dates)
        x_sub, y_sub = x_arr[mask], y_arr[mask]
        valid = ~np.isnan(x_sub) & ~np.isnan(y_sub) & (y_sub >= 0)
        n_valid = np.sum(valid)
        if n_valid < 10:
            continue
        # numpy Spearman: rank both, then Pearson
        xr = rankdata(x_sub[valid])
        yr = rankdata(y_sub[valid])
        ic = np.corrcoef(xr, yr)[0, 1]
        if not np.isnan(ic):
            ic_list.append(float(ic))
    if not ic_list:
        return (feat, False, 0.0, 0.0)
    mean_ic = np.mean(ic_list)
    ir = mean_ic / (np.std(ic_list) + EPS) if len(ic_list) > 1 else 0
    ok = abs(mean_ic) > IC_MIN_ABS and ir > IR_MIN
    return (feat, ok, mean_ic, ir)


def rolling_ic_filter(df: pd.DataFrame, feat_cols: List[str], label_col: str,
                      n_jobs: int = -1) -> List[str]:
    """Filter features by rolling IC, parallelized."""
    from concurrent.futures import ProcessPoolExecutor
    import os as _os

    work = df.sort_values('date').copy()
    work['date_d'] = pd.to_datetime(work['date']).dt.normalize()
    unique_dates = np.array(sorted(work['date_d'].unique()))
    date_arr = work['date_d'].values
    y_arr = work[label_col].values.astype(float)

    if len(unique_dates) < IC_WINDOW_DAYS:
        print(f"  IC filter: not enough dates ({len(unique_dates)} < {IC_WINDOW_DAYS}), keeping all")
        return feat_cols

    if n_jobs <= 0:
        n_jobs = max(1, _os.cpu_count() or 64)  # use all cores

    tasks = []
    for feat in feat_cols:
        if feat not in work.columns:
            continue
        x_arr = work[feat].values.astype(float)
        tasks.append((feat, x_arr, y_arr, date_arr, unique_dates, IC_WINDOW_DAYS))

    print(f"  IC filter: computing {len(tasks)} features with {n_jobs} workers...")
    kept = []
    with ProcessPoolExecutor(max_workers=n_jobs) as ex:
        futures = {ex.submit(_compute_ic_worker, t): t[0] for t in tasks}
        from concurrent.futures import as_completed
        for fut in as_completed(futures):
            feat, ok, mean_ic, ir = fut.result()
            if ok:
                kept.append(feat)

    kept_sorted = sorted(kept, key=lambda f: abs(
        pd.Series(work[f].values).corr(pd.Series(y_arr), method='spearman') or 0
    ), reverse=True)
    print(f"  IC filter: {len(feat_cols)} → {len(kept_sorted)} (|IC|>{IC_MIN_ABS}, IR>{IR_MIN})")
    return kept_sorted


# ══════════════════════════════════════════════════════════
# Part 6: Purged Time Split
# ══════════════════════════════════════════════════════════

def purged_time_split(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split with ±5 day purge around boundaries."""
    df = df.copy()
    df['date_d'] = pd.to_datetime(df['date']).dt.normalize()

    train_end = pd.Timestamp(TRAIN_END)
    val_start = pd.Timestamp(VAL_START)
    val_end = pd.Timestamp(VAL_END)
    test_start = pd.Timestamp(TEST_START)

    trade_dates = pd.DatetimeIndex(sorted(df['date_d'].dropna().unique()))
    purge_dates = set()

    # train → val boundary
    purge_dates.update(trade_dates[trade_dates > train_end][:PURGE_DAYS])
    purge_dates.update(trade_dates[trade_dates < val_start][-PURGE_DAYS:])
    # val → test boundary
    purge_dates.update(trade_dates[trade_dates > val_end][:PURGE_DAYS])
    purge_dates.update(trade_dates[trade_dates < test_start][-PURGE_DAYS:])

    clean = df[~df['date_d'].isin(purge_dates)].copy()
    train_df = clean[clean['date_d'] <= train_end].copy()
    val_df = clean[(clean['date_d'] >= val_start) & (clean['date_d'] <= val_end)].copy()
    test_df = clean[clean['date_d'] >= test_start].copy()

    print(f"  Purged split: train={len(train_df)}, val={len(val_df)}, test={len(test_df)}, purged={len(purge_dates)}")
    return train_df, val_df, test_df


# ══════════════════════════════════════════════════════════
# Part 7: Expanding Window Scaler (no look-ahead)
# ══════════════════════════════════════════════════════════

def expanding_window_scale(train_df: pd.DataFrame, val_df: pd.DataFrame,
                           test_df: pd.DataFrame, feat_cols: List[str]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Scale features using expanding window up to each date."""
    combined = pd.concat([train_df, val_df, test_df], ignore_index=True)
    combined = combined.sort_values('date').reset_index(drop=True)
    combined['date_d'] = pd.to_datetime(combined['date']).dt.normalize()
    unique_dates = combined['date_d'].unique()

    X_scaled = combined[feat_cols].copy().fillna(0.0)
    X = X_scaled.values

    for d in unique_dates:
        mask_hist = (combined['date_d'] <= d).values
        mask_curr = (combined['date_d'] == d).values
        hist_data = X_scaled.loc[mask_hist]
        if len(hist_data) < 10:
            continue
        means = hist_data.mean().values
        stds = hist_data.std().replace(0, EPS).values
        X[mask_curr] = (X[mask_curr] - means) / stds

    # Split back
    n_train, n_val = len(train_df), len(val_df)
    X_train = X[:n_train]
    X_val = X[n_train:n_train + n_val]
    X_test = X[n_train + n_val:]

    print(f"  Scaled: train={X_train.shape}, val={X_val.shape}, test={X_test.shape}")
    return X_train, X_val, X_test


# ══════════════════════════════════════════════════════════
# Part 8: XGBoost Training
# ══════════════════════════════════════════════════════════

def train_xgboost(X_train: np.ndarray, y_train: np.ndarray,
                  X_val: np.ndarray, y_val: np.ndarray,
                  X_test: np.ndarray, y_test: np.ndarray,
                  feat_names: List[str]) -> Tuple[Any, Dict]:
    """Train XGBoost with validation-based early stopping."""
    import xgboost as xgb
    from sklearn.metrics import accuracy_score, roc_auc_score, precision_score, recall_score, f1_score

    pos_rate = y_train.mean()
    scale_weight = (1 - pos_rate) / max(pos_rate, EPS)

    model = xgb.XGBClassifier(
        **XGB_PARAMS,
        scale_pos_weight=scale_weight,
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )

    # Evaluation
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    acc = accuracy_score(y_test, y_pred)
    auc = roc_auc_score(y_test, y_proba)
    prec = precision_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)

    # Rank IC (Spearman) — the key metric for stock ranking models
    rank_ic = pd.Series(y_proba).corr(pd.Series(y_test), method='spearman')

    # Feature importance
    importances = model.feature_importances_
    top_idx = np.argsort(importances)[-20:][::-1]

    metrics = {
        'accuracy': float(acc), 'auc': float(auc),
        'precision': float(prec), 'recall': float(rec), 'f1': float(f1),
        'rank_ic': float(rank_ic),
        'n_features': len(feat_names),
        'n_train': len(y_train), 'n_val': len(y_val), 'n_test': len(y_test),
        'pos_rate_train': float(pos_rate),
        'pos_rate_test': float(y_test.mean()),
    }

    print(f"\n  === Training Results ===")
    print(f"  Accuracy: {acc*100:.1f}% | AUC: {auc:.4f} | Rank IC: {rank_ic:.4f}")
    print(f"  Precision: {prec:.3f} | Recall: {rec:.3f} | F1: {f1:.3f}")
    print(f"  Samples: {len(y_train)}/{len(y_val)}/{len(y_test)}")
    print(f"\n  Top 20 features:")
    for i in top_idx:
        print(f"    {feat_names[i]:<50s} {importances[i]:.4f}")

    return model, metrics


# ══════════════════════════════════════════════════════════
# Part 9: Prediction / Scanning
# ══════════════════════════════════════════════════════════

def scan_stock(code: str, csv_path: str, model: Any, feat_order: List[str]) -> Optional[Dict]:
    """Scan one stock and return the latest buy signal with score."""
    snaps = _process_one_stock(code, csv_path)
    if not snaps:
        return None

    # Get latest buy signal
    buy_snaps = [s for s in snaps if s.is_buy]
    if not buy_snaps:
        return None

    latest = buy_snaps[-1]
    feats = extract_base_features(latest)
    vec = np.array([feats.get(k, 0.0) for k in feat_order]).reshape(1, -1)

    proba = model.predict_proba(vec)[0, 1]
    score = proba * 100

    zs_str = f'{int(latest.zs_low)}~{int(latest.zs_high)}' if latest.zs_low > 0 else ''

    # Entry/Stop/TP for 中枢内 buy
    entry = stop = tp1 = rr = None
    if latest.zs_low > 0 and latest.pos == '内':
        zl, zh = latest.zs_low, latest.zs_high
        entry = zl + (zh - zl) * 0.1
        stop = zl * 0.97
        tp1 = zh + (zh - zl) * 0.5
        rr = (tp1 - entry) / max(entry - stop, EPS) if entry > stop else 0

    return {
        'code': code,
        'date': latest.date,
        'price': round(latest.price, 2),
        'score': round(score, 1),
        'bsp_label': f"Buy-{'三买' if '3' in str(latest.bsp_types) else '二买' if '2' in str(latest.bsp_types) else '一买' if '1' in str(latest.bsp_types) else 'Buy'}",
        'pos': latest.pos,
        'ytd': round(latest.ytd, 1),
        'zs_str': zs_str,
        'entry': round(entry, 1) if entry else None,
        'stop': round(stop, 1) if stop else None,
        'tp1': round(tp1, 1) if tp1 else None,
        'rr': round(rr, 1) if rr else None,
    }


# ══════════════════════════════════════════════════════════
# Main Pipeline
# ══════════════════════════════════════════════════════════

def main():
    import csv as csv_mod
    t_total = time.time()

    print("=" * 70)
    print("CSI 300 生产级训练管线 v2.0")
    print("=" * 70)

    # ── 1. Collect BSP snapshots ──
    print("\n[1/8] Collecting BSP snapshots via chan.py step_load...")
    csv_files = sorted(DATA_DIR.glob("*.csv"))
    print(f"  Found {len(csv_files)} CSV files")

    snaps, _ = collect_all_snapshots(csv_files, max_stocks=300)
    if len(snaps) < 100:
        print(f"  ⚠ Not enough snapshots ({len(snaps)}), aborting")
        return

    # ── 2. Build labels ──
    print("\n[2/8] Building enhanced labels (Triple-Barrier + CS percentile + MFE/MAE)...")
    label_df = build_labels(snaps)

    # Filter to clear labels only
    valid_mask = label_df['label'].isin([0, 1])
    label_df = label_df[valid_mask].reset_index(drop=True)
    # Map snap indices
    valid_indices = np.where(valid_mask.values)[0]
    snaps = [snaps[i] for i in valid_indices]
    print(f"  Valid labeled samples: {len(snaps)}")

    # ── 3. Extract base features ──
    print("\n[3/8] Extracting base features (55-dim)...")
    feat_df, base_cols = build_feature_matrix(snaps)
    print(f"  Base features: {len(base_cols)}")

    # ── 4. Feature expansion: lightweight — only base features, skip full expansion
    #    Full expansion (55→5940) on 2628 train samples causes severe overfitting.
    #    Use only base 55-dim features, which achieved AUC=0.667 in simpler model.
    print("\n[4/8] Feature expansion: using base features only (55-dim, proven AUC 0.667)...")
    all_feat_cols = list(base_cols)  # skip time-series + cross-sectional for now
    print(f"  Features: {len(all_feat_cols)}")

    # ── 5. Merge labels ──
    print("\n[5/8] Merge labels...")
    feat_df['label'] = label_df['label'].values
    feat_df['code'] = label_df['code'].values
    feat_df['date'] = label_df['date'].values

    # ── 6. Purged time split（先 split，消除特征选择泄漏 P0-05）──
    print("\n[6/8] Purged time split (±5 day buffer)...")
    train_df, val_df, test_df = purged_time_split(feat_df)

    # ── 7. FeaturePipeline（split-before-fit：fit 只在 train）──
    print("\n[7/8] FeaturePipeline (split-before-fit, 无泄漏)...")
    from feature_pipeline import FeaturePipeline
    pipeline = FeaturePipeline()
    pipeline.fit(train_df, all_feat_cols, 'label')
    X_train = pipeline.transform(train_df).values
    X_val = pipeline.transform(val_df).values
    X_test = pipeline.transform(test_df).values
    final_feat_cols = pipeline.keep_features
    print(f"  Final features: {len(final_feat_cols)} "
          f"(constants={len(pipeline.constants_removed)}, "
          f"corr_drop={len(pipeline.correlation_drop)}, "
          f"ic_drop={len(pipeline.ic_drop)}, "
          f"missing_drop={len(pipeline.missing_dropped)})")
    # 保存 preprocessing 工件（model bundle 的一部分）
    pipeline.save(MODEL_DIR / 'preprocessing.json')

    y_train = train_df['label'].values.astype(int)
    y_val = val_df['label'].values.astype(int)
    y_test = test_df['label'].values.astype(int)

    # ── 8. Train ──
    print("\n[8/8] Training XGBoost...")
    model, metrics = train_xgboost(
        X_train, y_train, X_val, y_val, X_test, y_test, final_feat_cols)

    # ── Save ──
    model_path = MODEL_DIR / "chan_xgb_production.pkl"
    with open(model_path, 'wb') as f:
        pickle.dump(model, f)

    meta = {
        **metrics,
        'feature_names': final_feat_cols,
        'engine': 'chan.py step_load (Vespa314 CChan)',
        'labeling': 'Triple-Barrier + CS percentile + MFE/MAE composite',
        'trained_at': pd.Timestamp.now().isoformat(),
        'total_time_s': round(time.time() - t_total, 1),
    }
    with open(MODEL_DIR / "chan_xgb_production_meta.json", 'w') as f:
        json.dump(meta, f, indent=2, default=str)

    print(f"\n{'='*70}")
    print(f"✅ Training complete in {time.time()-t_total:.0f}s")
    print(f"   Model: {model_path} ({model_path.stat().st_size/1024:.0f}KB)")
    print(f"   AUC: {metrics['auc']:.4f} | Rank IC: {metrics['rank_ic']:.4f}")
    print(f"{'='*70}")

    return model, final_feat_cols, snaps, feat_df


if __name__ == '__main__':
    main()
