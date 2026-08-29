#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标签一致性测试：Triple-Barrier meta-label + daily IC + 超额收益。"""
import os
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, '..', 'scripts')
sys.path.insert(0, SCRIPTS)

from labels import (compute_atr, build_meta_labels, daily_ic,
                    build_forward_excess_targets)


def _snap(code='000001', price=10.0, idx=60, closes=None, highs=None, lows=None,
          all_closes=None, all_highs=None, all_lows=None, date='2026-01-01'):
    s = SimpleNamespace()
    s.code = code
    s.date = date
    s.idx = idx
    s.is_buy = True
    s.price = price
    n = len(closes) if closes is not None else 60
    s.closes = np.asarray(closes if closes is not None else np.full(n, price), float)
    s.highs = np.asarray(highs if highs is not None else s.closes + 0.1, float)
    s.lows = np.asarray(lows if lows is not None else s.closes - 0.1, float)
    s.all_closes = np.asarray(all_closes if all_closes is not None else s.closes, float)
    s.all_highs = np.asarray(all_highs if all_highs is not None else s.highs, float)
    s.all_lows = np.asarray(all_lows if all_lows is not None else s.lows, float)
    return s


def _series_with_future_upper():
    """未来第2根触及 upper（高开+大涨）。"""
    closes = np.full(80, 10.0)
    closes[61] = 12.0   # 未来第1根 (idx 60 之后)
    closes[62] = 11.0
    highs = closes + 0.1
    lows = closes - 0.1
    return closes, highs, lows


def test_atr_positive():
    closes = np.linspace(10, 12, 60)
    highs = closes + 0.3
    lows = closes - 0.3
    atr = compute_atr(highs, lows, closes)
    assert np.isfinite(atr) and atr > 0


def test_barrier_upper_hit():
    """未来先触及 upper -> label 1。"""
    closes = np.full(80, 10.0)
    closes[61] = 13.0  # 远超 upper (10 + 1.5*ATR)
    highs = closes + 0.01
    lows = closes - 0.01
    s = _snap(closes=closes[:61], highs=highs[:61], lows=lows[:61],
              all_closes=closes, all_highs=highs, all_lows=lows)
    df = build_meta_labels([s])
    assert df['label'].iloc[0] == 1
    assert df['hit_bar'].iloc[0] == 'upper'


def test_barrier_lower_hit():
    """未来先触及 lower -> label 0。"""
    closes = np.full(80, 10.0)
    closes[61] = 7.0  # 远低于 lower (10 - 1.0*ATR)
    highs = closes + 0.01
    lows = closes - 0.01
    s = _snap(closes=closes[:61], highs=highs[:61], lows=lows[:61],
              all_closes=closes, all_highs=highs, all_lows=lows)
    df = build_meta_labels([s])
    assert df['label'].iloc[0] == 0
    assert df['hit_bar'].iloc[0] == 'lower'


def test_barrier_timeout():
    """未来 10 根都未触及 barrier -> timeout (label NaN, is_timeout True)。"""
    rng = np.random.RandomState(42)
    # 历史有明确波动 => ATR ≈ 0.6，upper=10.9 / lower=9.4
    hist = 10 + rng.randn(61) * 0.3
    hist_high = hist + 0.3
    hist_low = hist - 0.3
    # 未来：窄幅回到 10，不触及 upper/lower
    future = np.full(10, 10.0)
    future_high = future + 0.05
    future_low = future - 0.05
    all_closes = np.concatenate([hist, future])
    all_highs = np.concatenate([hist_high, future_high])
    all_lows = np.concatenate([hist_low, future_low])
    s = _snap(closes=hist, highs=hist_high, lows=hist_low,
              all_closes=all_closes, all_highs=all_highs, all_lows=all_lows)
    df = build_meta_labels([s])
    assert bool(df['is_timeout'].iloc[0]) is True
    assert pd.isna(df['label'].iloc[0])


def test_daily_ic_shape_and_sign():
    """daily IC：按日期分组，输出 date/ic/n。构造正相关 => ic > 0。"""
    rng = np.random.RandomState(1)
    n = 200
    score = rng.randn(n)
    label = (score + rng.randn(n) * 0.5 > 0).astype(int)
    df = pd.DataFrame({'date': np.repeat(['d1', 'd2', 'd3', 'd4'], 50),
                       'score': score, 'label': label})
    ic = daily_ic(df, 'score', 'label')
    assert list(ic.columns) == ['date', 'ic', 'n']
    assert len(ic) == 4
    assert ic['ic'].mean() > 0, '正相关特征应有正 IC'


def test_forward_excess():
    """超额收益 = 个股10日收益 - benchmark 10日收益。"""
    closes = np.full(80, 10.0)
    closes[70] = 11.0  # 10日后涨 10%
    s = _snap(closes=closes[:61], all_closes=closes)
    bench = {s.date: 3.0}  # benchmark 同期涨 3%
    df = build_forward_excess_targets([s], benchmark_returns=bench, horizon=10)
    assert abs(df['forward_ret_10d'].iloc[0] - 10.0) < 0.5
    assert abs(df['excess_ret_10d'].iloc[0] - 7.0) < 0.5


if __name__ == '__main__':
    test_atr_positive()
    test_barrier_upper_hit()
    test_barrier_lower_hit()
    test_barrier_timeout()
    test_daily_ic_shape_and_sign()
    test_forward_excess()
    print('label consistency tests: ALL PASS')
