#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""信号新鲜度测试：_bsp_classify 提取最新 BSP 日期 + signal_age 计算。"""
import os
import sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CHANPY = os.path.join(HERE, '..', 'chanpy')
sys.path.insert(0, CHANPY)

from chan_engine_v5 import _bsp_classify, analyze


def _pts(*items):
    return [{'point_type': t, 'date': pd.Timestamp(d), 'full_name': n}
            for (t, d, n) in items]


def test_latest_bsp_date_buy():
    """最新 buy 点日期被正确提取。"""
    pts = _pts(('buy', '2026-08-20', '二买'), ('buy', '2026-08-25', '三买'))
    bsp_buy, bsp_types, latest = _bsp_classify(pts, 10.0, [])
    assert bsp_buy is True
    assert latest == pd.Timestamp('2026-08-25')


def test_latest_bsp_date_mixed():
    """buy/sell 混合时取两者最新日期。"""
    pts = _pts(('buy', '2026-08-20', '二买'), ('sell', '2026-08-27', '二卖'))
    bsp_buy, bsp_types, latest = _bsp_classify(pts, 10.0, [])
    assert latest == pd.Timestamp('2026-08-27')
    assert 'Sell-二卖' in bsp_types


def test_no_bsp_latest_none():
    """无 BSP 时 latest_bsp_date 为 None。"""
    bsp_buy, bsp_types, latest = _bsp_classify([], 10.0, [])
    assert latest is None


def test_analyze_returns_fresh_attrs():
    """analyze 返回的 cur 带 is_fresh_bsp / signal_age_bars / bsp_event_date。"""
    import numpy as np
    n = 80
    dates = pd.date_range('2026-06-01', periods=n).strftime('%Y-%m-%d').tolist()
    rng = np.random.RandomState(7)
    closes = np.cumsum(rng.randn(n) * 0.1) + 20
    opens = closes + rng.randn(n) * 0.05
    highs = np.maximum(opens, closes) + 0.1
    lows = np.minimum(opens, closes) - 0.1
    cur, bsp_buy, bsp_types, px, zs_str, trend = analyze(dates, opens, closes, highs, lows, '000001')
    assert hasattr(cur, 'is_fresh_bsp')
    assert hasattr(cur, 'signal_age_bars')
    assert hasattr(cur, 'bsp_event_date')
    # signal_age_bars 要么是 None（无BSP），要么是 >= 0 的整数
    if cur.signal_age_bars is not None:
        assert cur.signal_age_bars >= 0
        assert isinstance(cur.is_fresh_bsp, bool)


if __name__ == '__main__':
    test_latest_bsp_date_buy()
    test_latest_bsp_date_mixed()
    test_no_bsp_latest_none()
    test_analyze_returns_fresh_attrs()
    print('signal freshness tests: ALL PASS')
