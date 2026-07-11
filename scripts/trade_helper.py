#!/usr/bin/env python3
"""
TradeHelper 核心模块吸收 — Minimal Viable Integration

吸收自: https://github.com/Little-Pr1nce/TradeHelper
三个核心模块精简合并:
  1. 概率预测引擎 — 1/3/5日涨跌概率 (analog法)
  2. 数据质量闸门 — 交易前自动质量评分+降级
  3. 市场状态检测 — ADX+波动率 → 趋势/震荡分类

使用:
  from trade_helper import predict_probability, check_data_quality, detect_regime

设计原则:
  - 零外部依赖(只用numpy)
  - 自包含单文件
  - 返回简洁dict，易集成到analyze.py
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Optional

# ══════════════════════════════════════════════════════════════════
# 1. 概率预测引擎 — Analog历史相似状态法
# ══════════════════════════════════════════════════════════════════

FEATURE_NAMES = ("momentum_5", "momentum_20", "trend_20", "volatility_20")


def _compute_features(close: np.ndarray) -> dict:
    """从收盘价序列计算4个特征"""
    if len(close) < 25:
        return {}
    c = close.astype(float)
    mom5 = (c[-1] / c[-6] - 1) if len(c) >= 6 else 0
    mom20 = (c[-1] / c[-21] - 1) if len(c) >= 21 else 0
    ma20 = np.mean(c[-20:])
    trend20 = (c[-1] / ma20 - 1) if ma20 > 0 else 0
    rets = np.diff(c[-21:]) / c[-21:-1]
    vol20 = np.std(rets) if len(rets) > 1 else 0
    return {
        "momentum_5": mom5,
        "momentum_20": mom20,
        "trend_20": trend20,
        "volatility_20": vol20,
    }


def _build_samples(close: np.ndarray, horizon: int) -> tuple:
    """构建训练样本: 对每个历史时点计算特征+未来horizon日收益率"""
    n = len(close)
    min_len = 25 + horizon
    if n < min_len:
        return None, None, None, None

    features_list, returns_list = [], []
    for i in range(25, n - horizon):
        window = close[: i + 1]
        feat = _compute_features(window)
        if not feat:
            continue
        fut_ret = close[i + horizon] / close[i] - 1.0
        features_list.append([feat[k] for k in FEATURE_NAMES])
        returns_list.append(fut_ret)

    if len(features_list) < 30:
        return None, None, None, None

    X = np.array(features_list)
    y = np.array(returns_list)
    return X, y, np.array([_compute_features(close)[k] for k in FEATURE_NAMES]), close


def predict_probability(
    close: np.ndarray,
    horizon: int = 5,
    neighbor_count: int = 80,
    threshold: float = 0.01,
) -> dict | None:
    """
    用历史相似状态预测未来horizon日的涨跌概率。

    Args:
        close: 收盘价序列(numpy array, 至少60个数据点)
        horizon: 预测天数(1/3/5)
        neighbor_count: 最近邻数量
        threshold: 平盘阈值(±1%为平)

    Returns:
        dict with keys:
          prob_up, prob_flat, prob_down  — 三类概率
          direction                       — 'bullish'/'neutral'/'bearish'
          expected_return_p10/p50/p90     — 分位数收益
          sample_count                    — 有效样本数
          reference_price                 — 参考价
    """
    min_samples = 60
    if close is None or len(close) < min_samples + horizon:
        return None

    c = np.asarray(close, dtype=float)
    c = c[np.isfinite(c)]
    if len(c) < min_samples:
        return None

    X, y, current, _ = _build_samples(c, horizon)
    if X is None or current is None:
        return None

    # 标准化距离计算
    scale = np.std(X, axis=0)
    scale[scale == 0] = 1.0
    distances = np.sum(((X - current) / scale) ** 2, axis=1)

    # 取最近邻
    k = min(neighbor_count, len(y))
    nearest_idx = np.argpartition(distances, k - 1)[:k]
    nearest_returns = y[nearest_idx]

    # 三类概率
    prob_up = np.mean(nearest_returns > threshold)
    prob_down = np.mean(nearest_returns < -threshold)
    prob_flat = 1.0 - prob_up - prob_down

    # 方向判断
    probs = {"bullish": prob_up, "neutral": prob_flat, "bearish": prob_down}
    direction = max(probs, key=probs.get)

    # 分位数收益
    sorted_ret = np.sort(nearest_returns)
    n_ret = len(sorted_ret)
    p10 = sorted_ret[max(0, int(n_ret * 0.10))]
    p50 = sorted_ret[max(0, int(n_ret * 0.50))]
    p90 = sorted_ret[min(n_ret - 1, int(n_ret * 0.90))]

    return {
        "horizon": horizon,
        "reference_price": float(c[-1]),
        "prob_up": round(float(prob_up), 4),
        "prob_flat": round(float(prob_flat), 4),
        "prob_down": round(float(prob_down), 4),
        "direction": direction,
        "expected_return_p10": round(float(p10), 4),
        "expected_return_p50": round(float(p50), 4),
        "expected_return_p90": round(float(p90), 4),
        "sample_count": len(nearest_returns),
    }


def predict_all_horizons(
    close: np.ndarray, horizons: tuple = (1, 3, 5)
) -> dict[int, dict]:
    """一次性预测1/3/5日"""
    results = {}
    for h in horizons:
        r = predict_probability(close, horizon=h)
        if r:
            results[h] = r
    return results


# ══════════════════════════════════════════════════════════════════
# 2. 数据质量闸门
# ══════════════════════════════════════════════════════════════════


@dataclass
class DataQualityReport:
    score: float = 100.0
    status: str = "clean"  # clean / watch / degraded / blocked
    action: str = "normal"  # normal / reduce_position / block
    max_position_pct: float = 1.0  # 最大仓位比例(1.0=满仓)
    block_new_entries: bool = False
    issues: list = field(default_factory=list)  # 严重问题
    warnings: list = field(default_factory=list)  # 警告
    notes: list = field(default_factory=list)  # 备注


def check_data_quality(
    df_dict: dict,
    current_price: float = 0.0,
    min_samples: int = 60,
) -> DataQualityReport:
    """
    检查K线数据质量, 返回质量报告。

    Args:
        df_dict: {'open':[], 'high':[], 'low':[], 'close':[], 'volume':[]}
        current_price: 实时现价(用于与最新收盘价比对)
        min_samples: 最少K线数量

    返回 DataQualityReport:
      - status='clean': 满分可全仓
      - status='watch': 85分以下，注意
      - status='degraded': 70分以下，仓位减半
      - status='blocked': 50分以下或严重问题，禁止开仓
    """
    report = DataQualityReport()

    close = np.asarray(df_dict.get("close", []), dtype=float)
    if len(close) == 0:
        report.issues.append("K线数据为空")
        return _finalize_dq(report)

    n = len(close)

    # 1. 样本量检查
    if n < 20:
        report.issues.append(f"K线样本严重不足: 仅{n}条 (<20)")
    elif n < min_samples:
        report.warnings.append(f"K线样本偏少: {n}条 (<{min_samples})")

    # 2. OHLCV完整性
    for col in ["open", "high", "low", "close", "volume"]:
        vals = df_dict.get(col, [])
        if len(vals) < n:
            report.issues.append(f"缺少{col}字段或长度不匹配")

    # 3. 价格合法性
    if report.issues:
        return _finalize_dq(report)

    o = np.asarray(df_dict["open"], dtype=float)
    h = np.asarray(df_dict["high"], dtype=float)
    l = np.asarray(df_dict["low"], dtype=float)
    v = np.asarray(df_dict["volume"], dtype=float)

    # 价格非正
    for arr, name in [(o, "开"), (h, "高"), (l, "低"), (close, "收")]:
        if np.any(arr <= 0):
            report.issues.append(f"存在非正{name}盘价")

    # OHLC关系异常
    bad = (h < l) | (close > h * 1.001) | (close < l * 0.999)
    bad_count = int(np.sum(bad))
    if bad_count > 0:
        report.issues.append(f"OHLC价格关系异常: {bad_count}条")

    # 成交量检查
    zero_vol_ratio = np.mean(v <= 0) if len(v) > 0 else 0
    if zero_vol_ratio > 0.2:
        report.warnings.append(f"零/负成交量占比过高: {zero_vol_ratio:.1%}")

    # 涨跌幅异常
    if n >= 2:
        rets = np.abs(np.diff(close) / close[:-1])
        huge = np.sum(rets > 0.60)
        large = np.sum(rets > 0.25)
        if huge > 0:
            report.issues.append(f"疑似复权异常: 单日涨跌>60%共{int(huge)}次")
        elif large > 0:
            report.warnings.append(f"较大单日跳变: >25%共{int(large)}次")

    # 实时价vs收盘价偏离
    if current_price > 0 and close[-1] > 0:
        gap = abs(current_price - close[-1]) / close[-1]
        if gap > 0.25:
            report.warnings.append(f"实时价与最新K线收盘偏离较大: {gap:.1%}")
        elif gap > 0.10:
            report.notes.append(f"实时价偏离K线收盘: {gap:.1%}")

    return _finalize_dq(report)


def _finalize_dq(report: DataQualityReport) -> DataQualityReport:
    """结算质量评分和操作建议"""
    score = 100.0
    score -= 35.0 * len(report.issues)
    score -= 8.0 * len(report.warnings)
    report.score = max(0.0, min(100.0, score))

    if report.issues or report.score < 50:
        report.status = "blocked"
        report.action = "block"
        report.max_position_pct = 0.0
        report.block_new_entries = True
    elif report.score < 70:
        report.status = "degraded"
        report.action = "reduce_position"
        report.max_position_pct = 0.5
    elif report.score < 85:
        report.status = "watch"
        report.action = "normal"
        report.max_position_pct = 0.75
    else:
        report.status = "clean"
        report.action = "normal"
        report.max_position_pct = 1.0

    return report


# ══════════════════════════════════════════════════════════════════
# 3. 市场状态检测 — ADX + 波动率 → 趋势/震荡
# ══════════════════════════════════════════════════════════════════


def calc_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray | None:
    """手动计算ADX(不需要ta库)"""
    n = len(close)
    if n < period + 1:
        return None

    # True Range
    tr = np.zeros(n)
    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hc, lc)

    # ATR (Wilder smoothing)
    atr = np.zeros(n)
    atr[period] = np.mean(tr[1 : period + 1])
    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    # +DM / -DM
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    for i in range(1, n):
        up = high[i] - high[i - 1]
        down = low[i - 1] - low[i]
        if up > down and up > 0:
            plus_dm[i] = up
        if down > up and down > 0:
            minus_dm[i] = down

    # Smoothed DM
    plus_di = np.zeros(n)
    minus_di = np.zeros(n)
    for i in range(period, n):
        if atr[i] > 0:
            plus_di[i] = 100 * _wilder_smooth(plus_dm, period, i) / atr[i]
            minus_di[i] = 100 * _wilder_smooth(minus_dm, period, i) / atr[i]

    # DX → ADX
    dx = np.zeros(n)
    for i in range(period, n):
        denom = plus_di[i] + minus_di[i]
        if denom > 0:
            dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / denom

    adx = np.zeros(n)
    adx[period * 2 - 1] = np.mean(dx[period : period * 2])
    for i in range(period * 2, n):
        adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

    return adx


def _wilder_smooth(series: np.ndarray, period: int, index: int) -> float:
    """Wilder平滑求和"""
    return series[index] if index <= period else _wilder_cached(series, period, index)


_wilder_cache = {}


def _wilder_cached(series: np.ndarray, period: int, index: int) -> float:
    key = (id(series), period, index)
    if key in _wilder_cache:
        return _wilder_cache[key]
    total = series[index]
    for j in range(1, period):
        if index - j >= 0:
            total += series[index - j] * ((period - 1) / period) ** j
        else:
            break
    _wilder_cache[key] = total
    return total


def detect_regime(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    adx_threshold_high: float = 25,
    adx_threshold_low: float = 20,
) -> dict:
    """
    检测市场状态(趋势/震荡)。

    Returns:
        dict with:
          regime: 'trending_volatile' / 'trending_steady' / 'ranging' / 'transitional' / 'unknown'
          adx: 当前ADX值
          adx_mean: 近20日ADX均值
          atr_pct: ATR占价格百分比
          weights: 各指标权重建议
    """
    # 默认权重
    trending_weights = {"rsi": 0.15, "macd": 0.25, "bb_pct": 0.10, "kdj": 0.15, "momentum": 0.20, "volume": 0.15}
    ranging_weights = {"rsi": 0.20, "macd": 0.10, "bb_pct": 0.20, "kdj": 0.20, "momentum": 0.15, "volume": 0.15}
    equal_weights = {"rsi": 0.17, "macd": 0.17, "bb_pct": 0.17, "kdj": 0.17, "momentum": 0.16, "volume": 0.16}

    adx = calc_adx(high, low, close)
    if adx is None:
        return {"regime": "unknown", "adx": None, "adx_mean": None, "atr_pct": None, "weights": equal_weights}

    adx_valid = adx[~np.isnan(adx)]
    if len(adx_valid) < 5:
        return {"regime": "unknown", "adx": None, "adx_mean": None, "atr_pct": None, "weights": equal_weights}

    adx_now = float(adx_valid[-1])
    adx_mean = float(np.mean(adx_valid[-20:])) if len(adx_valid) >= 20 else adx_now

    # ATR%
    n = len(close)
    tr_list = []
    for i in range(max(1, n - 20), n):
        if i > 0:
            hl = high[i] - low[i]
            hc = abs(high[i] - close[i - 1])
            lc = abs(low[i] - close[i - 1])
            tr_list.append(max(hl, hc, lc))
    atr = np.mean(tr_list) if tr_list else 0
    atr_pct = atr / close[-1] if close[-1] > 0 else 0

    # 长期趋势辅助
    long_term_up = False
    if len(close) >= 60:
        ma60 = np.mean(close[-60:])
        total_ret = (close[-1] - close[0]) / close[0] if close[0] > 0 else 0
        if total_ret > 0.50 and close[-1] > ma60:
            long_term_up = True

    judge = adx_mean if adx_mean is not None else adx_now

    if judge > adx_threshold_high:
        if atr_pct > 0.05:
            regime = "trending_volatile"
            weights = trending_weights
        else:
            regime = "trending_steady"
            weights = trending_weights
    elif judge < adx_threshold_low:
        regime = "trending_steady" if long_term_up else "ranging"
        weights = ranging_weights if regime == "ranging" else trending_weights
    else:
        regime = "trending_steady" if long_term_up else "transitional"
        weights = trending_weights if regime == "trending_steady" else equal_weights

    return {
        "regime": regime,
        "adx": round(adx_now, 1),
        "adx_mean": round(adx_mean, 1),
        "atr_pct": round(atr_pct, 4),
        "weights": weights,
        "long_term_up": long_term_up,
    }


# ══════════════════════════════════════════════════════════════════
# 4. 一体化接口 — 一键运行全部分析
# ══════════════════════════════════════════════════════════════════


def full_trade_helper_analysis(
    o: np.ndarray,
    h: np.ndarray,
    l: np.ndarray,
    c: np.ndarray,
    v: np.ndarray,
    live_price: float = 0.0,
) -> dict:
    """
    一键运行TradeHelper全部吸收模块。

    Args:
        o, h, l, c, v: K线数据 (numpy arrays, 至少60根)
        live_price: 实时价

    Returns:
        dict with keys:
          data_quality: DataQualityReport
          regime: 市场状态
          forecast_1d/3d/5d: 概率预测
    """
    result = {}

    # 1. 数据质量
    dq = check_data_quality(
        {"open": o, "high": h, "low": l, "close": c, "volume": v},
        current_price=live_price,
    )
    result["data_quality"] = {
        "score": dq.score,
        "status": dq.status,
        "action": dq.action,
        "max_position_pct": dq.max_position_pct,
        "block_new": dq.block_new_entries,
        "issues": dq.issues,
        "warnings": dq.warnings,
    }

    # 2. 市场状态
    result["regime"] = detect_regime(h, l, c)

    # 3. 概率预测
    forecasts = predict_all_horizons(c)
    for h in [1, 3, 5]:
        key = f"forecast_{h}d"
        result[key] = forecasts.get(h)

    # 4. 综合信号
    f5 = result.get("forecast_5d") or {}
    regime = result["regime"]["regime"]
    dq_status = result["data_quality"]["status"]

    # 综合判断
    signal = "neutral"
    if dq_status == "blocked":
        signal = "blocked"
    elif f5.get("direction") == "bullish" and regime.startswith("trending"):
        signal = "bullish_strong"
    elif f5.get("direction") == "bullish":
        signal = "bullish"
    elif f5.get("direction") == "bearish" and regime == "ranging":
        signal = "bearish"
    elif f5.get("direction") == "bearish":
        signal = "bearish_strong"

    result["signal"] = signal
    result["summary"] = (
        f"[{signal}] 数据{dq_status}({dq.score:.0f}分) | "
        f"市场{regime}(ADX={result['regime']['adx']}) | "
        f"5日方向={f5.get('direction','?')} "
        f"(涨{f5.get('prob_up',0):.0%}/平{f5.get('prob_flat',0):.0%}/跌{f5.get('prob_down',0):.0%})"
    )

    return result


# ══════════════════════════════════════════════════════════════════
# CLI 入口
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys, json
    import subprocess as sp
    import time

    code = sys.argv[1] if len(sys.argv) > 1 else "002050"

    # 用baostock获取数据
    import baostock as bs

    bs.login()
    sym = f"{'sh' if code.startswith('6') else 'sz'}.{code}"
    rs = bs.query_history_k_data_plus(
        sym, "date,open,high,low,close,volume",
        start_date="2025-07-01",
        end_date=time.strftime("%Y-%m-%d"),
        frequency="d",
        adjustflag="2",
    )
    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    bs.logout()

    if not rows:
        print("无数据")
        sys.exit(1)

    o = np.array([float(r[1]) for r in rows])
    h = np.array([float(r[2]) for r in rows])
    l = np.array([float(r[3]) for r in rows])
    c = np.array([float(r[4]) for r in rows])
    v = np.array([float(r[5]) for r in rows])

    # 腾讯实时价
    url = f"http://qt.gtimg.cn/q={'sh' if code.startswith('6') else 'sz'}{code}"
    r = sp.run(["curl", "-sL", "--max-time", "5", url], stdout=sp.PIPE)
    raw = r.stdout.decode("gbk", "ignore")
    live = 0.0
    for line in raw.split("\n"):
        p = line.split("~")
        if len(p) >= 10:
            live = float(p[3])

    if live > 0:
        c[-1] = live

    result = full_trade_helper_analysis(o, h, l, c, v, live_price=live)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
