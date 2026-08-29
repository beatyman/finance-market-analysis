#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""trade_entry_engine 单元测试：R:R 约束、不追高、仓位计算。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, '..', 'scripts')
sys.path.insert(0, SCRIPTS)

from trade_entry_engine import (
    EngineConfig, Candidate, evaluate_candidate,
    safe_rr, max_entry_for_rr, size_position, classify_signal_strength,
)


def _cfg():
    return EngineConfig(account_equity=1_000_000, risk_per_trade=0.005)


def test_max_entry_for_rr_math():
    """解 R:R 约束：entry_max = (target + rr*stop) / (1 + rr)。"""
    stop, target, rr = 10.0, 15.0, 2.5
    e = max_entry_for_rr(stop, target, rr)
    assert abs(e - (15.0 + 2.5 * 10.0) / 3.5) < 1e-6
    assert safe_rr(e, stop, target) >= rr - 1e-9


def test_no_chase_watch():
    """现价远高于最大接受价 -> WATCH（不追高）。"""
    c = Candidate(code='000001', name='平安银行', price=12.0,
                  xgb_score=55, score_3d=50, setup_quality=65, data_confidence=0.9,
                  support=10.5, structural_stop=10.0, target1=15.0, atr=0.5)
    plan = evaluate_candidate(c, _cfg())
    assert plan.state == 'WATCH'
    assert '不追' in plan.reason or '高于' in plan.reason


def test_triggered_long():
    """价格在理想区 + 触发通过 -> 允许买入。"""
    c = Candidate(code='000001', name='平安银行', price=10.6,
                  xgb_score=60, score_3d=55, setup_quality=75, data_confidence=0.9,
                  support=10.5, structural_stop=10.0, target1=15.0, atr=0.3,
                  lower_tf_higher_low=True, lower_tf_macd_positive=True,
                  lower_tf_breakout=True, lower_tf_volume_confirm=False)
    plan = evaluate_candidate(c, _cfg())
    # 价格 10.6 距 support 10.5 仅 0.33 ATR，在理想区附近
    assert plan.state in ('TRIGGERED_LONG', 'SETUP')
    assert plan.suggested_shares > 0 or plan.state == 'SETUP'


def test_size_position_rounding():
    """手数取整到 100 股，且不超过风险预算。"""
    cfg = _cfg()
    risk_budget, shares, cap, loss = size_position(
        entry=10.0, stop=9.5, strength='NORMAL', cfg=cfg)
    assert risk_budget == 5000.0
    # per_share_risk = 0.5 -> 风险可买 10000 股，cap 200k -> 20000 股，取 min 10000
    assert shares == 10000
    assert shares % 100 == 0


def test_signal_strength_very_strong():
    """只有 ML 和 setup 都高才 VERY_STRONG，单一强分不越级。"""
    c = Candidate(code='000001', name='X', price=10.0,
                  xgb_score=90, score_3d=40, setup_quality=60, data_confidence=0.95)
    # xgb 90 但 3d 40 和 setup 60 低 -> 不是 VERY_STRONG
    assert classify_signal_strength(c) in ('STRONG', 'NORMAL')


if __name__ == '__main__':
    test_max_entry_for_rr_math()
    test_no_chase_watch()
    test_triggered_long()
    test_size_position_rounding()
    test_signal_strength_very_strong()
    print('trade_entry_engine tests: ALL PASS')
