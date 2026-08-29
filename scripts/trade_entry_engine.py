# -*- coding: utf-8 -*-
"""
trade_entry_engine.py

A-share quantitative trade-entry engine.

Purpose
-------
Turn a scan candidate into an executable trade plan:

    candidate
      -> eligibility
      -> alpha/setup gate
      -> structural support/stop
      -> realistic T1
      -> max acceptable entry by R:R
      -> ideal entry zone
      -> lower-timeframe trigger
      -> risk-based position sizing
      -> final action

Design principles
-----------------
1) Model decides "whether the stock is worth trading".
2) Price structure decides "where to buy".
3) Lower timeframe decides "when to buy".
4) Risk engine decides "how much to buy".
5) Single-stock notional is capped in the 200k-300k RMB range.
6) Do NOT force a 200k-300k position if stop-distance implies a smaller size.
7) T1 must be the nearest realistic resistance, not a remote optimistic target.

This is a research/execution-planning engine. It does not place orders.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from math import floor
from typing import Optional, Dict, Any


class TradeState(str, Enum):
    NO_TRADE = "NO_TRADE"
    WATCH = "WATCH"
    SETUP = "SETUP"
    TRIGGERED_LONG = "TRIGGERED_LONG"
    ACTIVE = "ACTIVE"
    REDUCE = "REDUCE"
    EXIT = "EXIT"


@dataclass
class EngineConfig:
    # Account / risk
    account_equity: float = 1_000_000.0

    # Risk budget per trade.
    # 0.5% NAV on a 1m account = 5,000 RMB max planned loss.
    risk_per_trade: float = 0.005

    # Hard cap of single-stock notional.
    hard_max_notional: float = 300_000.0

    # Signal-tier caps.
    cap_normal: float = 200_000.0
    cap_strong: float = 250_000.0
    cap_very_strong: float = 300_000.0

    # A-share board lot
    lot_size: int = 100

    # Model/setup gates
    min_xgb: float = 52.0
    min_3d: float = 48.0
    min_setup_quality: float = 60.0
    min_data_confidence: float = 0.80

    # Entry-zone construction
    entry_zone_low_atr: float = 0.10
    entry_zone_high_atr: float = 0.40
    max_support_distance_atr: float = 1.00

    # R:R policy
    min_rr_very_strong: float = 1.8
    min_rr_strong: float = 2.0
    min_rr_normal: float = 2.5

    # If current price is too far above max acceptable entry -> do not chase
    chase_tolerance_pct: float = 0.003  # 0.3%

    # Optional portfolio-level cap for total deployed capital
    max_portfolio_deployed_pct: float = 0.70


@dataclass
class Candidate:
    code: str
    name: str

    # Current price
    price: float

    # Model / scan scores
    xgb_score: float
    score_3d: float
    setup_quality: float

    # 0~1
    data_confidence: float = 1.0

    # Structure
    support: float = 0.0
    structural_stop: float = 0.0
    target1: float = 0.0
    target2: Optional[float] = None

    # Volatility
    atr: float = 0.0

    # Location / structure flags
    in_valid_structure: bool = True
    daily_trend_ok: bool = True

    # Lower-timeframe confirmation
    lower_tf_higher_low: bool = False
    lower_tf_macd_positive: bool = False
    lower_tf_breakout: bool = False
    lower_tf_volume_confirm: bool = False

    # Optional explicit trigger price.
    # Example: 60m structure high to break.
    trigger_price: Optional[float] = None

    # Optional market-regime score:
    # -1 strong bear, 0 neutral, +1 strong bull
    market_regime: float = 0.0

    # Optional current deployed capital, used for portfolio cap.
    current_portfolio_deployed: float = 0.0


@dataclass
class TradePlan:
    code: str
    name: str
    state: str
    action: str

    signal_strength: str
    min_required_rr: float

    current_price: float
    support: float
    ideal_entry_low: float
    ideal_entry_high: float
    max_acceptable_entry: float
    trigger_price: Optional[float]

    stop: float
    target1: float
    target2: Optional[float]

    rr_at_current: float
    rr_at_ideal_mid: float

    risk_budget_rmb: float
    position_cap_rmb: float
    suggested_notional_rmb: float
    suggested_shares: int
    estimated_loss_at_stop_rmb: float

    distance_to_support_atr: float
    trigger_score: int
    trigger_pass: bool

    reason: str


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def safe_rr(entry: float, stop: float, target: float) -> float:
    risk = entry - stop
    reward = target - entry
    if risk <= 0 or reward <= 0:
        return 0.0
    return reward / risk


def max_entry_for_rr(stop: float, target: float, min_rr: float) -> float:
    """
    Solve:
        (target - entry) / (entry - stop) >= min_rr

    Boundary:
        entry_max = (target + min_rr * stop) / (1 + min_rr)
    """
    if target <= stop or min_rr <= 0:
        return 0.0
    return (target + min_rr * stop) / (1.0 + min_rr)


def lower_tf_trigger_score(c: Candidate) -> int:
    """
    Four confirmation items.
    Require >= 2 for a normal trigger.
    Require >= 3 if model/setup is only normal.
    """
    flags = [
        c.lower_tf_higher_low,
        c.lower_tf_macd_positive,
        c.lower_tf_breakout,
        c.lower_tf_volume_confirm,
    ]
    return sum(bool(x) for x in flags)


def classify_signal_strength(c: Candidate) -> str:
    """
    Do not allow a single strong sub-score to dominate.
    Very strong requires both ML and setup quality.
    """
    alpha = 0.60 * c.xgb_score + 0.40 * c.score_3d

    if (
        alpha >= 65
        and c.setup_quality >= 80
        and c.data_confidence >= 0.90
    ):
        return "VERY_STRONG"

    if (
        alpha >= 58
        and c.setup_quality >= 70
        and c.data_confidence >= 0.85
    ):
        return "STRONG"

    return "NORMAL"


def rr_requirement(strength: str, cfg: EngineConfig) -> float:
    if strength == "VERY_STRONG":
        return cfg.min_rr_very_strong
    if strength == "STRONG":
        return cfg.min_rr_strong
    return cfg.min_rr_normal


def notional_cap(strength: str, cfg: EngineConfig) -> float:
    if strength == "VERY_STRONG":
        cap = cfg.cap_very_strong
    elif strength == "STRONG":
        cap = cfg.cap_strong
    else:
        cap = cfg.cap_normal
    return min(cap, cfg.hard_max_notional)


def build_entry_zone(
    support: float,
    atr: float,
    max_acceptable_entry: float,
    cfg: EngineConfig,
) -> tuple[float, float]:
    """
    Entry zone is slightly above support:
        support + 0.1 ATR ... support + 0.4 ATR

    But the upper bound is never allowed above max acceptable entry.
    """
    low = support + cfg.entry_zone_low_atr * atr
    high = support + cfg.entry_zone_high_atr * atr
    high = min(high, max_acceptable_entry)

    if high < low:
        # R:R constraint is tighter than normal zone.
        low = max(support, high - 0.15 * atr)

    return round(low, 3), round(high, 3)


def size_position(
    entry: float,
    stop: float,
    strength: str,
    cfg: EngineConfig,
    current_portfolio_deployed: float = 0.0,
) -> tuple[float, int, float, float]:
    """
    Position is the minimum of:
      1) risk-based notional
      2) signal-tier notional cap (200k/250k/300k)
      3) hard max notional
      4) remaining portfolio deployment allowance

    For A-shares, shares are rounded DOWN to board-lot size.
    """
    per_share_risk = entry - stop
    if per_share_risk <= 0 or entry <= 0:
        return 0.0, 0, 0.0, 0.0

    risk_budget = cfg.account_equity * cfg.risk_per_trade

    # shares allowed by loss budget
    risk_based_shares = floor(risk_budget / per_share_risk)

    # signal cap
    cap_rmb = notional_cap(strength, cfg)
    cap_based_shares = floor(cap_rmb / entry)

    # portfolio capital cap
    max_deployed = cfg.account_equity * cfg.max_portfolio_deployed_pct
    remaining = max(0.0, max_deployed - current_portfolio_deployed)
    portfolio_based_shares = floor(remaining / entry)

    raw_shares = min(
        risk_based_shares,
        cap_based_shares,
        portfolio_based_shares,
    )

    lot = cfg.lot_size
    shares = floor(raw_shares / lot) * lot

    if shares <= 0:
        return risk_budget, 0, cap_rmb, 0.0

    notional = shares * entry
    loss_at_stop = shares * per_share_risk

    return risk_budget, shares, cap_rmb, loss_at_stop


def evaluate_candidate(c: Candidate, cfg: EngineConfig) -> TradePlan:
    reasons = []

    # ---------- Hard eligibility ----------
    invalid = []

    if c.price <= 0:
        invalid.append("现价无效")
    if c.atr <= 0:
        invalid.append("ATR无效")
    if c.support <= 0:
        invalid.append("结构支撑无效")
    if c.structural_stop <= 0:
        invalid.append("结构止损无效")
    if c.target1 <= 0:
        invalid.append("T1无效")
    if c.structural_stop >= c.support:
        invalid.append("止损应低于结构支撑")
    if c.target1 <= c.support:
        invalid.append("T1应高于结构支撑")
    if not c.in_valid_structure:
        invalid.append("结构条件不满足")
    if not c.daily_trend_ok:
        invalid.append("日线趋势不满足")
    if c.data_confidence < cfg.min_data_confidence:
        invalid.append("数据置信度不足")
    if c.xgb_score < cfg.min_xgb:
        invalid.append("XGB不足")
    if c.score_3d < cfg.min_3d:
        invalid.append("3D不足")
    if c.setup_quality < cfg.min_setup_quality:
        invalid.append("Setup质量不足")

    strength = classify_signal_strength(c)
    min_rr = rr_requirement(strength, cfg)

    max_entry = max_entry_for_rr(
        c.structural_stop,
        c.target1,
        min_rr,
    )

    # If T1 itself is too close to create a trade, fail.
    if max_entry <= c.structural_stop:
        invalid.append("R:R无法成立")

    entry_low, entry_high = build_entry_zone(
        c.support,
        c.atr,
        max_entry,
        cfg,
    )

    dist_support_atr = (
        (c.price - c.support) / c.atr
        if c.atr > 0
        else 999.0
    )

    rr_current = safe_rr(
        c.price,
        c.structural_stop,
        c.target1,
    )

    ideal_mid = (entry_low + entry_high) / 2.0
    rr_ideal = safe_rr(
        ideal_mid,
        c.structural_stop,
        c.target1,
    )

    trig_score = lower_tf_trigger_score(c)

    # NORMAL setup needs stronger lower-TF confirmation.
    required_trigger_score = 3 if strength == "NORMAL" else 2
    trigger_pass = trig_score >= required_trigger_score

    # If explicit trigger price exists, price must also be near/above it
    # unless the trade is a support-reversal style entry.
    if c.trigger_price is not None:
        trigger_pass = trigger_pass and (
            c.price >= c.trigger_price * (1.0 - 0.002)
        )

    # ---------- Early NO_TRADE ----------
    if invalid:
        return TradePlan(
            code=c.code,
            name=c.name,
            state=TradeState.NO_TRADE.value,
            action="不交易",
            signal_strength=strength,
            min_required_rr=min_rr,
            current_price=round(c.price, 3),
            support=round(c.support, 3),
            ideal_entry_low=entry_low,
            ideal_entry_high=entry_high,
            max_acceptable_entry=round(max_entry, 3),
            trigger_price=c.trigger_price,
            stop=round(c.structural_stop, 3),
            target1=round(c.target1, 3),
            target2=round(c.target2, 3) if c.target2 else None,
            rr_at_current=round(rr_current, 2),
            rr_at_ideal_mid=round(rr_ideal, 2),
            risk_budget_rmb=round(cfg.account_equity * cfg.risk_per_trade, 2),
            position_cap_rmb=round(notional_cap(strength, cfg), 2),
            suggested_notional_rmb=0.0,
            suggested_shares=0,
            estimated_loss_at_stop_rmb=0.0,
            distance_to_support_atr=round(dist_support_atr, 2),
            trigger_score=trig_score,
            trigger_pass=False,
            reason="；".join(invalid),
        )

    # ---------- Do not chase ----------
    if c.price > max_entry * (1.0 + cfg.chase_tolerance_pct):
        reasons.append(
            f"现价高于最高接受价 {max_entry:.2f}，R:R不足，不追"
        )
        return TradePlan(
            code=c.code,
            name=c.name,
            state=TradeState.WATCH.value,
            action=f"等待回踩 {entry_low:.2f}~{entry_high:.2f}",
            signal_strength=strength,
            min_required_rr=min_rr,
            current_price=round(c.price, 3),
            support=round(c.support, 3),
            ideal_entry_low=entry_low,
            ideal_entry_high=entry_high,
            max_acceptable_entry=round(max_entry, 3),
            trigger_price=c.trigger_price,
            stop=round(c.structural_stop, 3),
            target1=round(c.target1, 3),
            target2=round(c.target2, 3) if c.target2 else None,
            rr_at_current=round(rr_current, 2),
            rr_at_ideal_mid=round(rr_ideal, 2),
            risk_budget_rmb=round(cfg.account_equity * cfg.risk_per_trade, 2),
            position_cap_rmb=round(notional_cap(strength, cfg), 2),
            suggested_notional_rmb=0.0,
            suggested_shares=0,
            estimated_loss_at_stop_rmb=0.0,
            distance_to_support_atr=round(dist_support_atr, 2),
            trigger_score=trig_score,
            trigger_pass=trigger_pass,
            reason="；".join(reasons),
        )

    # Too far from support even if R:R barely passes
    if dist_support_atr > cfg.max_support_distance_atr:
        reasons.append(
            f"距离结构支撑 {dist_support_atr:.2f} ATR，位置偏贵"
        )
        return TradePlan(
            code=c.code,
            name=c.name,
            state=TradeState.WATCH.value,
            action=f"等待靠近支撑，优先 {entry_low:.2f}~{entry_high:.2f}",
            signal_strength=strength,
            min_required_rr=min_rr,
            current_price=round(c.price, 3),
            support=round(c.support, 3),
            ideal_entry_low=entry_low,
            ideal_entry_high=entry_high,
            max_acceptable_entry=round(max_entry, 3),
            trigger_price=c.trigger_price,
            stop=round(c.structural_stop, 3),
            target1=round(c.target1, 3),
            target2=round(c.target2, 3) if c.target2 else None,
            rr_at_current=round(rr_current, 2),
            rr_at_ideal_mid=round(rr_ideal, 2),
            risk_budget_rmb=round(cfg.account_equity * cfg.risk_per_trade, 2),
            position_cap_rmb=round(notional_cap(strength, cfg), 2),
            suggested_notional_rmb=0.0,
            suggested_shares=0,
            estimated_loss_at_stop_rmb=0.0,
            distance_to_support_atr=round(dist_support_atr, 2),
            trigger_score=trig_score,
            trigger_pass=trigger_pass,
            reason="；".join(reasons),
        )

    # ---------- Setup / Trigger ----------
    in_entry_zone = entry_low <= c.price <= entry_high

    # Allow slight tolerance around the entry zone
    near_entry_zone = (
        c.price >= entry_low - 0.10 * c.atr
        and c.price <= entry_high + 0.10 * c.atr
    )

    if not near_entry_zone:
        reasons.append("价格尚未进入理想买入区")
        state = TradeState.SETUP.value
        action = f"挂观察：理想区 {entry_low:.2f}~{entry_high:.2f}"
        shares = 0
        cap_rmb = notional_cap(strength, cfg)
        risk_budget = cfg.account_equity * cfg.risk_per_trade
        loss_at_stop = 0.0
        suggested_notional = 0.0

    elif not trigger_pass:
        reasons.append(
            f"已接近买入区，但小周期确认仅 {trig_score}/{required_trigger_score}"
        )
        state = TradeState.SETUP.value
        action = "等待30/60分钟确认，不提前抢跑"
        shares = 0
        cap_rmb = notional_cap(strength, cfg)
        risk_budget = cfg.account_equity * cfg.risk_per_trade
        loss_at_stop = 0.0
        suggested_notional = 0.0

    else:
        # Use current price as executable reference.
        entry_for_sizing = c.price

        risk_budget, shares, cap_rmb, loss_at_stop = size_position(
            entry_for_sizing,
            c.structural_stop,
            strength,
            cfg,
            c.current_portfolio_deployed,
        )

        suggested_notional = shares * entry_for_sizing

        if shares <= 0:
            reasons.append("风险预算/组合资金不足以形成最小交易单位")
            state = TradeState.NO_TRADE.value
            action = "不交易"
        else:
            reasons.append("价格、R:R、小周期触发和风险预算均通过")
            state = TradeState.TRIGGERED_LONG.value
            action = "允许买入"

    return TradePlan(
        code=c.code,
        name=c.name,
        state=state,
        action=action,
        signal_strength=strength,
        min_required_rr=min_rr,
        current_price=round(c.price, 3),
        support=round(c.support, 3),
        ideal_entry_low=entry_low,
        ideal_entry_high=entry_high,
        max_acceptable_entry=round(max_entry, 3),
        trigger_price=c.trigger_price,
        stop=round(c.structural_stop, 3),
        target1=round(c.target1, 3),
        target2=round(c.target2, 3) if c.target2 else None,
        rr_at_current=round(rr_current, 2),
        rr_at_ideal_mid=round(rr_ideal, 2),
        risk_budget_rmb=round(risk_budget, 2),
        position_cap_rmb=round(cap_rmb, 2),
        suggested_notional_rmb=round(suggested_notional, 2),
        suggested_shares=shares,
        estimated_loss_at_stop_rmb=round(loss_at_stop, 2),
        distance_to_support_atr=round(dist_support_atr, 2),
        trigger_score=trig_score,
        trigger_pass=trigger_pass,
        reason="；".join(reasons),
    )


def print_plan(plan: TradePlan) -> None:
    d = asdict(plan)
    width = 28
    print("=" * 72)
    print(f"{plan.name} {plan.code}")
    print("=" * 72)
    for k, v in d.items():
        print(f"{k:<{width}} {v}")


if __name__ == "__main__":
    # ---------------------------------------------------------
    # Example only.
    # Replace these values with real outputs from your scan engine.
    #
    # Key inputs:
    # support          = nearest REAL structural support
    # structural_stop  = actual setup invalidation price
    # target1          = nearest REALISTIC resistance
    # target2          = optional larger trend target
    # atr              = preferably ATR14 on daily timeframe
    #
    # Lower-TF flags should come from 30m/60m data.
    # ---------------------------------------------------------

    cfg = EngineConfig(
        account_equity=1_000_000,
        risk_per_trade=0.005,       # 0.5% NAV risk
        cap_normal=200_000,
        cap_strong=250_000,
        cap_very_strong=300_000,
        hard_max_notional=300_000,
    )

    demo = Candidate(
        code="600309",
        name="万华化学",
        price=77.50,

        xgb_score=57,
        score_3d=49,
        setup_quality=81.3,
        data_confidence=0.95,

        # Example structure values only.
        # Replace with your actual structural extraction.
        support=76.80,
        structural_stop=73.69,
        target1=82.50,
        target2=88.66,
        atr=2.20,

        in_valid_structure=True,
        daily_trend_ok=True,

        lower_tf_higher_low=True,
        lower_tf_macd_positive=True,
        lower_tf_breakout=True,
        lower_tf_volume_confirm=False,

        trigger_price=77.40,
        market_regime=0.2,
        current_portfolio_deployed=300_000,
    )

    plan = evaluate_candidate(demo, cfg)
    print_plan(plan)

    # For integration:
    # result_dict = asdict(plan)
    # Write result_dict into your scan dataframe / CSV / Excel.
