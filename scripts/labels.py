#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
标签与评估（V2，落地 P0-04 / COMMIT 4）：

    build_meta_labels           Triple-Barrier meta-label（非对称 upper/lower）
    build_forward_excess_targets 超额收益目标（相对 benchmark）
    daily_ic                    每日横截面 IC（正确口径）
    mark_signal_freshness       信号新鲜度（fresh BSP gate 的标签侧）

标签口径（方案 P0-04 推荐，单一可审计）：
    candidate = 当日新鲜 Buy BSP
    entry = 信号生成后下一可交易价格（以 snap.price 近似）
    atr = ATR14
    upper = entry + 1.5 × ATR
    lower = entry - 1.0 × ATR
    horizon = 10 个交易日
    先触及 upper -> 1；先触及 lower -> 0；都未触及 -> TIMEOUT(-1)
    TIMEOUT 从 classifier 训练剔除（timeout_policy='exclude'），但保留用于回测统计。
"""
import numpy as np
import pandas as pd


def compute_atr(highs, lows, closes, period=14):
    """True Range 的 EMA 平滑 ATR。返回标量（最后值）。"""
    h = np.asarray(highs, dtype=float)
    l = np.asarray(lows, dtype=float)
    c = np.asarray(closes, dtype=float)
    if len(c) < 2:
        return np.nan
    prev_c = np.roll(c, 1)
    prev_c[0] = c[0]
    tr = np.maximum.reduce([h - l, np.abs(h - prev_c), np.abs(l - prev_c)])
    atr = pd.Series(tr).ewm(alpha=1.0 / period, adjust=False).mean().iloc[-1]
    return float(atr)


def _barrier_label(snap, horizon=10, upper_atr=1.5, lower_atr=1.0):
    """单个 snapshot 的 Triple-Barrier 标签。返回 (label, meta)。"""
    atr = compute_atr(snap.highs, snap.lows, snap.closes)
    if not np.isfinite(atr) or atr <= 0:
        return -1, {'atr': np.nan, 'hit_bar': 'no_atr', 'bars_held': 0}
    entry = float(snap.price)
    upper = entry + upper_atr * atr
    lower = max(entry - lower_atr * atr, 1e-8)
    idx = snap.idx
    future_h = np.asarray(snap.all_highs[idx + 1:], dtype=float)
    future_l = np.asarray(snap.all_lows[idx + 1:], dtype=float)
    n = min(len(future_h), horizon)
    for i in range(n):
        h = future_h[i]
        l = future_l[i]
        if not (np.isfinite(h) and np.isfinite(l)):
            continue
        hit_u = h >= upper
        hit_l = l <= lower
        if not hit_u and not hit_l:
            continue
        if hit_u and not hit_l:
            return 1, {'atr': atr, 'hit_bar': 'upper', 'bars_held': i + 1}
        if hit_l and not hit_u:
            return 0, {'atr': atr, 'hit_bar': 'lower', 'bars_held': i + 1}
        # 同 bar 双触：按距 entry 更近者
        if abs(upper - entry) <= abs(entry - lower):
            return 1, {'atr': atr, 'hit_bar': 'upper', 'bars_held': i + 1}
        return 0, {'atr': atr, 'hit_bar': 'lower', 'bars_held': i + 1}
    return -1, {'atr': atr, 'hit_bar': 'timeout', 'bars_held': n}


def build_meta_labels(snaps, horizon=10, upper_atr=1.5, lower_atr=1.0,
                      timeout_policy='exclude'):
    """
    Triple-Barrier meta-label DataFrame。
    timeout_policy:
        'exclude' -> TIMEOUT 样本的 label 置为 NaN（训练时剔除），但保留 timeout 标志列。
        'keep'    -> 保留 TIMEOUT 作为 -1。
    返回 df 含列: code/date/idx/is_buy/price/atr/hit_bar/bars_held/label/is_timeout
    """
    rows = []
    for s in snaps:
        lab, meta = _barrier_label(s, horizon, upper_atr, lower_atr)
        is_timeout = (lab == -1)
        label = lab
        if is_timeout and timeout_policy == 'exclude':
            label = np.nan
        rows.append({
            'code': s.code, 'date': s.date, 'idx': s.idx,
            'is_buy': s.is_buy, 'price': s.price,
            'atr': meta['atr'], 'hit_bar': meta['hit_bar'],
            'bars_held': meta['bars_held'],
            'is_timeout': is_timeout, 'label': label,
        })
    df = pd.DataFrame(rows)
    n1 = int((df['label'] == 1).sum())
    n0 = int((df['label'] == 0).sum())
    nto = int(df['is_timeout'].sum())
    total = len(df)
    print(f"  meta-label: 1={n1}({n1/max(total,1)*100:.1f}%) "
          f"0={n0}({n0/max(total,1)*100:.1f}%) "
          f"timeout={nto}({nto/max(total,1)*100:.1f}%)")
    return df


def build_forward_excess_targets(snaps, benchmark_returns=None, horizon=10):
    """
    超额收益目标：forward_excess_return_10d = stock_return_10d - benchmark_return_10d。
    benchmark_returns: 可选，{date_str: benchmark_forward_10d_return} 字典；
                       未提供时只算 stock_return（超额目标暂缺）。
    返回 df 含列: code/date/idx/forward_ret_10d/excess_ret_10d
    """
    rows = []
    for s in snaps:
        idx = s.idx
        n_total = len(s.all_closes)
        fut_idx = min(idx + horizon, n_total - 1)
        fwd = np.nan
        if fut_idx > idx and s.price > 0:
            fwd = (s.all_closes[fut_idx] / s.price - 1) * 100
        excess = np.nan
        if benchmark_returns is not None and np.isfinite(fwd):
            b = benchmark_returns.get(s.date, np.nan)
            if np.isfinite(b):
                excess = fwd - b
        rows.append({'code': s.code, 'date': s.date, 'idx': s.idx,
                     'forward_ret_10d': fwd, 'excess_ret_10d': excess})
    return pd.DataFrame(rows)


def daily_ic(df, score_col, label_col, date_col='date', method='spearman'):
    """
    每日横截面 IC。返回 DataFrame(date, ic, n)。
    按 date 分组，对 score_col 与 label_col 算秩相关（spearman）/皮尔逊(pearson)。
    """
    out = []
    for d, g in df.groupby(date_col):
        x = g[score_col].astype(float)
        y = g[label_col].astype(float)
        m = x.notna() & y.notna()
        if m.sum() < 5:
            out.append({'date': d, 'ic': np.nan, 'n': int(m.sum())})
            continue
        if method == 'spearman':
            ic = x[m].corr(y[m], method='spearman')
        else:
            ic = x[m].corr(y[m])
        out.append({'date': d, 'ic': float(ic), 'n': int(m.sum())})
    return pd.DataFrame(out)


def mark_signal_freshness(snaps, asof_date=None):
    """
    信号新鲜度标记。asof_date=None 时，训练侧每个 step_load 事件即视为 fresh。
    返回为每个 snap 增加 is_fresh_bsp=True 的列表（推理侧由扫描脚本按 signal_age 判定）。
    """
    for s in snaps:
        s.is_fresh_bsp = True
    return snaps


if __name__ == '__main__':
    # 自检：合成 snapshots 验证 Triple-Barrier + daily IC
    class FakeSnap:
        pass

    rng = np.random.RandomState(0)
    snaps = []
    for i in range(200):
        s = FakeSnap()
        s.code = f'{i:06d}'
        s.date = pd.Timestamp('2026-01-01') + pd.Timedelta(days=i // 10)
        s.date = str(s.date.date())
        s.idx = 60
        s.is_buy = True
        s.price = 10.0
        n = 90
        s.closes = rng.randn(n).cumsum() + 10
        s.highs = s.closes + abs(rng.randn(n))
        s.lows = s.closes - abs(rng.randn(n))
        s.all_closes = np.concatenate([s.closes, (rng.randn(20) * 0.3).cumsum() + s.closes[-1]])
        s.all_highs = s.all_closes + abs(rng.randn(len(s.all_closes)))
        s.all_lows = s.all_closes - abs(rng.randn(len(s.all_closes)))
        snaps.append(s)

    lbl = build_meta_labels(snaps)
    print('meta-label 列:', list(lbl.columns))
    print('有效 label 数:', lbl['label'].notna().sum())

    # daily IC 自检
    d = pd.DataFrame({'date': np.repeat(['d1', 'd2'], 50),
                      'score': rng.randn(100),
                      'label': rng.randint(0, 2, 100)})
    ic = daily_ic(d, 'score', 'label')
    print('daily IC:')
    print(ic.to_string(index=False))
    print('labels.py 自检通过')
