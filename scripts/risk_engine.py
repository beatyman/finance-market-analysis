#!/usr/bin/env python3
"""
风险优先交易引擎 — 吸收自 Julian-dev28/hermes-trader（Hyperliquid 自主交易系统）

纯函数模块，零外部依赖（dataclasses/time/typing），资产类别无关（A股/加密/期货通用）。

三大模块：
  1. sizing       — ATR 等风险仓位规模（Turtle N / Larry Hite / Ed Seykota 学派）
  2. risk_gates   — 11 道风险门控（每道都是纯函数返回 {pass, reason}）
  3. dsl_exit     — DSL 两阶段动态退出（Phase1 损失保护 → Phase2 利润锁定）

核心思想（与"交易=规避风险而非追逐机会"一致）：
  - 每笔交易止损亏损 = 固定比例的权益（无论标的波动率/杠杆）
  - 杠杆是"输出"（notional/equity），不是"输入"——先定风险，再定仓位
  - 锁住盈利日：当日 PnL 回撤超阈值即停开新仓，防止赢的一天全部吐回
  - 空头需要更多流动性（薄市场会被挤压）
  - 持仓只由 DSL 引擎管理，禁止翻单/金字塔加仓
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Iterable

# ══════════════════════════════════════════════════════════════════
# 1. SIZING — ATR 等风险仓位规模
# ══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SizingResult:
    notional_usd: float        # 仓位名义金额（美元/元）
    implied_leverage: float    # notional / equity（结果，不是输入）
    risk_usd: float            # 止损触发时的亏损金额
    stop_distance_frac: float  # 入场到止损的分数价格变动
    clamped_by: str            # "" | "notional_cap" | "max_leverage" | "zero"


def atr_equal_risk_notional(
    *,
    equity: float,
    risk_per_trade_pct: float,   # 每笔止损亏损占权益比例（如 0.01 = 1%）
    atr_abs: float,              # ATR 绝对价格（价格单位）
    entry_px: float,
    sl_atr_mult: float,          # 止损距离 = sl_atr_mult × ATR
    max_trade_notional_usd: float = 0.0,  # 单笔名义硬上限（0 = 无）
    coin_max_leverage: int = 0,           # 交易所单币最大杠杆（0 = 未知）
    config_max_leverage: int = 0,         # 操作者杠杆上限（0 = 无）
) -> SizingResult:
    """Turtle-"N" 等美元风险仓位规模。

    解  notional * stop_distance_frac == risk_per_trade_pct * equity
    使每笔交易止损亏损 = 固定权益比例，再用单笔上限和杠杆上限夹紧。
    杠杆是输出（notional/equity），永不是输入——按风险定仓位，
    不是先选杠杆再发现风险。返回 notional=0（clamped_by="zero"）时
    调用方必须视为"不交易"，绝不当作"用默认值"。
    """
    if equity <= 0 or atr_abs <= 0 or entry_px <= 0 or risk_per_trade_pct <= 0 or sl_atr_mult <= 0:
        return SizingResult(0.0, 0.0, 0.0, 0.0, "zero")

    stop_distance_frac = (sl_atr_mult * atr_abs) / entry_px
    if stop_distance_frac <= 0:
        return SizingResult(0.0, 0.0, 0.0, 0.0, "zero")

    risk_usd_target = risk_per_trade_pct * equity
    notional = risk_usd_target / stop_distance_frac
    clamped_by = ""

    lev_caps = [c for c in (coin_max_leverage, config_max_leverage) if c and c > 0]
    if lev_caps:
        max_notional_by_lev = min(lev_caps) * equity
        if notional > max_notional_by_lev:
            notional = max_notional_by_lev
            clamped_by = "max_leverage"

    if max_trade_notional_usd and max_trade_notional_usd > 0 and notional > max_trade_notional_usd:
        notional = max_trade_notional_usd
        clamped_by = "notional_cap"

    implied_leverage = notional / equity if equity > 0 else 0.0
    risk_usd = notional * stop_distance_frac
    return SizingResult(notional, implied_leverage, risk_usd, stop_distance_frac, clamped_by)


def risk_of_ruin(
    *,
    win_rate: float,
    payoff_ratio: float,
    risk_per_trade_pct: float,
    ruin_fraction: float = 1.0,
) -> float:
    """固定分数赌徒的近似最终破产概率（0..1）。

    标准 gambler's-ruin 逐单位近似：每笔风险一"单位"（= 权益的
    risk_per_trade_pct），以概率 win_rate 赢 payoff_ratio 单位。
    无正期望（edge<=0）→ 必然破产（返回1.0）。用途是让"这个风险
    比例太疯狂"在账户证明之前就可见。
    """
    win_rate = max(0.0, min(1.0, win_rate))
    if payoff_ratio <= 0 or risk_per_trade_pct <= 0:
        return 1.0
    loss_rate = 1.0 - win_rate
    edge_per_unit = win_rate * payoff_ratio - loss_rate
    if edge_per_unit <= 0:
        return 1.0
    a = edge_per_unit / (win_rate * payoff_ratio + loss_rate)
    a = max(0.0, min(0.999999, a))
    units_to_ruin = max(1.0, ruin_fraction / risk_per_trade_pct)
    base = (1.0 - a) / (1.0 + a)
    ror = base ** units_to_ruin
    return max(0.0, min(1.0, ror))


# ══════════════════════════════════════════════════════════════════
# 2. RISK GATES — 11 道风险门控（全部纯函数）
# ══════════════════════════════════════════════════════════════════

GateResult = Dict[str, Any]  # {pass: bool, reason?: str}


class GateContext:
    """传给所有风险门控的上下文。"""
    def __init__(
        self,
        confidence: float,
        current_positions: List[Dict[str, Any]],
        trade_notional_usd: float,
        daily_pnl: float,
        market_volume_24h_usd: float,
        coin: str,
        trade_side: str,  # 'long' | 'short'
        has_binary_news_risk: bool,
        equity: float,
        total_open_notional: float,
        composite_score: float = 0.0,
        momentum_burst_fired: bool = False,
        slow_burn_fired: bool = False,
        whale_signal_fired: bool = False,
        binary_news_match: str = "",
        peak_daily_pnl: float = 0.0,
    ):
        self.confidence = confidence
        self.current_positions = current_positions
        self.trade_notional_usd = trade_notional_usd
        self.daily_pnl = daily_pnl
        self.peak_daily_pnl = peak_daily_pnl
        self.market_volume_24h_usd = market_volume_24h_usd
        self.coin = coin
        self.trade_side = trade_side
        self.has_binary_news_risk = has_binary_news_risk
        self.equity = equity
        self.total_open_notional = total_open_notional
        self.composite_score = composite_score
        self.momentum_burst_fired = momentum_burst_fired
        self.slow_burn_fired = slow_burn_fired
        self.whale_signal_fired = whale_signal_fired
        self.binary_news_match = binary_news_match


def confidence_gate(ctx: GateContext, min_confidence: float) -> GateResult:
    if ctx.confidence >= min_confidence:
        return {"pass": True}
    return {"pass": False, "reason": f"confidence {ctx.confidence:.2f} < {min_confidence}"}


def max_concurrent_positions_gate(ctx: GateContext, max_concurrent: int) -> GateResult:
    if len(ctx.current_positions) < max_concurrent:
        return {"pass": True}
    return {"pass": False, "reason": f"max positions reached ({len(ctx.current_positions)}/{max_concurrent})"}


def per_trade_notional_cap_gate(ctx: GateContext, cap_usd: float) -> GateResult:
    cap = float(cap_usd or 0)
    if cap <= 0:
        return {"pass": True}
    precision_tolerance = max(0.25, cap * 0.005)
    if ctx.trade_notional_usd <= cap + precision_tolerance:
        return {"pass": True}
    return {"pass": False, "reason": f"trade notional ${ctx.trade_notional_usd:.2f} exceeds cap ${cap:.2f}"}


def daily_loss_kill_switch(ctx: GateContext, max_daily_loss: float) -> GateResult:
    if ctx.daily_pnl > max_daily_loss:
        return {"pass": True}
    return {"pass": False, "reason": f"daily loss killswitch triggered (PnL ${ctx.daily_pnl:.0f} <= ${max_daily_loss})"}


def daily_giveback_gate(ctx: GateContext, halt_pct: float, min_peak_usd: float) -> GateResult:
    """锁住盈利日：一旦当日 PnL 达到峰值 >= min_peak_usd，若随后回撤
    超过 halt_pct 即禁止新开仓，让赢的一天不会全部回吐。已有持仓继续
    走自己的止损，只停开新仓。halt_pct<=0 时禁用。"""
    if halt_pct <= 0 or ctx.peak_daily_pnl < min_peak_usd:
        return {"pass": True}
    floor = ctx.peak_daily_pnl * (1.0 - halt_pct)
    if ctx.daily_pnl <= floor:
        return {"pass": False,
                "reason": (f"daily give-back halt: PnL ${ctx.daily_pnl:.0f} retraced "
                           f">{halt_pct*100:.0f}% from peak ${ctx.peak_daily_pnl:.0f} "
                           f"(floor ${floor:.0f}) — no new entries until UTC roll")}
    return {"pass": True}


def market_liquidity_floor(ctx: GateContext, min_volume: float,
                           min_volume_hip3: Optional[float] = None) -> GateResult:
    """阻止在流动性不足的市场交易（24h 名义成交额地板）。"""
    is_hip3 = ":" in (ctx.coin or "")
    floor = (min_volume_hip3 if (is_hip3 and min_volume_hip3 is not None) else min_volume)
    if ctx.market_volume_24h_usd >= floor:
        return {"pass": True}
    return {"pass": False, "reason": f"market 24h volume ${ctx.market_volume_24h_usd/1e6:.2f}M below floor ${floor/1e6:.2f}M"}


def short_liquidity_floor(ctx: GateContext, min_short_volume: float) -> GateResult:
    """空头需要更多流动性——薄市场会被挤压（squeeze）。仅对空头生效。
    数据：空头流血单 24h 成交中位数 ~$13M，空头赢家 ~$223M（17x 差）。"""
    if ctx.trade_side != "short" or not min_short_volume:
        return {"pass": True}
    if ctx.market_volume_24h_usd >= min_short_volume:
        return {"pass": True}
    return {"pass": False,
            "reason": (f"short on thin market: 24h vol ${ctx.market_volume_24h_usd/1e6:.1f}M "
                       f"< short floor ${min_short_volume/1e6:.0f}M (squeeze risk)")}


def coin_allowlist_gate(ctx: GateContext, allowlist: List[str], blocklist: List[str]) -> GateResult:
    if blocklist and ctx.coin in blocklist:
        return {"pass": False, "reason": f"{ctx.coin} is on the coin blocklist"}
    if allowlist and ctx.coin not in allowlist:
        return {"pass": False, "reason": f"{ctx.coin} not on the allowlist"}
    return {"pass": True}


def cooldown_gate(ctx: GateContext, last_trade_time: Optional[int], cooldown_min: float) -> GateResult:
    if last_trade_time is None:
        return {"pass": True}
    elapsed = (int(time.time() * 1000) - last_trade_time) / 60_000
    if elapsed >= cooldown_min:
        return {"pass": True}
    return {"pass": False, "reason": f"cooldown active ({int(cooldown_min - elapsed)}min remaining)"}


def opposite_direction_guard(ctx: GateContext) -> GateResult:
    """禁止对已持仓的标的任何再入场：持仓只由 DSL 引擎 + 周期平仓检查
    管理，永不翻单（反向=不自动翻转），也永不加仓（同向=失控金字塔）。"""
    existing = next((p for p in ctx.current_positions if p["coin"] == ctx.coin), None)
    if not existing:
        return {"pass": True}
    if existing["side"] != ctx.trade_side:
        return {"pass": False, "reason": f"opposite position exists ({ctx.coin} {existing['side']}) — no auto-flip"}
    return {"pass": False, "reason": f"already holding {ctx.coin} {existing['side']} — no pyramid/re-entry"}


_CRYPTO_COINS = frozenset([
    "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "MATIC", "LINK",
    "DOT", "UNI", "ATOM", "NEAR", "FTM", "APT", "ARB", "OP", "INJ", "TIA",
    "SUI", "SEI", "WIF", "PEPE", "BONK", "FLOKI", "TRX", "LTC", "BCH", "ETC",
    "XLM", "ALGO", "AAVE", "MKR", "SNX", "CRV", "COMP", "YFI", "SUSHI", "1INCH",
])


def correlation_cap(ctx: GateContext, max_crypto_correlated: int) -> GateResult:
    if ctx.trade_side != "long":
        return {"pass": True}
    existing_crypto_long = sum(
        1 for p in ctx.current_positions
        if p["coin"] in _CRYPTO_COINS and p["side"] == "long"
    )
    if existing_crypto_long < max_crypto_correlated:
        return {"pass": True}
    return {"pass": False, "reason": f"crypto long correlation cap reached ({existing_crypto_long}/{max_crypto_correlated})"}


def equity_risk_cap(ctx: GateContext, max_total_notional_pct: float) -> GateResult:
    max_notional = ctx.equity * max_total_notional_pct
    projected_notional = ctx.total_open_notional + ctx.trade_notional_usd
    if projected_notional <= max_notional:
        return {"pass": True}
    return {"pass": False,
            "reason": f"total notional ${projected_notional:.0f} would exceed {max_total_notional_pct*100:.0f}% of equity (${max_notional:.0f})"}


def market_regime_gate(ctx: GateContext, regime: str, funding_regime: str = "NEUTRAL",
                       counter_regime_min_conf: float = 0.7,
                       block_counter_trend_bypass: bool = False,
                       crowded_with_min_conf: float = 0.0) -> GateResult:
    """市场状态门控（regime 由外部传入，保持纯函数）。

    - 顺 regime → 放行
    - regime 中性 → 放行
    - 逆势 → 需满足：confidence >= counter_regime_min_conf 或
      composite_score >= 50 或 自身信号（momentum/slow_burn/whale）

    资金费率拥挤度对称覆盖：against_funding 提高门槛（conf>=0.85 或
    score>=60）；with_crowd（挤入拥挤盘）需 elevated conviction 防挤压。
    """
    against_funding = (
        (funding_regime == "SHORT_CROWDED" and ctx.trade_side == "long") or
        (funding_regime == "LONG_CROWDED" and ctx.trade_side == "short")
    )
    with_crowd = (
        (funding_regime == "SHORT_CROWDED" and ctx.trade_side == "short") or
        (funding_regime == "LONG_CROWDED" and ctx.trade_side == "long")
    )

    effective_min_conf = counter_regime_min_conf
    effective_min_score = 50.0
    if against_funding:
        effective_min_conf = max(counter_regime_min_conf, 0.85)
        effective_min_score = 60.0

    base = {"regime": regime, "funding": funding_regime,
            "against_funding": against_funding, "counter_trend": False}

    aligned = (regime == "up" and ctx.trade_side == "long") or \
              (regime == "down" and ctx.trade_side == "short")
    if aligned and not against_funding:
        if with_crowd and crowded_with_min_conf > 0 and ctx.confidence < crowded_with_min_conf:
            return {"pass": False, "via": "crowded_squeeze",
                    **{**base, "with_crowd": True},
                    "reason": (f"with-crowd {ctx.trade_side} into {funding_regime} "
                               f"(squeeze risk) — need conf >= {crowded_with_min_conf:.2f}, "
                               f"have {ctx.confidence:.2f}")}
        return {"pass": True, "via": "aligned", **{**base, "with_crowd": with_crowd}}

    if regime == "neutral" and not against_funding:
        return {"pass": True, "via": "neutral", **base}

    base["counter_trend"] = not aligned
    if ctx.confidence >= effective_min_conf:
        return {"pass": True, "via": "confidence", **base}
    if ctx.composite_score >= effective_min_score:
        return {"pass": True, "via": "composite", **base}
    if (ctx.momentum_burst_fired or ctx.slow_burn_fired or ctx.whale_signal_fired) \
            and not block_counter_trend_bypass:
        trig = ("momentum_burst" if ctx.momentum_burst_fired
                else "slow_burn" if ctx.slow_burn_fired else "whale")
        return {"pass": True, "via": f"trigger:{trig}", **base}

    blocked_via = "blocked_bypass" if block_counter_trend_bypass else "blocked"
    return {"pass": False, "via": blocked_via, **base,
            "reason": (f"counter-regime {ctx.trade_side} vs {regime} trend "
                       f"(funding={funding_regime}) — need conf >= {effective_min_conf:.2f} "
                       f"or score >= {effective_min_score:.0f}")}


def news_blackout_gate(ctx: GateContext) -> GateResult:
    if not ctx.has_binary_news_risk:
        return {"pass": True}
    detail = f" — {ctx.binary_news_match}" if ctx.binary_news_match else ""
    return {"pass": False,
            "reason": f"binary news risk (Fed/earnings/hack in recent news){detail} — standing down"}


def eval_all_gates(ctx: GateContext, config: Dict[str, Any],
                   last_trade_time: Optional[int] = None,
                   regime: str = "neutral",
                   funding_regime: str = "NEUTRAL") -> Dict[str, Any]:
    """评估全部风险门控并收集结果（不短路，全部评估以便遥测）。"""
    results = {}
    results["confidence"] = confidence_gate(ctx, float(config.get("min_confidence", 0.8)))
    results["max_concurrent"] = max_concurrent_positions_gate(ctx, config.get("max_concurrent", 3))
    results["notional_cap"] = per_trade_notional_cap_gate(ctx, config.get("max_trade_notional_usd", 300))
    results["daily_loss"] = daily_loss_kill_switch(ctx, config.get("max_daily_loss_usd", -100))
    results["daily_giveback"] = daily_giveback_gate(
        ctx, float(config.get("daily_giveback_halt_pct", 0.0) or 0.0),
        float(config.get("daily_giveback_min_peak_usd", 20.0) or 0.0))
    results["liquidity"] = market_liquidity_floor(
        ctx, config.get("min_market_volume_usd", 5_000_000),
        config.get("min_hip3_volume_usd", 500_000))
    results["short_liquidity"] = short_liquidity_floor(ctx, config.get("min_short_volume_usd", 0) or 0)
    results["coin_filter"] = coin_allowlist_gate(ctx, config.get("coin_allowlist", []), config.get("coin_blocklist", []))
    results["cooldown"] = cooldown_gate(ctx, last_trade_time, config.get("cooldown_min", 60))
    results["opposite_guard"] = opposite_direction_guard(ctx)
    results["correlation"] = correlation_cap(ctx, int(config.get("max_crypto_long_correlated", 2)))
    results["equity_risk"] = equity_risk_cap(ctx, config.get("max_total_notional_pct", 1.0))
    results["market_regime"] = market_regime_gate(
        ctx, regime, funding_regime,
        float(config.get("counter_regime_min_conf", 0.7)),
        bool(config.get("block_counter_trend_bypass", False)),
        float(config.get("crowded_with_min_conf", 0.0) or 0.0))
    results["news"] = news_blackout_gate(ctx)

    block_reasons = []
    blocked = False
    for key, result in results.items():
        if not result.get("pass"):
            blocked = True
            block_reasons.append(result.get("reason", key))
    return {"results": results, "blocked": blocked, "block_reasons": block_reasons}


# ══════════════════════════════════════════════════════════════════
# 3. DSL EXIT — 两阶段动态退出引擎
# ══════════════════════════════════════════════════════════════════


@dataclass
class RetraceTier:
    """一个利润层级及其回撤阈值。例：价格高于入场 10% 时，回撤阈值 30%——
    floor 跟踪在 entry + (peak - entry) * (1 - 0.30)。"""
    pct_above_entry: float
    retrace_threshold: float


@dataclass
class ExitVerdict:
    exit: bool = False
    reason: str = ""
    floor_price: Optional[float] = None
    peak_price: Optional[float] = None
    phase: str = ""          # "phase1" | "phase2" | "timeout"
    unrealized_pct: float = 0.0  # 现货价格变动%，非杠杆
    coin: str = ""
    position_side: str = ""  # "long" | "short"
    leverage: int = 1


@dataclass
class ExitPolicy:
    """DSL 退出策略配置。

    调优档位：
      Conservative: max_loss_pct=5, retrace=10, protect=3, hard_timeout=360min
      Moderate:     max_loss_pct=2.5, retrace=7, protect=1.5, hard_timeout=180min
      Aggressive:   max_loss_pct=1.5, retrace=5, protect=0.8, hard_timeout=90min
    """
    max_loss_pct: float = 2.5       # 最大现货%亏损（硬止损）
    max_loss_roe_pct: float = 50.0  # 最大 ROE% 亏损（杠杆感知安全网，min 取更紧者）
    protect_pct: float = 1.5        # 价格须涨过入场此%才进入 Phase2
    retrace_threshold: float = 0.30  # 回吐峰值利润的 30%（Phase2 默认）
    hard_timeout_minutes: float = 180.0  # 超时紧急退出
    breakeven_trigger_pct: float = 0.0   # 峰值现货%触发保本锁（0=关）
    breakeven_lock_pct: float = 0.0      # 触发后 floor 锁定的现货%
    atr_stop_enabled: bool = False       # ATR 缩放主止损
    atr_stop_mult: float = 1.5
    atr_stop_floor_pct: float = 1.0
    atr_stop_ceiling_pct: float = 4.0
    stale_flat_timeout_minutes: float = 0.0  # 从未进入 Phase2 的漂移仓超时平仓（0=关）
    phase2_tiers: List[RetraceTier] = field(default_factory=lambda: [
        RetraceTier(5.0, 0.30),   # 5% 利润 → 回吐 30%
        RetraceTier(10.0, 0.40),  # 10% 利润 → 锁更紧，回吐 40%
        RetraceTier(20.0, 0.50),  # 20% 利润 → 更紧
        RetraceTier(50.0, 0.60),  # 50% 利润 → 锁住大部分
    ])
    consecutive_breaches_required: int = 1  # 连续跌破 floor 次数才退出
    noise_band_enabled: bool = False        # 噪声带抑制（首层级下方不因噪声退出）
    noise_band_atr_mult: float = 1.0


class DSLTracker:
    """单持仓的 DSL 状态追踪。每个价格 tick 调用 check(mark_px)。"""

    def __init__(self, coin: str, side: str, entry_px: float,
                 entry_time: Optional[float] = None,
                 policy: Optional[ExitPolicy] = None,
                 leverage: int = 1, entry_atr_pct: float = 0.0):
        self.coin = coin
        self.side = side
        self.entry_px = entry_px
        self.entry_time = entry_time if entry_time is not None else time.time()
        self.policy = policy or ExitPolicy()
        self.leverage = int(leverage) if leverage else 1
        self.entry_atr_pct = float(entry_atr_pct or 0.0)
        self.peak_px = entry_px
        self.consecutive_breaches = 0
        self._last_floor: Optional[float] = None

    def is_long(self) -> bool:
        return self.side == "long"

    def _unrealized_pct(self, mark_px: float) -> float:
        if self.is_long():
            return (mark_px - self.entry_px) / self.entry_px * 100
        return (self.entry_px - mark_px) / self.entry_px * 100

    def _verdict(self, **kwargs: Any) -> ExitVerdict:
        return ExitVerdict(coin=self.coin, position_side=self.side,
                           leverage=self.leverage, **kwargs)

    def _active_tier(self, mark_px: float) -> RetraceTier:
        upct = self._unrealized_pct(mark_px)
        active = RetraceTier(0.0, self.policy.retrace_threshold)
        for tier in self.policy.phase2_tiers:
            if upct >= tier.pct_above_entry:
                active = tier
        return active

    def check(self, mark_px: float) -> ExitVerdict:
        """评估 DSL floor 对当前价格。每个 tick 调用。"""
        elapsed_min = (time.time() - self.entry_time) / 60
        upct = self._unrealized_pct(mark_px)
        is_long = self.is_long()
        pol = self.policy

        # 更新峰值（多头最高价 / 空头最低价）
        peak_changed = False
        if is_long and mark_px > self.peak_px:
            self.peak_px = mark_px
            peak_changed = True
        elif not is_long and mark_px < self.peak_px:
            self.peak_px = mark_px
            peak_changed = True

        lev = max(1, self.leverage)
        spot_cap = pol.max_loss_pct
        if pol.atr_stop_enabled and self.entry_atr_pct > 0:
            spot_cap = min(max(self.entry_atr_pct * pol.atr_stop_mult,
                               pol.atr_stop_floor_pct),
                           pol.atr_stop_ceiling_pct)
        effective_max_loss = min(spot_cap, pol.max_loss_roe_pct / lev)

        # 陈旧漂移仓超时
        if pol.stale_flat_timeout_minutes > 0 and elapsed_min >= pol.stale_flat_timeout_minutes:
            if is_long:
                peak_profit = (self.peak_px - self.entry_px) / self.entry_px * 100
            else:
                peak_profit = (self.entry_px - self.peak_px) / self.entry_px * 100
            if peak_profit < pol.protect_pct:
                return self._verdict(
                    exit=True,
                    reason=(f"stale_flat_timeout ({elapsed_min:.0f}min below protect; "
                            f"peak {peak_profit:.2f}% < {pol.protect_pct}%)"),
                    floor_price=None, peak_price=self.peak_px, phase="timeout",
                    unrealized_pct=upct)

        # 硬超时
        if elapsed_min >= pol.hard_timeout_minutes:
            return self._verdict(exit=True, reason=f"hard_timeout ({elapsed_min:.0f}min)",
                                 floor_price=None, peak_price=self.peak_px,
                                 phase="timeout", unrealized_pct=upct)

        # 计算 floor
        if is_long:
            profit_pct = (mark_px - self.entry_px) / self.entry_px * 100
            loss_pct = (self.entry_px - mark_px) / self.entry_px * 100
            if loss_pct >= effective_max_loss:
                roe_loss = loss_pct * lev
                return self._verdict(
                    exit=True,
                    reason=(f"max_loss ({loss_pct:.2f}% spot / {roe_loss:.1f}% ROE "
                            f">= {effective_max_loss:.2f}% spot cap; "
                            f"spot_cap={spot_cap:.2f}{'[atr]' if (pol.atr_stop_enabled and self.entry_atr_pct > 0) else ''}, "
                            f"roe_cap={pol.max_loss_roe_pct}/{lev}x)"),
                    floor_price=self.entry_px * (1 - effective_max_loss / 100),
                    peak_price=self.peak_px, phase="phase1", unrealized_pct=upct)
            if profit_pct >= pol.protect_pct:
                tier = self._active_tier(self.peak_px)
                profit_range = self.peak_px - self.entry_px
                floor = self.entry_px + profit_range * (1 - tier.retrace_threshold)
            else:
                floor = self.entry_px * (1 - effective_max_loss / 100)
        else:
            profit_pct = (self.entry_px - mark_px) / self.entry_px * 100
            loss_pct = (mark_px - self.entry_px) / self.entry_px * 100
            if loss_pct >= effective_max_loss:
                roe_loss = loss_pct * lev
                return self._verdict(
                    exit=True,
                    reason=(f"max_loss ({loss_pct:.2f}% spot / {roe_loss:.1f}% ROE "
                            f">= {effective_max_loss:.2f}% spot cap)"),
                    floor_price=self.entry_px * (1 + effective_max_loss / 100),
                    peak_price=self.peak_px, phase="phase1", unrealized_pct=upct)
            if profit_pct >= pol.protect_pct:
                tier = self._active_tier(self.peak_px)
                profit_range = self.entry_px - self.peak_px
                floor = self.entry_px - profit_range * (1 - tier.retrace_threshold)
            else:
                floor = self.entry_px * (1 + effective_max_loss / 100)

        # 保本棘轮
        if pol.breakeven_trigger_pct > 0:
            if is_long:
                peak_profit_pct = (self.peak_px - self.entry_px) / self.entry_px * 100
                if peak_profit_pct >= pol.breakeven_trigger_pct:
                    floor = max(floor, self.entry_px * (1 + pol.breakeven_lock_pct / 100))
            else:
                peak_profit_pct = (self.entry_px - self.peak_px) / self.entry_px * 100
                if peak_profit_pct >= pol.breakeven_trigger_pct:
                    floor = min(floor, self.entry_px * (1 - pol.breakeven_lock_pct / 100))

        # floor 永不回退（多头只升 / 空头只降）
        prev_floor = self._last_floor
        if prev_floor is not None:
            if is_long:
                floor = max(floor, prev_floor)
            else:
                floor = min(floor, prev_floor)
        self._last_floor = floor

        # floor 跌破检查
        breached = (is_long and mark_px < floor) or (not is_long and mark_px > floor)

        # 噪声带抑制（首层级下方）
        if breached and pol.noise_band_enabled and self.entry_atr_pct > 0:
            first_tier_pct = min((t.pct_above_entry for t in pol.phase2_tiers), default=3.0)
            peak_profit_pct = (abs(self.peak_px - self.entry_px) / self.entry_px) * 100
            pullback_pct = (abs(self.peak_px - mark_px) / self.entry_px) * 100
            band = pol.noise_band_atr_mult * self.entry_atr_pct
            if peak_profit_pct < first_tier_pct and pullback_pct <= band:
                self.consecutive_breaches = 0
                return self._verdict(
                    exit=False, reason="noise_band_hold", floor_price=floor,
                    peak_price=self.peak_px, phase="phase1", unrealized_pct=upct)

        if breached:
            self.consecutive_breaches += 1
            if self.consecutive_breaches >= pol.consecutive_breaches_required:
                return self._verdict(
                    exit=True,
                    reason=f"floor_breach ({self.consecutive_breaches}x consec, floor={floor:.2f})",
                    floor_price=floor, peak_price=self.peak_px,
                    phase="phase2" if self._unrealized_pct(mark_px) >= pol.protect_pct else "phase1",
                    unrealized_pct=upct)
        else:
            self.consecutive_breaches = 0

        return self._verdict(
            exit=False, reason="", floor_price=self._last_floor,
            peak_price=self.peak_px,
            phase="phase2" if self._unrealized_pct(mark_px) >= pol.protect_pct else "phase1",
            unrealized_pct=upct)
