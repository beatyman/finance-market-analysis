#!/usr/bin/env python3
"""
SMC/ICT 聪明钱分析模块 — 严格按 cn_stock_scan 原始实现移植

来源: https://github.com/Allanli1011/cn_stock_scan

与原始仓库保持一致:
  - 相同的评分体系: MACD(1.0/0.5) + ThreePush(1.0) + PDA(1.0/0.5) = max 3.0
  - 相同的R3规则(DIF回调逼近零轴)
  - 相同的config参数
  - ≥2.5 = "三重共振"最强信号

使用:
  from smc_ict import scan_one, scan_all
  result = scan_one(high, low, open_, close, direction='bottom')
  # result['score']: 0.0~3.0
  # result['trade_plan']: 入场/止损/目标/R:R
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field, replace
from typing import Literal, Optional

# ══════════════════════════════════════════════════════════════════
# Config — 与原始 config.yaml 一致
# ══════════════════════════════════════════════════════════════════

CONFIG = {
    "macd": {"fast": 12, "slow": 26, "signal": 9},
    "divergence": {
        "min_area_reduction": 0.10,
        "dif_zero_tolerance": 0.0,
        "dif_approach_zero_ratio": 0.50,
        "min_price_increase_pct": 0.001,
        "recency_bars": 30,
    },
    "swing": {"pct_threshold": 0.03},
    "ob_fvg": {
        "ob_displacement_atr": 2.0,
        "fvg_min_size_atr": 0.3,
        "atr_period": 14,
    },
    "three_push": {
        "pullback_target_pct": 0.75,
        "pullback_tolerance": 0.15,
    },
}

Direction = Literal["top", "bottom"]
Timeframe = Literal["W", "M"]


# ══════════════════════════════════════════════════════════════════
# 1. Swing Points (ZigZag) — 与原始 swing.py 一致
# ══════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class SwingPoint:
    idx: int
    kind: Literal["high", "low"]
    price: float
    confirmed: bool = True


def find_swing_points(
    high: np.ndarray, low: np.ndarray, close: np.ndarray,
    pct_threshold: float = 0.03, include_tentative_last: bool = True,
) -> list[SwingPoint]:
    """ZigZag摆点 — 与原始 swing.py 完全一致"""
    n = len(close)
    if n < 3:
        return []

    cand_idx, cand_close = 0, float(close[0])
    direction: Optional[str] = None
    swings: list[SwingPoint] = []

    for i in range(1, n):
        c = float(close[i])
        if direction is None:
            if c > cand_close * (1 + pct_threshold):
                direction = "up"
                swings.append(SwingPoint(cand_idx, "low", float(low[cand_idx])))
                cand_idx, cand_close = i, c
            elif c < cand_close * (1 - pct_threshold):
                direction = "down"
                swings.append(SwingPoint(cand_idx, "high", float(high[cand_idx])))
                cand_idx, cand_close = i, c
        elif direction == "up":
            if c > cand_close:
                cand_idx, cand_close = i, c
            elif c < cand_close * (1 - pct_threshold):
                swings.append(SwingPoint(cand_idx, "high", float(high[cand_idx])))
                direction, cand_idx, cand_close = "down", i, c
        else:
            if c < cand_close:
                cand_idx, cand_close = i, c
            elif c > cand_close * (1 + pct_threshold):
                swings.append(SwingPoint(cand_idx, "low", float(low[cand_idx])))
                direction, cand_idx, cand_close = "up", i, c

    if include_tentative_last and direction is not None:
        kind = "high" if direction == "up" else "low"
        price = float(high[cand_idx]) if kind == "high" else float(low[cand_idx])
        swings.append(SwingPoint(cand_idx, kind, price, confirmed=False))

    return swings


# ══════════════════════════════════════════════════════════════════
# 2. OB / FVG — 与原始 ob_fvg.py 一致
# ══════════════════════════════════════════════════════════════════

ZoneKind = Literal["ob", "fvg"]
ZoneDir = Literal["bullish", "bearish"]


@dataclass(frozen=True)
class Zone:
    kind: ZoneKind
    direction: ZoneDir
    formation_idx: int
    zone_high: float
    zone_low: float
    mitigated: bool = False
    invalidated: bool = False

    @property
    def mid(self) -> float:
        return (self.zone_high + self.zone_low) / 2

    def contains(self, price: float) -> bool:
        return self.zone_low <= price <= self.zone_high

    def overlaps(self, other: "Zone") -> bool:
        return not (self.zone_high < other.zone_low or self.zone_low > other.zone_high)


def _calc_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    atr = np.zeros(n)
    atr[period] = np.mean(tr[1:period + 1])
    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def find_order_blocks(
    high: np.ndarray, low: np.ndarray, open_: np.ndarray, close: np.ndarray,
    atr_period: int = 14, displacement_atr: float = 2.0, lookforward: int = 3,
) -> list[Zone]:
    """与原始 find_order_blocks 完全一致"""
    atr = _calc_atr(high, low, close, atr_period)
    n = len(close)
    obs: list[Zone] = []
    for i in range(atr_period, n - lookforward):
        if np.isnan(atr[i]) or atr[i] == 0:
            continue
        threshold = displacement_atr * atr[i]
        bl = float(close[i])
        fh = high[i + 1:i + 1 + lookforward]
        fl = low[i + 1:i + 1 + lookforward]
        if len(fh) and fh.max() - bl >= threshold and close[i] < open_[i]:
            obs.append(Zone("ob", "bullish", i, float(high[i]), float(low[i])))
        if len(fl) and bl - fl.min() >= threshold and close[i] > open_[i]:
            obs.append(Zone("ob", "bearish", i, float(high[i]), float(low[i])))
    return obs


def find_fvgs(
    high: np.ndarray, low: np.ndarray, close: np.ndarray,
    atr_period: int = 14, min_size_atr: float = 0.3,
) -> list[Zone]:
    """与原始 find_fvgs 完全一致"""
    atr = _calc_atr(high, low, close, atr_period)
    n = len(close)
    fvgs: list[Zone] = []
    for i in range(atr_period + 2, n):
        a = atr[i]
        if np.isnan(a) or a == 0:
            continue
        ms = min_size_atr * a
        k1h, k1l = high[i - 2], low[i - 2]
        k3h, k3l = high[i], low[i]
        if k1h < k3l and (k3l - k1h) >= ms:
            fvgs.append(Zone("fvg", "bullish", i - 1, float(k3l), float(k1h)))
        if k1l > k3h and (k1l - k3h) >= ms:
            fvgs.append(Zone("fvg", "bearish", i - 1, float(k1l), float(k3h)))
    return fvgs


def _zone_status(z: Zone, high: np.ndarray, low: np.ndarray, close: np.ndarray, end_idx: int) -> Zone:
    """与原始 _zone_status 完全一致"""
    if end_idx <= z.formation_idx:
        return z
    ah = high[z.formation_idx + 1:end_idx + 1]
    al = low[z.formation_idx + 1:end_idx + 1]
    ac = close[z.formation_idx + 1:end_idx + 1]
    if len(ah) == 0:
        return z
    touched = ((al <= z.zone_high) & (ah >= z.zone_low)).any()
    if z.direction == "bullish":
        broken = (ac < z.zone_low).any()
    else:
        broken = (ac > z.zone_high).any()
    return replace(z, mitigated=bool(touched), invalidated=bool(broken))


def find_active_zones(
    high: np.ndarray, low: np.ndarray, open_: np.ndarray, close: np.ndarray,
    end_idx: Optional[int] = None,
) -> list[Zone]:
    """与原始 find_active_zones 完全一致"""
    if end_idx is None:
        end_idx = len(close) - 1
    obs = find_order_blocks(high, low, open_, close)
    fvgs = find_fvgs(high, low, close)
    zones = obs + fvgs
    return [z for z in [_zone_status(z, high, low, close, end_idx) for z in zones] if not z.invalidated]


def find_overlap_zones(zones: list[Zone]) -> list[tuple[Zone, Zone]]:
    """与原始 find_overlap_zones 完全一致"""
    obs = [z for z in zones if z.kind == "ob"]
    fvgs = [z for z in zones if z.kind == "fvg"]
    return [(ob, fvg) for ob in obs for fvg in fvgs if ob.direction == fvg.direction and ob.overlaps(fvg)]


# ══════════════════════════════════════════════════════════════════
# 3. MACD Triple Divergence — 与原始 macd.py 完全一致
# ══════════════════════════════════════════════════════════════════


@dataclass
class MacdWave:
    direction: str
    start_cross_idx: int
    end_cross_idx: int
    cross_value: float
    extreme_idx: int
    extreme_price: float
    hist_area: float


@dataclass
class RuleCheck:
    code: str
    name: str
    passed: bool
    detail: str = ""


@dataclass
class DivergenceResult:
    hit: bool
    hit_kind: str = "miss"
    direction: str = "top"
    waves: list = field(default_factory=list)
    reasons: list = field(default_factory=list)
    rule_checks: list = field(default_factory=list)
    strength: float = 0.0
    n_passed: int = 0
    n_total: int = 5

    @property
    def failed_rules(self) -> list:
        return [c for c in self.rule_checks if not c.passed]


def _calc_macd_full(close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9):
    """与原始 compute_macd 一致: hist = (dif-dea)*2"""
    n = len(close)
    ef = np.zeros(n); es = np.zeros(n)
    ef[0] = close[0]; es[0] = close[0]
    kf = 2 / (fast + 1); ks = 2 / (slow + 1)
    for i in range(1, n):
        ef[i] = close[i] * kf + ef[i - 1] * (1 - kf)
        es[i] = close[i] * ks + es[i - 1] * (1 - ks)
    dif = ef - es
    dea = np.zeros(n); dea[0] = dif[0]; kd = 2 / (signal + 1)
    for i in range(1, n):
        dea[i] = dif[i] * kd + dea[i - 1] * (1 - kd)
    hist = (dif - dea) * 2.0
    return dif, dea, hist


def _find_crossovers(dif: np.ndarray, dea: np.ndarray) -> list[dict]:
    """与原始 find_crossovers 一致"""
    delta = dif - dea
    records = []
    for i in range(1, len(delta)):
        if delta[i - 1] <= 0 and delta[i] > 0:
            records.append({"idx": i, "type": "up", "value": float(dif[i])})
        elif delta[i - 1] >= 0 and delta[i] < 0:
            records.append({"idx": i, "type": "down", "value": float(dif[i])})
    return sorted(records, key=lambda x: x["idx"])


def _build_waves(
    price: np.ndarray, hist: np.ndarray, crossovers: list[dict],
    start_type: str, end_type: str, extreme_op: str,
) -> list[MacdWave]:
    """与原始 _build_waves 完全一致"""
    starts = [c for c in crossovers if c["type"] == start_type]
    ends = [c for c in crossovers if c["type"] == end_type]
    n = len(price)
    waves: list[MacdWave] = []
    for s in starts:
        si = s["idx"]
        nxt = [e for e in ends if e["idx"] > si]
        ei = nxt[0]["idx"] if nxt else n - 1
        if ei < si:
            continue
        seg_p = price[si:ei + 1]
        seg_h = hist[si:ei + 1]
        if len(seg_p) == 0:
            continue
        if extreme_op == "max":
            eo = int(np.argmax(seg_p))
        else:
            eo = int(np.argmin(seg_p))
        waves.append(MacdWave(
            "up" if start_type == "up" else "down",
            si, ei, float(s["value"]),
            si + eo, float(seg_p[eo]),
            float(np.abs(seg_h).sum()),
        ))
    return waves


def _check_divergence_rules(
    w1: MacdWave, w2: MacdWave, w3: MacdWave,
    dif: np.ndarray, direction: str,
    bars_since_last: int, min_area_reduction: float,
    dif_zero_tolerance: float, dif_approach_zero_ratio: float,
    min_price_increase_pct: float, recency_bars: int,
) -> tuple[list[RuleCheck], float]:
    """与原始 check_divergence_rules 完全一致"""
    checks: list[RuleCheck] = []
    p1, p2, p3 = w1.extreme_price, w2.extreme_price, w3.extreme_price
    c1, c2, c3 = w1.cross_value, w2.cross_value, w3.cross_value
    a1, a2, a3 = w1.hist_area, w2.hist_area, w3.hist_area

    # R1: 价格三推创新极值
    if direction == "top":
        inc12 = (p2 - p1) / p1 if p1 > 0 else 0
        inc23 = (p3 - p2) / p2 if p2 > 0 else 0
        r1_ok = inc12 >= min_price_increase_pct and inc23 >= min_price_increase_pct
        r1_detail = f"{p1:.2f}→{p2:.2f}→{p3:.2f} (+{inc12*100:.2f}%/+{inc23*100:.2f}%)" if r1_ok else \
            f"价格未创新高 {p1:.2f}→{p2:.2f}→{p3:.2f} (+{inc12*100:.2f}%/+{inc23*100:.2f}%)"
        checks.append(RuleCheck("R1", "价格三推创新高", r1_ok, r1_detail))
    else:
        dec12 = (p1 - p2) / p1 if p1 > 0 else 0
        dec23 = (p2 - p3) / p2 if p2 > 0 else 0
        r1_ok = dec12 >= min_price_increase_pct and dec23 >= min_price_increase_pct
        r1_detail = f"{p1:.2f}→{p2:.2f}→{p3:.2f} (-{dec12*100:.2f}%/-{dec23*100:.2f}%)" if r1_ok else \
            f"价格未创新低 {p1:.2f}→{p2:.2f}→{p3:.2f} (-{dec12*100:.2f}%/-{dec23*100:.2f}%)"
        checks.append(RuleCheck("R1", "价格三推创新低", r1_ok, r1_detail))

    # R2: DIF交叉值单调收敛
    if direction == "top":
        r2_ok = c1 > c2 > c3
        checks.append(RuleCheck("R2", "DIF金叉值递减", r2_ok, f"{c1:+.3f}→{c2:+.3f}→{c3:+.3f}"))
    else:
        r2_ok = c1 < c2 < c3
        checks.append(RuleCheck("R2", "DIF死叉值递增", r2_ok, f"{c1:+.3f}→{c2:+.3f}→{c3:+.3f}"))

    # R3: DIF回调逼近零轴（不破零+充分逼近）—— ⭐ 关键规则
    r3_problems = []
    for k, (wA, wB) in enumerate([(w1, w2), (w2, w3)], start=1):
        seg = dif[wA.end_cross_idx:wB.start_cross_idx + 1]
        if len(seg) == 0:
            continue
        if direction == "top":
            seg_min = float(seg.min())
            if seg_min < -dif_zero_tolerance:
                r3_problems.append(f"回调{k}破零(min={seg_min:.3f})")
            if wA.cross_value > 0:
                thr = wA.cross_value * dif_approach_zero_ratio
                if seg_min > thr:
                    r3_problems.append(f"回调{k}未逼近(min={seg_min:.3f}需≤{thr:.3f})")
        else:
            seg_max = float(seg.max())
            if seg_max > dif_zero_tolerance:
                r3_problems.append(f"反弹{k}破零(max={seg_max:.3f})")
            if wA.cross_value < 0:
                thr = wA.cross_value * dif_approach_zero_ratio
                if seg_max < thr:
                    r3_problems.append(f"反弹{k}未逼近(max={seg_max:.3f}需≥{thr:.3f})")
    r3_ok = len(r3_problems) == 0
    r3_detail = "两次回调均逼近零未破" if r3_ok else "; ".join(r3_problems)
    checks.append(RuleCheck("R3", "DIF回调逼近零轴", r3_ok, r3_detail))

    # R4: 柱面积严格衰减
    red12 = (a1 - a2) / a1 if a1 > 0 else 0
    red23 = (a2 - a3) / a2 if a2 > 0 else 0
    r4_mono = a1 > a2 > a3
    r4_enough = red12 >= min_area_reduction and red23 >= min_area_reduction
    r4_ok = r4_mono and r4_enough
    if r4_ok:
        r4_detail = f"{a1:.2f}→{a2:.2f}→{a3:.2f} 衰减{red12*100:.0f}%/{red23*100:.0f}%"
    elif not r4_mono:
        r4_detail = f"非严格递减 {a1:.2f}/{a2:.2f}/{a3:.2f}"
    else:
        r4_detail = f"衰减不足 {red12*100:.0f}%/{red23*100:.0f}% (需≥{min_area_reduction*100:.0f}%)"
    checks.append(RuleCheck("R4", "柱面积严格衰减", r4_ok, r4_detail))

    # R5: 第三推时效
    r5_ok = bars_since_last <= recency_bars
    checks.append(RuleCheck("R5", "第三推时效", r5_ok,
        f"第三推距今{bars_since_last}根 (≤{recency_bars})"))

    # 强度计算（无论是否命中都算）
    if direction == "top":
        ps = min(max((p3 - p1) / max(p1, 1e-6), 0), 0.5) / 0.5
        cs = min(max((c1 - c3) / max(c1, 1e-6), 0), 0.9) / 0.9
    else:
        ps = min(max((p1 - p3) / max(p1, 1e-6), 0), 0.5) / 0.5
        cs = min(max((c3 - c1) / max(abs(c1), 1e-6), 0), 0.9) / 0.9
    a_s = min(max((a1 - a3) / max(a1, 1e-6), 0), 0.9) / 0.9
    strength = float(np.clip((ps + cs + a_s) / 3, 0, 1))
    return checks, strength


def detect_triple_divergence(
    close: np.ndarray, high: np.ndarray, low: np.ndarray,
    direction: str = "top",
    fast: int = 12, slow: int = 26, signal: int = 9,
    min_area_reduction: float = 0.10,
    dif_zero_tolerance: float = 0.0,
    dif_approach_zero_ratio: float = 0.50,
    min_price_increase_pct: float = 0.001,
    recency_bars: int = 30,
) -> DivergenceResult:
    """与原始 detect_triple_divergence 完全一致"""
    n = len(close)
    if n < slow * 2:
        return DivergenceResult(hit=False, direction=direction, reasons=[f"仅{n}根K线"])

    dif, dea, hist = _calc_macd_full(close, fast, slow, signal)
    crossovers = _find_crossovers(dif, dea)

    price_arr = high if direction == "top" else low
    if direction == "top":
        waves = _build_waves(price_arr, hist, crossovers, "up", "down", "max")
    else:
        waves = _build_waves(price_arr, hist, crossovers, "down", "up", "min")

    if len(waves) < 3:
        return DivergenceResult(hit=False, direction=direction, reasons=[f"仅{len(waves)}段wave"])

    w1, w2, w3 = waves[-3:]
    bars_since = n - 1 - w3.extreme_idx
    checks, raw_strength = _check_divergence_rules(
        w1, w2, w3, dif, direction, bars_since,
        min_area_reduction, dif_zero_tolerance, dif_approach_zero_ratio,
        min_price_increase_pct, recency_bars,
    )
    failed = [c for c in checks if not c.passed]

    if len(failed) == 0:
        return DivergenceResult(hit=True, hit_kind="strict", direction=direction,
            waves=[w1, w2, w3], rule_checks=checks, strength=raw_strength,
            n_passed=5, n_total=5)
    if len(failed) == 1:
        return DivergenceResult(hit=False, hit_kind="loose", direction=direction,
            waves=[w1, w2, w3], rule_checks=checks, strength=raw_strength * 0.5,
            reasons=[c.detail for c in failed], n_passed=4, n_total=5)
    return DivergenceResult(hit=False, hit_kind="miss", direction=direction,
        waves=[w1, w2, w3], rule_checks=checks, reasons=[c.detail for c in failed],
        strength=0.0, n_passed=5 - len(failed), n_total=5)


# ══════════════════════════════════════════════════════════════════
# 4. Three-Push — 与原始 three_push.py 完全一致
# ══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ThreePushResult:
    hit: bool
    direction: Direction
    origin: Optional[SwingPoint] = None
    extremes: tuple = ()
    intermediates: tuple = ()
    pullbacks: tuple = ()
    reasons: tuple = ()
    quality: float = 0.0


def detect_three_push(
    close: np.ndarray, high: np.ndarray, low: np.ndarray,
    direction: str = "top",
    pct_threshold: float = 0.03,
    pullback_target: float = 0.75,
    pullback_tolerance: float = 0.15,
    recency_bars: int = 30,
) -> ThreePushResult:
    """与原始 detect_three_push 完全一致"""
    swings = find_swing_points(high, low, close, pct_threshold=pct_threshold)
    ending_kind = "high" if direction == "top" else "low"
    expected_seq = (
        ["low", "high", "low", "high", "low", "high"] if direction == "top"
        else ["high", "low", "high", "low", "high", "low"]
    )

    # 取最后6个以ending_kind结尾的摆点
    six = None
    for i in range(len(swings) - 1, -1, -1):
        if swings[i].kind == ending_kind and i >= 5:
            six = swings[i - 5:i + 1]
            break
    if six is None:
        return ThreePushResult(hit=False, direction=direction, reasons=(f"摆点不足",))

    actual = [s.kind for s in six]
    if actual != expected_seq:
        return ThreePushResult(hit=False, direction=direction, reasons=(f"高低交替断裂",))

    s0, e1, s1, e2, s2, e3 = six
    extremes = (e1, e2, e3)
    intermediates = (s1, s2)

    # 三推同向
    if direction == "top":
        if not (e1.price < e2.price < e3.price):
            return ThreePushResult(hit=False, direction=direction, extremes=extremes,
                reasons=(f"高点未递增",))
        push1 = e1.price - s0.price; pull1 = e1.price - s1.price
        push2 = e2.price - s1.price; pull2 = e2.price - s2.price
    else:
        if not (e1.price > e2.price > e3.price):
            return ThreePushResult(hit=False, direction=direction, extremes=extremes,
                reasons=(f"低点未递减",))
        push1 = s0.price - e1.price; pull1 = s1.price - e1.price
        push2 = s1.price - e2.price; pull2 = s2.price - e2.price

    if push1 <= 0 or push2 <= 0:
        return ThreePushResult(hit=False, direction=direction, extremes=extremes,
            reasons=("推浪幅度无效",))

    r1, r2 = pull1 / push1, pull2 / push2
    low_pct = pullback_target - pullback_tolerance
    high_pct = pullback_target + pullback_tolerance

    bad = []
    if not (low_pct <= r1 <= high_pct):
        bad.append(f"回撤1={r1:.0%}不在[{low_pct:.0%},{high_pct:.0%}]")
    if not (low_pct <= r2 <= high_pct):
        bad.append(f"回撤2={r2:.0%}不在[{low_pct:.0%},{high_pct:.0%}]")

    bars_since = len(close) - 1 - e3.idx
    if bars_since > recency_bars:
        bad.append(f"第三推距今{bars_since}>{recency_bars}根")

    if bad:
        return ThreePushResult(hit=False, direction=direction, origin=s0,
            extremes=extremes, intermediates=intermediates,
            pullbacks=(r1, r2), reasons=tuple(bad))

    # 质量评分 → 与原始一致
    d1 = abs(r1 - pullback_target) / pullback_tolerance
    d2 = abs(r2 - pullback_target) / pullback_tolerance
    quality = max(0.0, 1.0 - (d1 + d2) / 2)

    return ThreePushResult(hit=True, direction=direction, origin=s0,
        extremes=extremes, intermediates=intermediates,
        pullbacks=(r1, r2), quality=quality)


# ══════════════════════════════════════════════════════════════════
# 5. PDA (HTF) — 与原始 pda.py 一致
# ══════════════════════════════════════════════════════════════════

def resample_weekly(high: np.ndarray, low: np.ndarray, open_: np.ndarray, close: np.ndarray) -> tuple:
    """日线→周线: 按W-FRI对齐(A股周末休市, 每5天一组)"""
    w = len(close) // 5
    if w < 5:
        return None, None, None, None
    return (
        np.array([high[i * 5:(i + 1) * 5].max() for i in range(w)]),
        np.array([low[i * 5:(i + 1) * 5].min() for i in range(w)]),
        np.array([open_[i * 5] for i in range(w)]),
        np.array([close[(i + 1) * 5 - 1] for i in range(w)]),
    )


def detect_htf_pda(
    high: np.ndarray, low: np.ndarray, open_: np.ndarray, close: np.ndarray,
    target_price: float, direction: str = "bottom",
) -> dict:
    """与原始 detect_htf_pda_hit 一致 — 返回评分制"""
    wh, wl, wo, wc = resample_weekly(high, low, open_, close)
    if wh is None:
        return {"hit": False, "quality": "NONE"}

    active = find_active_zones(wh, wl, wo, wc)
    zone_dir = "bearish" if direction == "top" else "bullish"
    hits = [z for z in active if z.direction == zone_dir and z.contains(target_price)]

    if not hits:
        return {"hit": False, "quality": "NONE"}

    overlaps = find_overlap_zones(hits)
    if overlaps:
        return {"hit": True, "quality": "OB+FVG", "zones": hits}
    # 检查是否有OB+FVG混合(不需要overlap, 只要有同向的两种zone)
    kinds = {z.kind for z in hits}
    if "ob" in kinds and "fvg" in kinds:
        return {"hit": True, "quality": "OB+FVG", "zones": hits}
    if "ob" in kinds:
        return {"hit": True, "quality": "OB", "zones": hits}
    return {"hit": True, "quality": "FVG", "zones": hits}


# ══════════════════════════════════════════════════════════════════
# 6. 主入口 — 与原始 scan_one / scan_all 一致
# ══════════════════════════════════════════════════════════════════

def _macd_score(kind: str) -> float:
    return {"strict": 1.0, "loose": 0.5}.get(kind, 0.0)


def _pda_score(quality: str) -> float:
    if quality == "OB+FVG":
        return 1.0
    if quality in ("OB", "FVG"):
        return 0.5
    return 0.0


def scan_one(
    high: np.ndarray, low: np.ndarray, open_: np.ndarray, close: np.ndarray,
    direction: str = "bottom",
) -> dict:
    """
    单股SMC/ICT扫描 — 与原始 scan_one 完全一致。

    Args:
        high, low, open_, close: OHLC numpy arrays
        direction: 'top'(做空) 或 'bottom'(做多)

    Returns:
        dict with:
          - signal: 'LONG'/'SHORT'
          - score: 0.0~3.0 (MACD+ThreePush+PDA)
          - macd_kind: 'strict'/'loose'/'miss'
          - macd_passed: 'N/5'
          - macd_strength: 0.0~1.0
          - three_push_hit: bool
          - three_push_quality: 0.0~1.0
          - pda_hit: bool
          - pda_quality: 'OB+FVG'/'OB'/'FVG'/'NONE'
          - trade_plan: dict or None (入场/止损/目标/R:R)
          - notes: 信号描述字符串
    """
    n = len(close)
    cfg = CONFIG

    # 找目标价格(最后一推的极值)
    swings = find_swing_points(high, low, close, cfg["swing"]["pct_threshold"])
    target_kind = "high" if direction == "top" else "low"
    candidates = [s for s in swings if s.kind == target_kind]
    target_price = candidates[-1].price if candidates else float(close[-1])

    # 三个检测器
    macd_res = detect_triple_divergence(
        close, high, low, direction=direction,
        fast=cfg["macd"]["fast"], slow=cfg["macd"]["slow"], signal=cfg["macd"]["signal"],
        min_area_reduction=cfg["divergence"]["min_area_reduction"],
        dif_zero_tolerance=cfg["divergence"]["dif_zero_tolerance"],
        dif_approach_zero_ratio=cfg["divergence"]["dif_approach_zero_ratio"],
        min_price_increase_pct=cfg["divergence"]["min_price_increase_pct"],
        recency_bars=cfg["divergence"]["recency_bars"],
    )
    tp_res = detect_three_push(
        close, high, low, direction=direction,
        pct_threshold=cfg["swing"]["pct_threshold"],
        pullback_target=cfg["three_push"]["pullback_target_pct"],
        pullback_tolerance=cfg["three_push"]["pullback_tolerance"],
        recency_bars=cfg["divergence"]["recency_bars"],
    )
    pda_res = detect_htf_pda(high, low, open_, close, target_price, direction)

    # 综合评分 — 与原始完全一致
    score = 0.0
    score += _macd_score(macd_res.hit_kind)
    score += 1.0 if tp_res.hit else 0.0
    score += _pda_score(pda_res["quality"])

    # 构建notes — 与原始 build_notes 一致
    parts = []
    label = "顶" if direction == "top" else "底"

    if tp_res.hit and tp_res.pullbacks:
        e1, e2, e3 = tp_res.extremes
        p1, p2 = tp_res.pullbacks
        pw = "回撤" if direction == "top" else "反弹"
        parts.append(f"三推{label} ¥{e1.price:.2f}→¥{e2.price:.2f}→¥{e3.price:.2f} {pw}{p1*100:.0f}%/{p2*100:.0f}%")

    if macd_res.hit_kind == "strict":
        parts.append(f"MACD严格{label}背离({macd_res.n_passed}/{macd_res.n_total},强度{macd_res.strength:.2f})")
    elif macd_res.hit_kind == "loose":
        failed = macd_res.failed_rules
        miss = failed[0].code if failed else ""
        parts.append(f"MACD宽松{label}背离({macd_res.n_passed}/{macd_res.n_total},差{miss},强度{macd_res.strength:.2f})")

    if pda_res["hit"]:
        z = pda_res["zones"][0]
        parts.append(f"周线{pda_res['quality']}[{z.zone_low:.2f}-{z.zone_high:.2f}]")

    # 交易计划: PDA命中+三推或MACD命中时生成
    trade_plan = None
    if pda_res["hit"] and (tp_res.hit or macd_res.hit_kind != "miss"):
        zone = pda_res["zones"][0]
        origin_price = tp_res.origin.price if (tp_res.hit and tp_res.origin) else None
        buffer_pct = 0.01

        if direction == "bottom":
            stop = zone.zone_low * (1 - buffer_pct)
            entry = target_price
            target = origin_price
            if target is not None and target > entry > stop:
                rr = (target - entry) / (entry - stop)
                parts.append(f"多:入¥{entry:.2f} 止¥{stop:.2f} 标¥{target:.2f} R:R{rr:.1f}")
                trade_plan = {"entry": round(entry, 2), "stop": round(stop, 2),
                              "target": round(target, 2), "rr": round(rr, 1)}
        else:
            stop = zone.zone_high * (1 + buffer_pct)
            entry = target_price
            target = origin_price
            if target is not None and stop > entry > target:
                rr = (entry - target) / (stop - entry)
                parts.append(f"空:入¥{entry:.2f} 止¥{stop:.2f} 标¥{target:.2f} R:R{rr:.1f}")
                trade_plan = {"entry": round(entry, 2), "stop": round(stop, 2),
                              "target": round(target, 2), "rr": round(rr, 1)}

    return {
        "signal": "SHORT" if direction == "top" else "LONG",
        "direction": direction,
        "score": round(score, 2),
        "last_close": round(float(close[-1]), 2),
        "target_price": round(target_price, 2),
        "macd_kind": macd_res.hit_kind,
        "macd_passed": f"{macd_res.n_passed}/{macd_res.n_total}",
        "macd_strength": round(macd_res.strength, 3) if macd_res.hit_kind != "miss" else None,
        "three_push_hit": tp_res.hit,
        "three_push_quality": round(tp_res.quality, 3) if tp_res.hit else None,
        "pda_hit": pda_res["hit"],
        "pda_quality": pda_res["quality"] if pda_res["hit"] else None,
        "trade_plan": trade_plan,
        "notes": " | ".join(parts) if parts else "(无显著信号)",
    }


def scan_both(
    high: np.ndarray, low: np.ndarray, open_: np.ndarray, close: np.ndarray,
) -> dict:
    """同时扫描做多(bottom)和做空(top)，返回两个方向的结果"""
    return {
        "bottom": scan_one(high, low, open_, close, direction="bottom"),
        "top": scan_one(high, low, open_, close, direction="top"),
    }


# ══════════════════════════════════════════════════════════════════
# CLI 测试
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys, json, baostock as bs, numpy as np

    code = sys.argv[1] if len(sys.argv) > 1 else "600362"

    bs.login()
    sym = f"{'sh' if code.startswith('6') else 'sz'}.{code}"
    rs = bs.query_history_k_data_plus(sym, 'date,open,high,low,close,volume',
        start_date='2025-07-01', end_date='2026-07-03', frequency='d', adjustflag='2')
    rows = []
    while (rs.error_code == '0') and rs.next():
        rows.append(rs.get_row_data())
    bs.logout()

    o = np.array([float(r[1]) for r in rows])
    h = np.array([float(r[2]) for r in rows])
    l = np.array([float(r[3]) for r in rows])
    c = np.array([float(r[4]) for r in rows])

    result = scan_both(h, l, o, c)

    for direction in ("bottom", "top"):
        r = result[direction]
        print(f"\n{'='*60}")
        print(f"  {code} [{direction}] 总分={r['score']} ({r['signal']}) | 现价¥{r['last_close']}")
        print(f"  MACD: {r['macd_kind']} ({r['macd_passed']}) 强度={r['macd_strength']}")
        print(f"  三推: {'✅' if r['three_push_hit'] else '❌'} Q={r['three_push_quality']}")
        print(f"  PDA:  {'✅' if r['pda_hit'] else '❌'} {r['pda_quality']}")
        print(f"  备注: {r['notes']}")
        if r['trade_plan']:
            tp = r['trade_plan']
            print(f"  🎯 交易计划: 入¥{tp['entry']} 止¥{tp['stop']} 标¥{tp['target']} R:R{tp['rr']}")
