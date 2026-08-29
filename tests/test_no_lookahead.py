#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无泄漏测试：FeaturePipeline 的 fit 只在 train 上，transform 只读。"""
import os
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, '..', 'scripts')
sys.path.insert(0, SCRIPTS)

from feature_pipeline import FeaturePipeline


def _make_df(n=600, seed=0):
    rng = np.random.RandomState(seed)
    dates = np.repeat(pd.date_range('2026-01-01', periods=12), n // 12).astype(str)
    # 让 f_signal 与 label 有真实相关性（跨 train/test 都有）
    signal = rng.randn(n)
    df = pd.DataFrame({
        'date': dates,
        'label': (signal + rng.randn(n) > 0).astype(int),
        'f_signal': signal,
        'f_noise1': rng.randn(n),
        'f_noise2': rng.randn(n) * 3,
        'f_const': np.ones(n),
    })
    return df


def test_fit_deterministic_same_train():
    """相同 train -> 相同 fit 参数（winsor 阈值 / keep_features）。"""
    df = _make_df()
    dates = sorted(df['date'].unique())
    train = df[df['date'].isin(dates[:8])]
    p1 = FeaturePipeline().fit(train, ['f_signal', 'f_noise1', 'f_noise2', 'f_const'], 'label')
    p2 = FeaturePipeline().fit(train, ['f_signal', 'f_noise1', 'f_noise2', 'f_const'], 'label')
    assert p1.keep_features == p2.keep_features
    assert p1.winsor_bounds == p2.winsor_bounds


def test_winsor_bounds_from_train_only():
    """test 数据里放极端值，不影响 train 拟合的 winsor 阈值。"""
    df = _make_df()
    dates = sorted(df['date'].unique())
    train = df[df['date'].isin(dates[:8])].copy()
    test = df[df['date'].isin(dates[8:])].copy()
    p1 = FeaturePipeline().fit(train, ['f_signal', 'f_noise1', 'f_noise2'], 'label')
    # 在 test 注入极端值（10000x），train 不变
    test_extreme = test.copy()
    test_extreme['f_noise1'] = test_extreme['f_noise1'] * 10000
    p2 = FeaturePipeline().fit(train, ['f_signal', 'f_noise1', 'f_noise2'], 'label')
    assert p1.winsor_bounds == p2.winsor_bounds, 'test 极端值不得影响 train 的 winsor 阈值'


def test_transform_read_only():
    """transform 不改变 fit 参数（只读，不重新 fit）。"""
    df = _make_df()
    dates = sorted(df['date'].unique())
    train = df[df['date'].isin(dates[:8])]
    test = df[df['date'].isin(dates[8:])]
    p = FeaturePipeline().fit(train, ['f_signal', 'f_noise1', 'f_noise2'], 'label')
    before_bounds = dict(p.winsor_bounds)
    before_keep = list(p.keep_features)
    p.transform(train)
    p.transform(test)
    assert p.winsor_bounds == before_bounds, 'transform 后 winsor 阈值不得变化'
    assert p.keep_features == before_keep, 'transform 后 keep_features 不得变化'


def test_transform_deterministic():
    """同一输入两次 transform 结果一致（确定性）。"""
    df = _make_df()
    dates = sorted(df['date'].unique())
    train = df[df['date'].isin(dates[:8])]
    p = FeaturePipeline().fit(train, ['f_signal', 'f_noise1', 'f_noise2'], 'label')
    X1 = p.transform(train).values
    X2 = p.transform(train).values
    assert np.array_equal(X1, X2, equal_nan=True)


def test_save_load_roundtrip():
    """保存/加载后 transform 结果一致（bundle 工件可复现）。"""
    import tempfile
    df = _make_df()
    dates = sorted(df['date'].unique())
    train = df[df['date'].isin(dates[:8])]
    p = FeaturePipeline().fit(train, ['f_signal', 'f_noise1', 'f_noise2'], 'label')
    X1 = p.transform(train).values
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        path = f.name
    p.save(path)
    p2 = FeaturePipeline().load(path)
    X2 = p2.transform(train).values
    assert np.array_equal(X1, X2, equal_nan=True)
    os.unlink(path)


if __name__ == '__main__':
    test_fit_deterministic_same_train()
    test_winsor_bounds_from_train_only()
    test_transform_read_only()
    test_transform_deterministic()
    test_save_load_roundtrip()
    print('no-lookahead tests: ALL PASS')
