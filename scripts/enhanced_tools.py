#!/usr/bin/env python3
"""
增强工具集 — 从14个GitHub仓库吸收的指标与算法

模块来源:
  1. 宏观风险NLP  — Stocks-Master/smcore/risk/macro.py
  2. 左侧支撑检测  — a-share-left-screener/ashare/module2_tech.py + indicators.py
  3. 横截面排名    — astock-quant/astock_quant/factors/value_score.py (概念吸收)
  4. 信号衰减模型  — BAISYS_QUANT/LogicAnalyzer/PipelineScoring.py (概念吸收)

设计原则:
  - 零外部依赖(仅numpy/pandas)
  - 自包含单文件
  - 所有函数返回dict，易集成到analyze.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from functools import lru_cache
from typing import Optional

# ══════════════════════════════════════════════════════════════════
# 1. 宏观风险NLP检测 (吸收自 Stocks-Master)
# ══════════════════════════════════════════════════════════════════

MACRO_STOPWORDS = {
    "中国", "经济", "市场", "企业", "行业", "部门", "地方",
    "今年", "今日", "昨天", "消息", "报道", "记者", "相关", "持续", "推进", "表示",
}

MACRO_NOISE_TOKENS = {
    "报道", "日报道", "日称", "日表示", "今日", "今天", "昨日", "昨天",
    "其中", "此外", "与此同时", "截至", "目前", "近日", "今年以来",
    "同比增长", "增长", "发展", "合作", "基础设施", "农业", "教育",
    "集群", "战略", "推进", "表示", "人工智能", "粤港澳大湾区",
}

MACRO_RISK_STRONG_FRAGMENTS = frozenset({
    "爆发", "袭击", "空袭", "制裁", "冲突", "断供", "中断", "停摆", "危机",
    "紧张", "动荡", "禁运", "关闭", "撤离", "飙升", "暴跌", "战争", "军事",
    "战机", "导弹", "反击", "核设施",
})

MACRO_RISK_SOFT_FRAGMENTS = frozenset({
    "升级", "谈判", "会谈", "协议", "能源", "原油", "油价", "天然气",
    "供应链", "跨境", "外贸", "出口", "关税", "波动",
})

MACRO_RISK_ALL = MACRO_RISK_STRONG_FRAGMENTS | MACRO_RISK_SOFT_FRAGMENTS | {
    "中东", "霍尔木兹", "海峡", "航运", "港口", "不确定", "风险", "大选",
}

MACRO_POSITIVE_HINTS = (
    "高质量发展", "赋能", "提质", "提效", "推进", "促进", "优化", "改善",
    "增长", "回升", "回暖", "稳住", "扩大", "加强", "提升", "建设",
    "投产", "开工", "竣工", "发布", "出台", "支持", "发展", "创新",
    "合作", "达成", "签约", "获批", "实现", "完成", "落地", "启动", "深化",
)

EXCLUDED_TITLES = frozenset({"国际联播快讯", "国内联播快讯", "联播快讯", "新闻联播", "朝闻天下", "晚间新闻"})
PROMO_KEYWORDS = ("伟大征程", "复兴之路", "辉煌中国", "奋斗", "初心使命", "新征程", "百年风华", "长征")


def macro_risk_scan(text: str, title: str = "") -> dict:
    """
    扫描一条文本的宏观风险信号。

    Args:
        text: 新闻正文
        title: 新闻标题(可选，用于排除宣传/联播类)

    Returns:
        dict with:
          risk_score: int (0=无风险, 1-2=低, 3-4=中, 5+=高)
          risk_level: str ('low'/'medium'/'high')
          strong_hits: list 强风险词
          soft_hits: list 软风险词
          all_tags: list 全部命中词
    """
    # 排除
    if title:
        t = title.strip()
        if t in EXCLUDED_TITLES or "联播快讯" in t:
            return {"risk_score": 0, "risk_level": "low", "strong_hits": [], "soft_hits": [], "all_tags": []}
        if any(kw in t for kw in PROMO_KEYWORDS):
            # 宣传类降级
            pass

    text_lower = f"{title} {text}".lower() if title else text.lower()

    strong_hits = [tok for tok in MACRO_RISK_STRONG_FRAGMENTS if tok in text_lower]
    soft_hits = [tok for tok in MACRO_RISK_SOFT_FRAGMENTS if tok in text_lower]

    # 正向语境降权
    if any(hint in text_lower for hint in MACRO_POSITIVE_HINTS):
        soft_hits = soft_hits[:1] if len(soft_hits) > 1 else soft_hits

    all_tags = list(dict.fromkeys(strong_hits + soft_hits))
    risk_score = len(strong_hits) * 2 + len(soft_hits)

    if risk_score >= 5:
        level = "high"
    elif risk_score >= 2:
        level = "medium"
    else:
        level = "low"

    return {
        "risk_score": risk_score,
        "risk_level": level,
        "strong_hits": strong_hits,
        "soft_hits": soft_hits,
        "all_tags": all_tags[:5],
    }


def macro_batch_scan(headlines: list[str]) -> dict:
    """
    批量扫描多条标题/新闻，聚合宏观风险。

    Returns:
        overall_level, total_score, top_tags, event_count
    """
    total = 0
    all_tags = []
    events = []
    for h in headlines:
        r = macro_risk_scan(h)
        if r["risk_score"] > 0:
            total += r["risk_score"]
            all_tags.extend(r["all_tags"])
            events.append({"title": h[:80], "score": r["risk_score"], "tags": r["all_tags"]})

    from collections import Counter
    top_tags = [t for t, _ in Counter(all_tags).most_common(10)]

    if total >= 8:
        level = "high"
    elif total >= 4:
        level = "medium"
    else:
        level = "low"

    return {
        "overall_level": level,
        "total_score": total,
        "top_tags": top_tags,
        "event_count": len(events),
        "events": events,
    }


# ══════════════════════════════════════════════════════════════════
# 2. 技术指标工具箱 (吸收自 a-share-left-screener)
# ══════════════════════════════════════════════════════════════════

def _ema(s: np.ndarray, n: int) -> np.ndarray:
    """指数移动平均"""
    result = np.zeros_like(s)
    result[0] = s[0]
    alpha = 2.0 / (n + 1)
    for i in range(1, len(s)):
        result[i] = alpha * s[i] + (1 - alpha) * result[i - 1]
    return result


def calc_macd(close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
    """返回 (dif, dea, hist)"""
    dif = _ema(close, fast) - _ema(close, slow)
    dea = _ema(dif, signal)
    hist = (dif - dea) * 2.0
    return dif, dea, hist


def calc_rsi(close: np.ndarray, n: int = 14) -> np.ndarray:
    """RSI"""
    diff = np.diff(close, prepend=close[0])
    up = np.maximum(diff, 0)
    dn = np.maximum(-diff, 0)
    # rolling mean
    rsi = np.zeros(len(close))
    for i in range(n, len(close)):
        avg_up = np.mean(up[i - n + 1:i + 1])
        avg_dn = np.mean(dn[i - n + 1:i + 1])
        if avg_dn == 0:
            rsi[i] = 100
        else:
            rsi[i] = 100 - 100 / (1 + avg_up / avg_dn)
    rsi[:n] = np.nan
    return rsi


def find_pivot_lows(low: np.ndarray, window: int = 10) -> list:
    """摆动低点: (index, price)。左右window根内最低"""
    lows = []
    n = len(low)
    for i in range(window, n - window):
        seg = low[i - window:i + window + 1]
        if low[i] == seg.min():
            lows.append((i, float(low[i])))
    return lows


def linreg_channel(close: np.ndarray, window: int = 60, band_k: float = 2.0) -> dict | None:
    """上升通道上下轨。返回 upper/lower band 及是否上升趋势"""
    n = len(close)
    if n < window:
        return None
    x = np.arange(window, dtype=float)
    y = close[-window:]
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    residuals = y - pred
    std = np.std(residuals)
    upper = pred[-1] + band_k * std
    lower = pred[-1] - band_k * std
    return {
        "slope": float(slope),
        "intercept": float(intercept),
        "upper_band": float(upper),
        "lower_band": float(lower),
        "uptrend": slope > 0,
        "lower_series": [float(p - band_k * std) for p in pred],
    }


def bollinger_lower(close: np.ndarray, n: int = 20, k: float = 2.0) -> np.ndarray:
    """布林带下轨"""
    ma = np.array([np.mean(close[max(0, i - n + 1):i + 1]) for i in range(len(close))])
    std = np.array([np.std(close[max(0, i - n + 1):i + 1]) for i in range(len(close))])
    return ma - k * std


def calc_kdj(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = 9) -> tuple:
    """KDJ(9,3,3) → (K, D, J)"""
    length = len(close)
    k = np.full(length, 50.0)
    d = np.full(length, 50.0)
    j = np.full(length, 50.0)
    for i in range(n - 1, length):
        hh = np.max(high[i - n + 1:i + 1])
        ll = np.min(low[i - n + 1:i + 1])
        rsv = (close[i] - ll) / (hh - ll) * 100 if hh > ll else 50
        k[i] = 2.0 / 3 * k[i - 1] + 1.0 / 3 * rsv if i > 0 else rsv
        d[i] = 2.0 / 3 * d[i - 1] + 1.0 / 3 * k[i] if i > 0 else k[i]
        j[i] = 3 * k[i] - 2 * d[i]
    return k, d, j


def kdj_tag(k_val: float, d_val: float, j_val: float) -> str:
    """KDJ状态标签"""
    if np.isnan(k_val) or np.isnan(d_val):
        return "数据不足"
    if k_val < 20 and d_val < 20:
        return "超卖区"
    if k_val > 80 and d_val > 80:
        return "超买区"
    if k_val > d_val and j_val > k_val:
        return "金叉向上"
    if k_val < d_val:
        return "死叉向下"
    return "中性"


def fib_levels(high: float, low: float) -> dict:
    """斐波那契回撤位"""
    rng = high - low
    return {
        "f382": round(high - rng * 0.382, 2),
        "f500": round(high - rng * 0.500, 2),
        "f618": round(high - rng * 0.618, 2),
    }


def atr_pct(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int = 14) -> float:
    """ATR占价格百分比"""
    n = len(close)
    if n < 2:
        return np.nan
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    atr = np.mean(tr[-window:])
    return atr / close[-1] if close[-1] > 0 else np.nan


def max_drawdown(close: np.ndarray, window: int = 250) -> float:
    """最大回撤%"""
    seg = close[-min(window, len(close)):]
    peak = np.maximum.accumulate(seg)
    dd = (seg - peak) / peak
    return float(np.min(dd) * 100)


def cumulative_return(close: np.ndarray, days: int = 120) -> float:
    """累计收益率%"""
    if len(close) <= days:
        return (close[-1] / close[0] - 1) * 100
    return (close[-1] / close[-days - 1] - 1) * 100


# ══════════════════════════════════════════════════════════════════
# 3. 左侧支撑检测 (吸收自 a-share-left-screener)
# ══════════════════════════════════════════════════════════════════

DEFAULT_LEFT_CONFIG = {
    "weights": {
        "channel": 30, "pivot": 25, "ma": 20,
        "oversold_div": 15, "drawdown": 10, "vol_confirm": 5,
    },
    "channel_window": 60, "channel_band_k": 2.0,
    "pivot_window": 10,
    "ma_list": [60, 120, 250],
    "ma_score_list": [20, 60, 120],
    "rsi_oversold": 30,
    "near_lower_pct": 5.0, "near_pivot_pct": 3.0, "near_ma_pct": 3.0,
    "drawdown_min": 0.15, "vol_shrink_ratio": 0.85,
    "min_price": 2.0, "min_amount_yi": 0.3,
    "boll_n": 20, "boll_k": 2.0,
}


def left_side_scan(close: np.ndarray, high: np.ndarray, low: np.ndarray,
                   volume: np.ndarray | None = None,
                   config: dict | None = None) -> dict:
    """
    左侧支撑位检测 — 判断股票是否正回踩关键支撑位。

    Args:
        close, high, low: 价格序列(numpy arrays)
        volume: 成交量(可选，用于量能确认)
        config: 配置参数(可选，使用默认)

    Returns:
        dict with keys:
          score: 综合分(0-100)
          n_signals: 命中信号数
          signals: 各信号命中情况
          supports: 支撑位列表
          main_support: 主要支撑(名称,价格)
          dist_support_pct: 距支撑%
    """
    cfg = {**DEFAULT_LEFT_CONFIG, **(config or {})}
    w = cfg["weights"]
    px = float(close[-1])
    n = len(close)
    if n < max(cfg["channel_window"], max(cfg["ma_list"])) + 5:
        return {"score": 0, "n_signals": 0, "signals": {},
                "supports": [], "main_support": None, "error": "数据不足"}

    score = 0.0
    signals = {}
    supports = []

    # 1) 上升通道下轨
    ch = linreg_channel(close, cfg["channel_window"], cfg["channel_band_k"])
    if ch and ch["uptrend"]:
        lb = ch["lower_band"]
        d = (px - lb) / px * 100
        if -1 <= d <= cfg["near_lower_pct"]:
            prox = max(0, 1 - abs(d) / cfg["near_lower_pct"])
            score += w["channel"] * (0.5 + 0.5 * prox)
            signals["channel"] = "✓"
            supports.append(("通道下轨", round(lb, 2)))
        else:
            signals["channel"] = ""
    else:
        signals["channel"] = ""

    # 2) 前期重要低点
    piv = find_pivot_lows(low, cfg["pivot_window"])
    if piv:
        cands = [p for (_, p) in piv if abs(p - px) / px <= 0.15]
        if cands:
            nearest = min(cands, key=lambda p: abs(p - px))
            d = (px - nearest) / px * 100
            if abs(d) <= cfg["near_pivot_pct"]:
                prox = max(0, 1 - abs(d) / cfg["near_pivot_pct"])
                score += w["pivot"] * (0.5 + 0.5 * prox)
                signals["pivot"] = "✓"
                supports.append(("前低", round(nearest, 2)))
    if "pivot" not in signals:
        signals["pivot"] = ""

    # 3) 关键均线支撑
    hit_ma, best_n, best_p = False, None, None
    for n_ma in cfg["ma_list"]:
        if len(close) < n_ma:
            continue
        ma = np.mean(close[-n_ma:])
        d = (px - ma) / px * 100
        if -1 <= d <= cfg["near_ma_pct"]:
            hit_ma = True
            if best_n is None or abs(d) < abs((px - best_p) / px * 100 if best_p else 999):
                best_n, best_p = n_ma, float(ma)
    if hit_ma:
        prox = max(0, 1 - abs((px - best_p) / px * 100) / cfg["near_ma_pct"])
        score += w["ma"] * (0.5 + 0.5 * prox)
        signals["ma"] = f"MA{best_n}"
        supports.append((f"MA{best_n}", round(best_p, 2)))
    else:
        signals["ma"] = ""

    # 4) 超跌 + 底背离
    rsi = calc_rsi(close)
    dif, dea, hist = calc_macd(close)
    oversold = not np.isnan(rsi[-1]) and rsi[-1] <= cfg["rsi_oversold"]
    green_shrink = hist[-1] < 0 and hist[-1] > hist[-2] if len(hist) >= 2 else False
    # 底背离简化检测
    bull_div = False
    look = 60
    if len(close) > look:
        c_tail = close[-15:]
        d_tail = dif[-15:]
        first_half = dif[-look:-look // 2]
        second_half = dif[-look // 2:]
        if c_tail[-1] <= np.min(c_tail[:-1]) and np.min(second_half) > np.min(first_half):
            bull_div = True
    hit_osc = oversold or green_shrink or bull_div
    if hit_osc:
        sub = (0.5 if oversold else 0) + (0.25 if green_shrink else 0) + (0.5 if bull_div else 0)
        score += w["oversold_div"] * min(1.0, sub)
    signals["osc"] = "".join(["超卖" if oversold else "", "缩柱" if green_shrink else "", "底背离" if bull_div else ""])

    # 5) 回撤幅度
    hi = float(np.max(high[-cfg["channel_window"]:]))
    dd = (hi - px) / hi if hi else 0
    if dd >= cfg["drawdown_min"]:
        score += w["drawdown"] * min(1.0, dd / 0.5)
    else:
        dd = 0

    # 6) 量能确认
    if volume is not None and len(volume) >= 20:
        avg20 = np.mean(volume[-21:-1])
        vol_ratio = volume[-1] / avg20 if avg20 > 0 else 1.0
        if supports and vol_ratio < cfg["vol_shrink_ratio"]:
            score += w["vol_confirm"] * 0.7
            signals["vol"] = "缩量企稳"

    n_sig = sum(1 for k in ("channel", "pivot", "ma") if signals.get(k)) + (1 if hit_osc else 0)

    # 主支撑
    main_support = None
    if supports:
        label, price = min(supports, key=lambda kv: abs(px - kv[1]))
        dist_pct = (px - price) / px * 100
        main_support = {"label": label, "price": price, "dist_pct": round(dist_pct, 2)}

    # 标准化到0-100
    max_possible = sum(w.values())
    score_norm = min(100, max(0, round(score / max_possible * 100)))

    return {
        "score": score_norm,
        "n_signals": n_sig,
        "signals": signals,
        "supports": supports,
        "main_support": main_support,
        "rsi": round(float(rsi[-1]), 1) if not np.isnan(rsi[-1]) else None,
        "drawdown_pct": round(dd * 100, 1),
    }


# ══════════════════════════════════════════════════════════════════
# 4. 横截面排名 (吸收自 astock-quant)
# ══════════════════════════════════════════════════════════════════

def cross_section_rank(series: pd.Series, min_count: int = 3) -> pd.Series:
    """
    按'每日横截面'做分位排名 → 防look-ahead。

    Args:
        series: pd.Series with MultiIndex(date, ticker)
        min_count: 当天最少有效股票数

    Returns:
        pd.Series of percentile ranks ∈ [0, 1]
    """
    def rank_one_day(x):
        if x.notna().sum() < min_count:
            return pd.Series(float('nan'), index=x.index)
        return x.rank(pct=True)

    if series.index.nlevels >= 2:
        return series.groupby(level='date', group_keys=False).transform(rank_one_day)
    return series.rank(pct=True)


# ══════════════════════════════════════════════════════════════════
# 5. 信号衰减模型 (吸收自 BAISYS_QUANT)
# ══════════════════════════════════════════════════════════════════

SIGNAL_DECAY = {
    "golden_cross": 30,       # 金叉30天半衰
    "divergence": 8,          # 背离8天半衰
    "kline_pattern": 10,      # K线形态10天半衰
    "oversold": 14,           # 超卖14天半衰
    "breakout": 20,           # 突破20天半衰
}


def signal_decay_weight(days_since: int, half_life: int, min_weight: float = 0.2) -> float:
    """
    信号衰减权重。

    Args:
        days_since: 信号产生后的天数
        half_life: 半衰期(天)
        min_weight: 最低权重(不低于此值)

    Returns:
        weight ∈ [min_weight, 1.0]
    """
    if days_since <= 0:
        return 1.0
    weight = 0.5 ** (days_since / half_life)
    return max(min_weight, weight)


def apply_signal_decay(signals: list[dict], current_day: int) -> list[dict]:
    """
    对信号列表应用衰减。

    Args:
        signals: [{'day': int, 'type': str, 'score': float}, ...]
        current_day: 当前交易日序号

    Returns:
        衰减后的信号列表(with decayed_score)
    """
    result = []
    for s in signals:
        days = current_day - s['day']
        hl = SIGNAL_DECAY.get(s['type'], 20)
        weight = signal_decay_weight(days, hl)
        result.append({**s, 'decay_weight': round(weight, 3),
                       'decayed_score': round(s['score'] * weight, 3)})
    return result


# ══════════════════════════════════════════════════════════════════
# 6. 一体化接口
# ══════════════════════════════════════════════════════════════════

def full_enhanced_analysis(
    close: np.ndarray, high: np.ndarray, low: np.ndarray,
    volume: np.ndarray | None = None,
    headlines: list[str] | None = None,
    previous_signals: list[dict] | None = None,
    current_day: int = 0,
) -> dict:
    """
    一键运行所有增强分析。

    Args:
        close, high, low: K线数据
        volume: 成交量(可选)
        headlines: 宏观新闻标题(可选)
        previous_signals: 历史信号列表(可选，用于衰减)
        current_day: 当前交易日序号

    Returns:
        dict with: left_side, macro_risk, decayed_signals, fib, kdj, indicators
    """
    result = {}

    # 左侧支撑
    result["left_side"] = left_side_scan(close, high, low, volume)

    # 宏观风险
    if headlines:
        result["macro_risk"] = macro_batch_scan(headlines)
    else:
        result["macro_risk"] = {"overall_level": "low", "total_score": 0, "top_tags": [], "event_count": 0}

    # 斐波那契
    hi90 = float(np.max(high[-90:])) if len(high) >= 90 else float(np.max(high))
    lo90 = float(np.min(low[-90:])) if len(low) >= 90 else float(np.min(low))
    result["fib"] = fib_levels(hi90, lo90)

    # KDJ
    k, d, j = calc_kdj(high, low, close)
    result["kdj"] = {
        "k": round(float(k[-1]), 2), "d": round(float(d[-1]), 2),
        "j": round(float(j[-1]), 2), "tag": kdj_tag(float(k[-1]), float(d[-1]), float(j[-1])),
    }

    # RSI
    rsi = calc_rsi(close)
    result["rsi"] = round(float(rsi[-1]), 1) if not np.isnan(rsi[-1]) else None

    # MACD
    dif, dea, hist = calc_macd(close)
    result["macd"] = {
        "dif": round(float(dif[-1]), 4), "dea": round(float(dea[-1]), 4),
        "hist": round(float(hist[-1]), 4),
        "signal": "金叉" if dif[-1] > dea[-1] and dif[-2] <= dea[-2] else
                  ("死叉" if dif[-1] < dea[-1] and dif[-2] >= dea[-2] else
                   ("多头" if dif[-1] > dea[-1] else "空头")),
    }

    # ATR
    result["atr_pct"] = round(atr_pct(high, low, close), 4)

    # 最大回撤
    result["max_dd_pct"] = round(max_drawdown(close), 2)

    # 回报
    result["ret_1m"] = round(cumulative_return(close, 21), 2)
    result["ret_3m"] = round(cumulative_return(close, 63), 2)
    result["ret_6m"] = round(cumulative_return(close, 126), 2)

    # 信号衰减
    if previous_signals and current_day > 0:
        result["decayed_signals"] = apply_signal_decay(previous_signals, current_day)

    return result


# ══════════════════════════════════════════════════════════════════
# CLI 测试
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys, json

    # 测试宏观风险
    test_news = [
        "中东局势突然升级，油价飙升10%，海峡航运中断",
        "美联储暗示9月降息，美股三大指数集体收涨",
        "中美新一轮贸易谈判将于下周举行，市场关注关税走向",
        "国内新能源汽车销量再创新高，比亚迪Q2交付突破100万辆",
        "台海军事演习扩大，多国发布旅行警告，供应链面临中断风险",
    ]
    print("=== 宏观风险扫描 ===")
    r = macro_batch_scan(test_news)
    print(json.dumps(r, ensure_ascii=False, indent=2))

    # 测试左侧支撑 (用模拟数据)
    np.random.seed(42)
    n = 200
    trend = np.linspace(40, 55, n) + np.random.randn(n) * 2
    trend[-30:] = 56 - np.arange(30) * 0.3 + np.random.randn(30) * 1.5  # 回踩
    h = trend + np.abs(np.random.randn(n)) * 1.5
    l = trend - np.abs(np.random.randn(n)) * 1.5
    v = np.random.randint(10000, 50000, n)

    print("\n=== 左侧支撑扫描 ===")
    r2 = left_side_scan(trend, h, l, v)
    print(json.dumps({k: v for k, v in r2.items() if k != "supports"}, ensure_ascii=False, indent=2, default=str))

    print("\n=== 信号衰减 ===")
    sigs = [
        {"day": 90, "type": "golden_cross", "score": 80},
        {"day": 95, "type": "divergence", "score": 60},
        {"day": 98, "type": "kline_pattern", "score": 70},
    ]
    decayed = apply_signal_decay(sigs, 100)
    for d in decayed:
        print(f"  {d['type']}: {d['score']} → decayed={d['decayed_score']} (weight={d['decay_weight']})")


# ══════════════════════════════════════════════════════════════════
# 7. V4.5经验因子 (吸收自 AStockV4-Systems)
#    基于20年47,267样本回测 — 准确率验证过的买卖规则
# ══════════════════════════════════════════════════════════════════

def v45_experience_score(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    volume: np.ndarray | None = None,
) -> dict:
    """
    V4.5经验因子综合评分 — 基于47,267样本回测的量化规则。

    核心发现:
      RSI55-65 + 跌幅10-6% → 准确率73.6% ⭐⭐⭐最强
      PSY>85 → 准确率34% ❌必须离场
      RSI45-55 + 涨幅>6% → 准确率36.8% ❌规避

    Returns:
        dict with: final_score, direction, confidence, buy_signals, avoid_signals, reasons
    """
    n = len(close)
    if n < 60:
        return {"final_score": 0, "direction": "数据不足", "confidence": 0,
                "buy_signals": [], "avoid_signals": [], "reasons": []}

    price = float(close[-1])

    # 计算所需指标
    # RSI14
    diff = np.diff(close[-15:], prepend=close[-15])
    up = np.maximum(diff, 0); dn = np.maximum(-diff, 0)
    avg_up = np.mean(up[-14:]); avg_dn = np.mean(dn[-14:])
    rsi14 = 100 - 100/(1 + avg_up/avg_dn) if avg_dn > 0 else 100

    # RSI6
    diff6 = np.diff(close[-7:], prepend=close[-7])
    up6 = np.maximum(diff6, 0); dn6 = np.maximum(-diff6, 0)
    avg_up6 = np.mean(up6[-6:]); avg_dn6 = np.mean(dn6[-6:])
    rsi6 = 100 - 100/(1 + avg_up6/avg_dn6) if avg_dn6 > 0 else 100

    # KDJ_J
    k, d, j = calc_kdj(high[-14:], low[-14:], close[-14:])  # reuse from earlier
    kdj_j = float(j[-1]) if len(j) > 0 else 50

    # 涨跌幅
    pct = (close[-1] / close[-2] - 1) * 100 if n >= 2 else 0  # 日涨幅
    pct5 = (close[-1] / close[-6] - 1) * 100 if n >= 6 else 0
    pct10 = (close[-1] / close[-11] - 1) * 100 if n >= 11 else 0
    pct60 = (close[-1] / close[-61] - 1) * 100 if n >= 61 else 0

    # 量比
    vr = 1.0
    if volume is not None and len(volume) >= 6:
        avg5 = np.mean(volume[-6:-1])
        vr = volume[-1] / avg5 if avg5 > 0 else 1.0

    # 威廉指标
    hh14 = np.max(high[-14:]); ll14 = np.min(low[-14:])
    williams_r = (hh14 - price) / (hh14 - ll14) * -100 if hh14 > ll14 else -50

    # PSY 心理线 (12日上涨天数比例)
    psy = 0
    if n >= 13:
        up_days = sum(1 for i in range(-12, 0) if close[i] > close[i-1])
        psy = up_days / 12 * 100

    # 布林带位置
    ma20 = np.mean(close[-20:]); std20 = np.std(close[-20:])
    boll_upper = ma20 + 2*std20; boll_lower = ma20 - 2*std20
    boll_pos = (price - boll_lower) / (boll_upper - boll_lower) if boll_upper > boll_lower else 0.5

    # 价格/MA60
    ma60 = np.mean(close[-60:]) if n >= 60 else price
    price_ma60 = price / ma60 if ma60 > 0 else 1.0

    # ═══ 买入信号 (17条，回测验证) ═══
    score = 0; reasons = []; buy_signals = []; avoid_signals = []

    # 信号1: RSI55-65 + 跌幅10-6% → 准确率73.6% ⭐⭐⭐
    if 55 <= rsi14 <= 65 and -10 <= pct < -6:
        score += 20; reasons.append("RSI55-65+跌幅10-6%[73.6%]"); buy_signals.append(('STRONG_BUY', 20))

    # 信号2: RSI<25 + 跌幅10-6% → 62.8%
    elif rsi14 < 25 and -10 <= pct < -6:
        score += 15; reasons.append("RSI<25+跌幅10-6%[62.8%]"); buy_signals.append(('BUY', 15))

    # 信号3: RSI45-55 + 跌幅10-6% → 58.1%
    elif 45 <= rsi14 < 55 and -10 <= pct < -6:
        score += 14; reasons.append("RSI45-55+跌幅10-6%[58.1%]"); buy_signals.append(('BUY', 14))

    # 信号4: RSI25-35 + 跌幅10-6% → 58.1%
    elif 25 <= rsi14 < 35 and -10 <= pct < -6:
        score += 14; reasons.append("RSI25-35+跌幅10-6%[58.1%]"); buy_signals.append(('BUY', 14))

    # 信号5: RSI35-45 + 跌幅10-6% → 56.4%
    elif 35 <= rsi14 < 45 and -10 <= pct < -6:
        score += 13; reasons.append("RSI35-45+跌幅10-6%[56.4%]"); buy_signals.append(('BUY', 13))

    # 信号6: 10日跌幅20-15% → 60.6%
    if -20 <= pct10 < -15:
        score += 12; reasons.append("10日跌20-15%[60.6%]"); buy_signals.append(('BUY', 12))

    # 信号7: 10日跌幅<-20% → 58.4%
    if pct10 < -20:
        score += 11; reasons.append("10日跌>20%[58.4%]"); buy_signals.append(('BUY', 11))

    # 信号8: 10日跌幅15-10% → 55%
    if -15 <= pct10 < -10:
        score += 10; reasons.append("10日跌15-10%[55%]"); buy_signals.append(('BUY', 10))

    # 信号9: KDJ_J<0 + RSI<30 → 54.8%
    if kdj_j < 0 and rsi14 < 30:
        score += 10; reasons.append("KDJ_J<0+RSI<30双重超卖[54.8%]"); buy_signals.append(('BUY', 10))

    # 信号10: 布林下轨+RSI超卖 → 54.7%
    if boll_pos < 0.15 and rsi14 < 30:
        score += 9; reasons.append("布林下轨+RSI超卖[54.7%]"); buy_signals.append(('BUY', 9))

    # 信号11: 价格严重低于MA60 → 57.3%
    if price_ma60 < 0.7:
        score += 11; reasons.append("价/MA60<0.7[57.3%]"); buy_signals.append(('BUY', 11))
    elif 0.7 <= price_ma60 < 0.8:
        score += 8; reasons.append("价/MA60 0.7-0.8[55.5%]"); buy_signals.append(('BUY', 8))

    # 信号12: RSI6<20 → 53%
    if rsi6 < 20:
        score += 6; reasons.append("RSI6<20短期超卖"); buy_signals.append(('BUY', 6))

    # 信号13: 60日跌幅40-60% → 54.8%
    if -60 <= pct60 < -40:
        score += 8; reasons.append("60日跌40-60%[54.8%]"); buy_signals.append(('BUY', 8))

    # 信号14: RSI65-75+温和下跌 → 57.4%
    if 65 <= rsi14 <= 75 and -6 <= pct < -2:
        score += 10; reasons.append("RSI65-75+温和下跌[57.4%]"); buy_signals.append(('BUY', 10))

    # 信号15: RSI<25+反弹进行中 → 59.5%
    if rsi14 < 25 and 2 <= pct < 6:
        score += 12; reasons.append("RSI<25+反弹中[59.5%]"); buy_signals.append(('BUY', 12))

    # ═══ 辅助加分 ═══
    if williams_r < -80:
        score += 4; reasons.append("威廉极度超卖")
    if kdj_j < 0:
        score += 3; reasons.append("KDJ_J低位")
    if boll_pos < 0.1:
        score += 4; reasons.append("布林带下轨")

    # ═══ 规避信号 ═══
    avoid_score = 0

    # 规避1: PSY>85 → 准确率34% ❌❌
    if psy > 85:
        avoid_score += 18; avoid_signals.append("PSY>85极度乐观[准确率34%离场!]")

    # 规避2: RSI45-55+涨幅>6% → 36.8% ❌
    if 45 <= rsi14 <= 55 and pct > 6:
        avoid_score += 15; avoid_signals.append("RSI45-55+涨幅>6%[36.8%规避!]")

    # 规避3: RSI>75+涨幅>6% → 43.6%
    if rsi14 > 75 and pct > 6:
        avoid_score += 10; avoid_signals.append("RSI高位+涨幅过大[43.6%]")

    # 规避4: KDJ_J>100 → 43.8%
    if kdj_j > 100:
        avoid_score += 8; avoid_signals.append("KDJ_J>100高位钝化")

    # 规避5: 布林上轨+RSI高位
    if boll_pos > 0.9 and rsi14 > 65:
        avoid_score += 7; avoid_signals.append("布林上轨+RSI高位")

    # 规避6: PSY>75
    if psy > 75 and psy <= 85:
        avoid_score += 5; avoid_signals.append("PSY>75过度乐观")

    final_score = score - avoid_score
    all_reasons = reasons + avoid_signals

    # 置信度
    if abs(final_score) >= 20: confidence = 0.85
    elif abs(final_score) >= 15: confidence = 0.75
    elif abs(final_score) >= 10: confidence = 0.65
    elif abs(final_score) >= 5: confidence = 0.55
    else: confidence = 0.50

    # 方向
    if final_score >= 15: direction = '强烈推荐'
    elif final_score >= 8: direction = '谨慎推荐'
    elif final_score <= -10: direction = '强烈规避'
    elif final_score <= -5: direction = '建议规避'
    else: direction = '观望'

    return {
        "final_score": final_score, "direction": direction,
        "confidence": confidence, "buy_signals": buy_signals,
        "avoid_signals": avoid_signals, "reasons": all_reasons,
        "rsi14": round(rsi14, 1), "rsi6": round(rsi6, 1),
        "kdj_j": round(kdj_j, 1), "psy": round(psy, 0),
        "williams_r": round(williams_r, 1), "boll_pos": round(boll_pos, 2),
        "price_ma60": round(price_ma60, 2), "vr": round(vr, 2),
        "pct": round(pct, 1), "pct5": round(pct5, 1),
        "pct10": round(pct10, 1), "pct60": round(pct60, 1),
    }


# ══════════════════════════════════════════════════════════════════
# 8. G/Z/K/S打分模型 (吸收自 stock_scorer — fishpj)
#    六大依据加权 → 0~10总分，市场环境自适应权重
# ══════════════════════════════════════════════════════════════════

def gzk_score(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    volume: np.ndarray | None = None,
    pe: float | None = None,
    pb: float | None = None,
    revenue_yoy: float | None = None,
    profit_yoy: float | None = None,
    circ_mv_yi: float | None = None,
    turnover_pct: float | None = None,
    market_regime: str = "neutral",
) -> dict:
    """
    G/Z/K/S四维打分 — 股票涨跌理论翻译为量化信号。

    六大依据(每项0~2分):
      Z1 业绩向好性: 营收/净利同比增长
      Z2 同质同价: PE估值水平
      Z3 形态的大概率: MA趋势+超涨超跌检测
      Z4 市场关注度(G): 换手率反映关注度
      Z5 最大可卖量(S): 流通市值反映流动性
      Z6 特定情境记忆: 外部信号(暂0)

    权重按市场环境自适应:
      neutral: 业绩30% + 同价15% + 形态20% + 关注10% + 可卖5% + 记忆20%
      bull: 形态35% + 关注20% + 其它分散
      bear: 业绩40% + 同价20% + 防御为主

    Returns:
        dict with total(0~10), sub_scores, advice, k_ratio, timing
    """
    n = len(close)
    price = float(close[-1])

    # ── Z1 业绩向好性 ──
    z1 = 0
    z1_note = ""
    if revenue_yoy is not None and revenue_yoy >= 0.20:
        z1 += 1
        z1_note += f"营收+{revenue_yoy*100:.0f}% "
    if profit_yoy is not None and profit_yoy >= 0.30:
        z1 += 1
        z1_note += f"净利+{profit_yoy*100:.0f}% "
    z1 = min(z1, 2)
    if not z1_note:
        z1_note = "数据不足"

    # ── Z2 同质同价 ──
    z2 = 0
    z2_note = ""
    if pe is not None and pe > 0:
        if pe < 15:
            z2 = 2; z2_note = f"PE={pe:.1f} 偏低"
        elif pe < 25:
            z2 = 1; z2_note = f"PE={pe:.1f} 中等"
        elif pe > 60:
            z2 = 0; z2_note = f"PE={pe:.1f} 偏高"
        else:
            z2 = 1; z2_note = f"PE={pe:.1f} 正常"
    else:
        z2_note = "PE数据缺失"

    # ── Z3 形态的大概率 ──
    z3 = 0; trend = "中性"; dev = "中性"; ret_20d = 0.0
    if n >= 60:
        ma5 = np.mean(close[-5:])
        ma20 = np.mean(close[-20:])
        ma60 = np.mean(close[-60:])
        ret_20d = (price / close[-21] - 1) if n >= 21 else 0
        if ma5 > ma20 > ma60:
            trend = "走强"; z3 += 1
        elif ma5 < ma20 < ma60:
            trend = "走弱"
        if ret_20d > 0.30:
            dev = "超涨"
        elif ret_20d < -0.20:
            dev = "超跌"; z3 += 1
        z3 = min(z3, 2)

    # ── Z4 市场关注度 (G) ──
    z4 = 0; g_note = ""
    if turnover_pct is not None:
        if turnover_pct > 5:
            z4 = 2; g_note = f"换手{turnover_pct:.1f}%(高关注)"
        elif turnover_pct > 2:
            z4 = 1; g_note = f"换手{turnover_pct:.1f}%"
        else:
            g_note = f"换手{turnover_pct:.1f}%(低关注)"
    else:
        g_note = "换手率缺失"

    # ── Z5 最大可卖量 (S) ──
    z5 = 0; s_note = ""
    if circ_mv_yi is not None:
        if circ_mv_yi < 80:
            z5 = 2; s_note = f"流通{circ_mv_yi:.0f}亿(小盘)"
        elif circ_mv_yi < 200:
            z5 = 1; s_note = f"流通{circ_mv_yi:.0f}亿"
        else:
            s_note = f"流通{circ_mv_yi:.0f}亿(大盘)"
    else:
        s_note = "缺失"

    # ── Z6 特定情境记忆 ──
    z6 = 0; z6_note = "无匹配"

    # ── K 盈亏比(自适应阻力) ──
    k_ratio = None; k_note = ""
    if n >= 20:
        ma20 = np.mean(close[-20:])
        low_5d = np.min(close[-5:])
        support = max(ma20, low_5d)
        lookback = min(n, 60)
        high_prev = np.max(close[-lookback:])

        if dev == "超涨":
            resistance = price * 1.10; res_label = "+10%(超涨保守)"
        elif trend == "走强" and high_prev > price:
            resistance = high_prev; res_label = "前高"
        else:
            resistance = ma20 * 1.30; res_label = "MA20×1.30"

        up = (resistance - price) / price if price > 0 else 0
        down = max((price - support) / price, 0.001)
        k_ratio = up / down
        k_note = f"支撑{support:.2f}|阻{res_label}{resistance:.2f}|上{up*100:.1f}%下{down*100:.1f}%"

    # ── R值方向信号(量比) ──
    amount_ratio = None; timing_ok = False
    if volume is not None and len(volume) >= 6:
        today_vol = volume[-1]
        avg5 = np.mean(volume[-6:-1])
        if avg5 > 0:
            amount_ratio = today_vol / avg5
            timing_ok = amount_ratio >= 1.5

    # ── 市场环境自适应权重 ──
    weights_map = {
        "neutral": {"业绩向好性": 0.30, "同质同价": 0.15, "形态的大概率": 0.20,
                     "市场关注度": 0.10, "最大可卖量": 0.05, "特定情境记忆": 0.20},
        "bull": {"业绩向好性": 0.15, "同质同价": 0.10, "形态的大概率": 0.35,
                  "市场关注度": 0.20, "最大可卖量": 0.10, "特定情境记忆": 0.10},
        "bear": {"业绩向好性": 0.40, "同质同价": 0.20, "形态的大概率": 0.10,
                  "市场关注度": 0.05, "最大可卖量": 0.05, "特定情境记忆": 0.20},
    }
    w = weights_map.get(market_regime, weights_map["neutral"])

    # ── Z3环境修正 ──
    z3_adj = z3
    if dev == "超涨":
        if ret_20d >= 0.50:
            z3_adj = -2  # 重超涨
        else:
            z3_adj = -1  # 普通超涨
    elif market_regime == "bull" and trend == "走强" and dev != "超涨":
        z3_adj = 2
    elif market_regime == "bear" and dev == "超跌":
        z3_adj = 2
    elif market_regime == "bear" and trend == "走弱":
        z3_adj = 1
    elif market_regime == "neutral":
        if trend == "走强" and dev != "超涨":
            z3_adj = 1
        elif dev == "超跌":
            z3_adj = 1

    # ── 合成总分(0~10) ──
    subs = [z1, z2, z3_adj, z4, z5, z6]
    labels = ["业绩向好性", "同质同价", "形态的大概率", "市场关注度", "最大可卖量", "特定情境记忆"]
    total = sum(subs[i] * w[labels[i]] for i in range(6)) * 5

    # K甜点奖励
    if k_ratio is not None:
        if 0.5 <= k_ratio <= 1.5:
            total += 0.5
        elif k_ratio < 0.3:
            total -= 1.0
    total = max(0, min(10, total))

    # Tiebreaker: 量比
    tiebreak = 0.0
    if amount_ratio is not None:
        tiebreak += min(max(amount_ratio, 0), 3.0) * 0.01

    # ── 建议 ──
    if total >= 5.5 and timing_ok:
        tag = "（高分警惕追涨）" if total >= 6.5 else ""
        advice = f"可建仓（择时已满足）{tag}".strip()
    elif total >= 5.5:
        tag = "（高分警惕追涨）" if total >= 6.5 else ""
        advice = f"进入候选（等待择时）{tag}".strip()
    else:
        advice = "暂不关注"

    return {
        "total": round(total + tiebreak, 2),
        "total_raw": round(total, 2),
        "advice": advice,
        "sub_scores": dict(zip(labels, subs)),
        "z3_raw": z3, "z3_adjusted": z3_adj,
        "trend": trend, "deviation": dev, "ret_20d": round(ret_20d, 4),
        "k_ratio": round(k_ratio, 2) if k_ratio else None,
        "k_note": k_note,
        "amount_ratio": round(amount_ratio, 2) if amount_ratio else None,
        "timing_ok": timing_ok,
        "regime": market_regime,
        "weights": {k: round(v*100, 1) for k, v in w.items()},
    }


# ══════════════════════════════════════════════════════════════════
# 9. 连板辨识度因子 (吸收自 a-share-quant-sim — fkchaos)
#    A股独有的"股性记忆"：历史连板越多+越近 → 二次启动概率越高
# ══════════════════════════════════════════════════════════════════

def streak_factor(
    close: np.ndarray,
    open_: np.ndarray | None = None,
    decay_days: int = 252,
    limit_pct: float = 0.095,
    min_streak: int = 2,
) -> dict:
    """
    连板辨识度因子 — 历史连板次数×时间衰减。

    逻辑:
      - 检测涨停: (close/open - 1) >= limit_pct (默认9.5%, 含科创板20%)
      - 统计连续涨停天数, 只记录≥min_streak(默认2板)的连板
      - 距离当前越近的连板, 权重越高: exp(-3.0 × days_since / decay_days)
      - 最终得分 = Σ(连板长度 × 衰减权重)

    Args:
        close, open_: 日线序列(open_=None时用close推算)
        decay_days: 衰减窗口(默认252天)
        limit_pct: 涨停阈值(默认9.5%)
        min_streak: 最小连板天数

    Returns:
        dict: score(连板辨识度分), raw_score, streaks(连板记录), risk(近期风险)
    """
    n = len(close)
    if n < 20:
        return {"score": 0.0, "raw_score": 0.0, "streaks": [], "risk": False}

    # 计算日涨幅
    if open_ is not None and len(open_) == n:
        rets = np.zeros(n)
        for i in range(1, n):
            rets[i] = (close[i] / open_[i] - 1) if open_[i] > 0 else 0
    else:
        rets = np.zeros(n)
        for i in range(1, n):
            rets[i] = (close[i] / close[i-1] - 1) if close[i-1] > 0 else 0

    limit_up = rets >= limit_pct

    # 找连板
    streaks = []  # [(length, end_idx), ...]
    current = 0
    for i in range(len(limit_up)):
        if limit_up[i]:
            current += 1
        else:
            if current >= min_streak:
                streaks.append((current, i))
            current = 0
    if current >= min_streak:
        streaks.append((current, len(limit_up) - 1))

    if not streaks:
        return {"score": 0.0, "raw_score": 0.0, "streaks": [], "risk": False}

    # 计算加权得分
    last_idx = len(limit_up) - 1
    raw_score = 0.0
    streak_details = []
    for length, end_idx in streaks:
        days_since = last_idx - end_idx
        decay = np.exp(-3.0 * days_since / decay_days)
        raw_score += length * decay
        streak_details.append({"length": length, "days_ago": days_since, "decay": round(decay, 3)})

    # 风险检测: 60天内是否有2+连板
    recent_cutoff = last_idx - 60
    risk = any(s[1] >= recent_cutoff for s in streaks)

    return {
        "score": round(raw_score, 3),
        "raw_score": round(raw_score, 3),
        "streaks": streak_details,
        "risk": risk,
        "max_streak": max(s[0] for s in streaks) if streaks else 0,
    }


# ══════════════════════════════════════════════════════════════════
# 10. 主线识别 (吸收自 cxdata-mainline-analysis-agent)
#     四维综合评分 = 涨幅排名30% + 涨停集中度30% + 周趋势20% + 月趋势20%
# ══════════════════════════════════════════════════════════════════

def mainline_score(
    day_change_pct: float,
    limit_up_count: int,
    total_stocks_in_sector: int,
    week_change_pct: float,
    month_change_pct: float,
) -> dict:
    """
    板块主线综合评分 — 四维度(0~100)。

    公式: 日涨幅排名分(30%) + 涨停集中度(30%) + 周涨幅趋势(20%) + 月涨幅趋势(20%)
    来源: cxdata-mainline-analysis-agent v3.1

    Args:
        day_change_pct: 板块日涨跌幅(%)
        limit_up_count: 板块内涨停股数
        total_stocks_in_sector: 板块总股数
        week_change_pct: 板块周涨跌幅(%)
        month_change_pct: 板块月涨跌幅(%)

    Returns:
        dict: composite_score, line_type, emotion_phase
    """
    # 日涨幅排名分(0-30): 涨幅越大分越高
    day_score = min(30, max(0, (day_change_pct + 3) * 3))  # -3%=0, +7%=30

    # 涨停集中度(0-30): 涨停股占比越高分越高
    if total_stocks_in_sector > 0:
        ratio = limit_up_count / total_stocks_in_sector
        concentration_score = min(30, ratio * 300)  # 10%=30分
    else:
        concentration_score = 0

    # 周涨幅趋势(0-20)
    week_score = min(20, max(0, (week_change_pct + 5) * 2))

    # 月涨幅趋势(0-20)
    month_score = min(20, max(0, (month_change_pct + 10) * 1))

    composite = day_score + concentration_score + week_score + month_score

    # 主线类型
    if composite >= 70:
        line_type = "核心主线"
    elif composite >= 50:
        line_type = "次级主线"
    elif composite >= 30:
        line_type = "次级热点"
    else:
        line_type = "弱方向"

    # 资金属性: 涨停集中度>15分=资金攻击型, 否则趋势防御型
    fund_type = "资金攻击型" if concentration_score >= 15 else "趋势防御型"

    # 情绪周期: 基于composite_score
    if composite >= 80:
        phase = "高潮"
    elif composite >= 60:
        phase = "主升"
    elif composite >= 40:
        phase = "修复"
    elif composite >= 20:
        phase = "调整"
    else:
        phase = "冰点"

    return {
        "composite_score": round(composite, 1),
        "day_score": round(day_score, 1),
        "concentration_score": round(concentration_score, 1),
        "week_score": round(week_score, 1),
        "month_score": round(month_score, 1),
        "line_type": line_type,
        "fund_type": fund_type,
        "emotion_phase": phase,
    }


# ══════════════════════════════════════════════════════════════════
# 11. K线形态识别 (吸收自 Sequoia-X — sngyai)
#     高旗形/涨停洗盘/海龟突破 → 与缠论互补: 缠论看位置, 形态看时机
# ══════════════════════════════════════════════════════════════════

def high_tight_flag_signal(
    close: np.ndarray, high: np.ndarray, low: np.ndarray,
    volume: np.ndarray,
    momentum_window: int = 40, consolidate_window: int = 10,
    momentum_ratio: float = 1.6, consolidate_ratio: float = 1.15,
    volume_shrink: float = 0.6,
) -> dict:
    """
    高旗形整理 — 强动量后极度收敛缩量。

    条件:
      1. 过去40日最高/最低 > 1.6（涨幅>60%）
      2. 最近10日最高/最低 < 1.15（振幅<15%，极度收敛）
      3. 高位抗跌: 10日最低 ≥ 40日最高×0.8
      4. 缩量: 今日量 < 20日均量×0.6

    Returns: {hit, score(0~1), details}
    """
    n = len(close)
    if n < 40:
        return {"hit": False, "score": 0.0, "reason": f"K线不足40根"}

    h40 = np.max(high[-40:]); l40 = np.min(low[-40:])
    h10 = np.max(high[-10:]); l10 = np.min(low[-10:])

    momentum = h40 / l40 > momentum_ratio
    consolidate = h10 / l10 < consolidate_ratio
    high_level = l10 >= h40 * 0.8
    vol_ma20 = np.mean(volume[-21:-1]) if len(volume) >= 21 else np.mean(volume[-10:])
    shrink = volume[-1] < vol_ma20 * volume_shrink

    score = sum([momentum, consolidate, high_level, shrink]) / 4
    reasons = []
    if momentum: reasons.append(f"40日涨{((h40/l40-1)*100):.0f}%")
    if consolidate: reasons.append(f"10日收敛{(h10/l10-1)*100:.1f}%")
    if high_level: reasons.append("高位抗跌")
    if shrink: reasons.append(f"缩量(量/均量={volume[-1]/vol_ma20:.1f})")

    return {
        "hit": momentum and consolidate and high_level and shrink,
        "score": round(score, 2),
        "reasons": reasons,
        "momentum_pct": round((h40/l40-1)*100, 1),
        "consolidate_pct": round((h10/l10-1)*100, 1),
    }


def shakeout_signal(
    close: np.ndarray, open_: np.ndarray,
    high: np.ndarray, low: np.ndarray, volume: np.ndarray,
) -> dict:
    """
    涨停洗盘 — 昨日涨停后今日放量收阴但不破昨收。

    条件:
      1. 昨日涨停: 昨收 ≥ 前收×1.095
      2. 今日收阴: 今收 < 今开
      3. 今日放量: 今量 > 昨量×2
      4. 支撑不破: 今低 ≥ 昨收

    Returns: {hit, score(0~1), details}
    """
    n = len(close)
    if n < 3:
        return {"hit": False, "score": 0.0, "reason": "K线不足3根"}

    prev2_c = close[-3]; prev1_c = close[-2]; today_c = close[-1]
    today_o = open_[-1]; today_l = low[-1]; today_v = volume[-1]; prev1_v = volume[-2]

    limit_up = prev1_c >= prev2_c * 1.095
    bearish = today_c < today_o
    volume_surge = today_v > prev1_v * 2.0
    support_hold = today_l >= prev1_c

    score = sum([limit_up, bearish, volume_surge, support_hold]) / 4
    reasons = []
    if limit_up: reasons.append(f"昨涨停(涨{(prev1_c/prev2_c-1)*100:.1f}%)")
    if bearish: reasons.append("今收阴")
    if volume_surge: reasons.append(f"放量(today/prev={today_v/prev1_v:.1f}x)")
    if support_hold: reasons.append("支撑不破")

    return {
        "hit": limit_up and bearish and volume_surge and support_hold,
        "score": round(score, 2),
        "reasons": reasons,
        "yesterday_gain_pct": round((prev1_c/prev2_c-1)*100, 1),
        "volume_ratio": round(today_v/prev1_v, 1),
    }


def turtle_breakout_signal(
    close: np.ndarray, high: np.ndarray,
    open_: np.ndarray, volume: np.ndarray,
    breakout_window: int = 20,
    min_turnover_yi: float = 1.0,
) -> dict:
    """
    海龟突破 — 20日新高+成交额过亿+实阳确认。

    条件:
      1. 突破: 今收 > 前20日最高
      2. 流动性: 成交额 > 1亿（需要外部传入）
      3. 实阳: 今收 > 今开（实体阳线）
      4. 真涨: 今收 > 昨收（非假阳线）

    Returns: {hit, score(0~1), details}
    """
    n = len(close)
    if n < breakout_window + 1:
        return {"hit": False, "score": 0.0, "reason": f"K线不足{breakout_window+1}根"}

    high_20 = np.max(high[-(breakout_window+1):-1])  # 前20日最高(不含今日)
    breakout = close[-1] > high_20
    is_yang = close[-1] > open_[-1]
    is_up = close[-1] > close[-2]

    score = sum([breakout, is_yang, is_up]) / 3

    reasons = []
    if breakout: reasons.append(f"突破20日高{high_20:.2f}")
    if is_yang: reasons.append("实体阳线")
    if is_up: reasons.append(f"真涨+{(close[-1]/close[-2]-1)*100:.1f}%")

    return {
        "hit": breakout and is_yang and is_up,
        "score": round(score, 2),
        "reasons": reasons,
        "breakout_pct": round((close[-1]/high_20-1)*100, 2) if high_20 > 0 else 0,
        "high_20": round(high_20, 2),
    }


def all_kline_patterns(
    close: np.ndarray, open_: np.ndarray,
    high: np.ndarray, low: np.ndarray, volume: np.ndarray,
) -> dict:
    """一键检测所有K线形态"""
    return {
        "high_tight_flag": high_tight_flag_signal(close, high, low, volume),
        "shakeout": shakeout_signal(close, open_, high, low, volume),
        "turtle_breakout": turtle_breakout_signal(close, high, open_, volume),
    }


# ============================================================================
# Module 12: 北向资金 (Northbound Capital Flow)
# 来源: 东财 datacenter → http://push2.eastmoney.com/api/qt/kamt.kline/get
# 用途: 判断外资动向对沪深300的影响
# ============================================================================

def get_northbound_flow(days: int = 5) -> dict:
    """
    获取北向资金近N日净流入（亿元）。
    返回: {"net_flow": 累计(亿), "trend": "流入"|"流出"|"平衡", "daily": [{日期,net},...]}
    """
    import urllib.request
    import json
    import os
    
    # 东财是国内API，不走socks5代理
    for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
        os.environ.pop(k, None)
    
    url = (
        "http://push2.eastmoney.com/api/qt/kamt.kline/get?"
        "fields1=f1,f2,f3,f4&fields2=f51,f52&klt=101&lmt=%d" % days
    )
    try:
        r = urllib.request.urlopen(
            urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "http://data.eastmoney.com/"
            }), timeout=5
        )
        data = json.loads(r.read())
        if not data or not data.get("data"):
            return {"net_flow": 0, "trend": "无数据", "daily": []}
        
        d = data["data"]
        # 北向 = hk2sh(沪股通) + hk2sz(深股通)
        north = {}
        for lst in [d.get("hk2sh", []), d.get("hk2sz", [])]:
            if lst:
                for item in lst[-days:]:
                    parts = item.split(",")
                    if len(parts) >= 2:
                        try:
                            dt = parts[0]
                            net = float(parts[1]) / 100000000  # 转亿
                            north[dt] = north.get(dt, 0) + net
                        except:
                            pass
        
        daily = [{"date": k, "net": round(v, 2)} for k, v in sorted(north.items())[-days:]]
        total_net = round(sum(v for _, v in north.items()), 2)
        
        trend = "流入" if total_net > 10 else ("流出" if total_net < -10 else "平衡")
        return {"net_flow": round(total_net, 2), "trend": trend, "daily": daily}
    except Exception as e:
        return {"net_flow": 0, "trend": "获取失败", "daily": [], "error": str(e)}


# ============================================================================
# Module 13: K线多源回退 (Multi-source K-line fallback)
# 备选: mootdx(通达信) → baidu → 腾讯 — 当 baostock 不可用时自动切换
# ============================================================================

def fetch_kline_fallback(code: str, start: str = "2025-07-01", 
                          end: str = "2026-07-10", freq: str = "d",
                          adjust: str = "qfq") -> list:
    """
    多源K线回退: 先用 baostock，失败则切换 mootdx/腾讯。
    返回: [dict(date,open,high,low,close,volume),...] 或空列表
    """
    import subprocess as sp, json
    
    # Source 1: baostock (already handled in scan, this is a fallback)
    # Source 2: mootdx (通达信，不封IP)
    try:
        import mootdx.quotes as mq
        client = mq.standard.Standard()
        # mootdx 需要深圳/上海代码格式
        market = 0 if code.startswith("6") else 1  # 0=深圳 1=上海
        # 映射频率
        period_map = {"d": 9, "w": 5, "m": 6, "60": 3, "30": 2, "15": 1, "5": 0}
        period = period_map.get(freq, 9)
        # 计算K线数量
        from datetime import datetime
        day_count = (datetime.strptime(end, "%Y-%m-%d") - datetime.strptime(start, "%Y-%m-%d")).days + 50
        df = client.index(market, code[2:], period) if code.startswith(("0", "3", "6")) else None
        if df is None or df.empty:
            raise Exception("mootdx no data")
        result = []
        for idx, row in df.iterrows():
            dt = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
            if start <= dt <= end:
                result.append({"date": dt, "open": float(row["open"]), "high": float(row["high"]),
                              "low": float(row["low"]), "close": float(row["close"]),
                              "volume": float(row.get("vol", 0))})
        if result:
            return result
    except Exception:
        pass
    
    # Source 3: 腾讯 (日线前复权)
    try:
        sym = f"{'sh' if code.startswith('6') else 'sz'}{code}"
        url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,{start},,500,qfq"
        r = sp.run(["curl", "-sL", "--max-time", "8", url], stdout=sp.PIPE)
        data = json.loads(r.stdout)
        klines = data.get("data", {}).get(sym, {}).get("qfqday", []) or \
                 data.get("data", {}).get(sym, {}).get("day", [])
        result = []
        for k in klines:
            dt = k[0]
            if start <= dt <= end:
                result.append({"date": dt, "open": float(k[1]), "high": float(k[3]),
                              "low": float(k[4]), "close": float(k[2]),
                              "volume": float(k[5])})
        return result
    except Exception:
        return []


# ============================================================================
# Module 14: 三维综合评分 (Composite 3D Score)
# 来源: chanlun-quant/composite_scorer.py — 自包含，硬编码默认权重
# 用法: compute_3d_score(tech_score=XGB分, fund_score=基本面分, news_score=消息面分)
# ============================================================================

# 默认权重与阈值
_W_TECH = 0.40   # 技术面 40%
_W_FUND = 0.30   # 基本面 30%
_W_NEWS = 0.30   # 消息面 30%
_TECH_BUY = 40   # 技术面 < 40 → 不建仓（校准后：新旧模型40+为有效信号）
_FUND_HEAVY = 55 # 基本面 ≥ 55 → 可重仓
_FUND_LIGHT = 30 # 基本面 < 30 → 仅轻仓
_COMP_A = 65     # 综合 ≥ 65 → A级
_COMP_B = 50     # 综合 ≥ 50 → B级
_COMP_C = 35     # 综合 ≥ 35 → C级


def compute_3d_score(tech_score: float, fund_score: float = 50,
                     news_score: float = 50, w_tech: float = _W_TECH,
                     w_fund: float = _W_FUND, w_news: float = _W_NEWS) -> dict:
    """
    三维综合评分 [0,100]。
    输入: 技术分(XGB) + 基本面分(GZK/V4.5) + 消息面分(默认中性)
    返回: {composite, grade, position, can_buy, reason}
    """
    tech_norm = max(0, min(100, tech_score))
    composite = tech_norm * w_tech + fund_score * w_fund + news_score * w_news

    # 共振惩罚
    if tech_norm < 60 and fund_score < 60:
        penalty = max(0, 60 - tech_norm) * w_tech + max(0, 60 - fund_score) * w_fund
        composite += penalty * 0.5

    composite = max(0, min(100, composite))

    if composite >= _COMP_A: grade = 'A'
    elif composite >= _COMP_B: grade = 'B'
    elif composite >= _COMP_C: grade = 'C'
    else: grade = 'D'

    can_buy = tech_norm >= _TECH_BUY
    if not can_buy: position = 0
    elif fund_score >= _FUND_HEAVY and grade == 'A': position = 0.50
    elif fund_score >= _FUND_HEAVY: position = 0.30
    elif fund_score >= _FUND_LIGHT: position = 0.20 if grade in ('A', 'B') else 0.10
    else: position = 0.10

    grade_map = {'A': '推荐重仓', 'B': '可买入', 'C': '观望', 'D': '回避'}
    return {
        'composite': round(composite, 1), 'grade': grade, 'position': position,
        'can_buy': can_buy, 'reason': grade_map.get(grade, '?'),
        'tech': tech_norm, 'fund': fund_score, 'news': news_score
    }


# ============================================================================
# Module 15: 风控过滤器 (Risk Filter)
# 来源: chanlun-quant/risk_filter.py — 自包含，零外部依赖
# 用法: check_risk(code, name) → (blocked, reasons)
# ============================================================================

def check_risk(code: str, name: str) -> tuple:
    """
    基础风控检查（不含AKShare依赖）:
    1. ST股检测  2. 人工黑名单(可扩展)
    返回: (is_blocked: bool, reasons: list)
    """
    reasons = []
    if 'ST' in name.upper() or '*ST' in name.upper():
        reasons.append('ST股')
        return True, reasons
    return len(reasons) > 0, reasons


# ============================================================================
# Module 16: MACD背驰辅助 (Divergence Helper)
# 来源: yanwuyou/chanlun-stock-analyzer/chan_lib/dynamics.py 背驰6条件精简版
# 用途: B中枢MACD回0轴检查 + 力度面积对比
# ============================================================================

def check_macd_divergence(close: 'np.ndarray', high: 'np.ndarray', low: 'np.ndarray',
                          b_start: int, b_end: int, c_start: int, c_end: int,
                          direction: str = 'up') -> dict:
    """
    MACD背驰检查（条件5+条件6）:
    - 条件5: B中枢是否将MACD黄白线拉回0轴附近
    - 条件6: c段MACD面积 < b段面积 且黄白线不创新高/低
    返回: {has_divergence, b_near_zero, area_divergence, diff_divergence}
    """
    import numpy as np
    
    # Compute MACD
    ema_fast = np.zeros_like(close)
    ema_slow = np.zeros_like(close)
    alpha_f = 2.0 / 13
    alpha_s = 2.0 / 27
    ema_fast[0] = close[0]
    ema_slow[0] = close[0]
    for i in range(1, len(close)):
        ema_fast[i] = close[i] * alpha_f + ema_fast[i-1] * (1 - alpha_f)
        ema_slow[i] = close[i] * alpha_s + ema_slow[i-1] * (1 - alpha_s)
    
    diff = ema_fast - ema_slow
    alpha_d = 2.0 / 10
    dea = np.zeros_like(diff)
    dea[0] = diff[0]
    for i in range(1, len(diff)):
        dea[i] = diff[i] * alpha_d + dea[i-1] * (1 - alpha_d)
    macd_hist = 2 * (diff - dea)
    
    # Condition 5: B zone near 0 axis
    b_diff = diff[b_start:min(b_end+1, len(diff))]
    b_max_abs = max(abs(b_diff.max()), abs(b_diff.min()))
    b_near_zero = b_max_abs < np.std(diff) * 1.5
    
    # Condition 6: area comparison
    b_hist = np.abs(macd_hist[b_start:min(b_end+1, len(macd_hist))])
    c_hist = np.abs(macd_hist[c_start:min(c_end+1, len(macd_hist))])
    b_area = float(np.trapz(b_hist) if len(b_hist) > 1 else b_hist.sum())
    c_area = float(np.trapz(c_hist) if len(c_hist) > 1 else c_hist.sum())
    area_divergence = c_area < b_area
    
    # DIF comparison
    if direction == 'up':
        b_diff_max = float(diff[b_start:min(b_end+1, len(diff))].max())
        c_diff_max = float(diff[c_start:min(c_end+1, len(diff))].max())
        diff_divergence = c_diff_max < b_diff_max
    else:
        b_diff_min = float(diff[b_start:min(b_end+1, len(diff))].min())
        c_diff_min = float(diff[c_start:min(c_end+1, len(diff))].min())
        diff_divergence = c_diff_min > b_diff_min
    
    has_div = (area_divergence or diff_divergence) and b_near_zero
    
    return {
        'has_divergence': bool(has_div),
        'b_near_zero': bool(b_near_zero),
        'area_divergence': bool(area_divergence),
        'diff_divergence': bool(diff_divergence),
        'b_area': round(b_area, 1), 'c_area': round(c_area, 1),
    }


# ============================================================================
# Module 17: 风控计划 (Risk Planner)
# 来源: chanlun-trade-signal/app/risk/planner.py — 止损/仓位/入场区规则
# 用法: build_risk_plan(signal_strength, signal, price, support, resistance)
# ============================================================================

def build_risk_plan(signal_strength: float, signal: str, latest_price: float,
                    supports: list = None, resistances: list = None,
                    max_leverage: int = 3, risk_per_trade: float = 0.01) -> dict:
    """
    根据缠论信号生成风控计划。
    signal_strength: 0-1 信号强度
    signal: "buy" / "sell" / "center_observe" / "neutral"
    supports: 最近支撑位列表 [底分型价格, 中枢下沿, ...]
    resistances: 最近压力位列表 [顶分型价格, 中枢上沿, ...]
    """
    supports = supports or []
    resistances = resistances or []
    
    # 信号不足 → 只观察
    if signal_strength < 0.5 or signal in ("neutral", "center_observe"):
        return {
            "action": "watch", "risk_level": "low",
            "entry_zone": (latest_price, latest_price),
            "stop_loss": latest_price,
            "leverage": 1,
            "reason": "信号不足，等待中枢突破或BSP信号确认"
        }
    
    buffer = max(latest_price * 0.0035, latest_price * risk_per_trade * 0.35)
    leverage = max(1, min(max_leverage, int(signal_strength * 5)))
    
    if "buy" in signal or signal == "bullish":
        # 止损 = 最近支撑（中枢下沿或底分型最低）
        stop = min(supports[-3:]) if supports else latest_price - buffer * 2
        stop = min(stop, latest_price - buffer)
        entry_low = max(stop + buffer, latest_price * 0.996)
        entry_high = latest_price * 1.004
        risk = (latest_price - stop) / latest_price * 100
        return {
            "action": "watch_long", "risk_level": "medium" if signal_strength < 0.8 else "high",
            "entry_zone": (round(entry_low, 2), round(entry_high, 2)),
            "stop_loss": round(stop, 2), "stop_pct": round(risk, 1),
            "leverage": min(leverage, 3),
            "reason": f"多头信号，止损设在{round(stop,2)}(-{round(risk,1)}%)"
        }
    
    # 空头信号
    resistance = max(resistances[-3:]) if resistances else latest_price + buffer * 2
    resistance = max(resistance, latest_price + buffer)
    entry_low = latest_price * 0.996
    entry_high = min(resistance - buffer, latest_price * 1.004)
    risk = (resistance - latest_price) / latest_price * 100
    return {
        "action": "watch_short", "risk_level": "medium" if signal_strength < 0.8 else "high",
        "entry_zone": (round(entry_low, 2), round(entry_high, 2)),
        "stop_loss": round(resistance, 2), "stop_pct": round(risk, 1),
        "leverage": min(leverage, 3),
        "reason": f"空头信号，止损设在{round(resistance,2)}(+{round(risk,1)}%)"
    }
