#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""关键 import 回归测试（防止干净 clone 后 ImportError）。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
SCRIPTS = os.path.join(ROOT, 'scripts')
CHANPY = os.path.join(ROOT, 'chanpy')
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, CHANPY)


def test_universe_import():
    import universe  # noqa: F401
    assert hasattr(universe, 'get_csi300_members')


def test_chan_engine_v5_import():
    """chan_engine_v5 在 chanpy/ 目录，经 sys.path 加载。"""
    from chan_engine_v5 import analyze, get_bsp_label  # noqa: F401
    assert callable(analyze)
    assert callable(get_bsp_label)


def test_data_layer_import():
    import data  # noqa: F401
    assert hasattr(data, 'load_a_stocks')
    assert hasattr(data, 'fetch_kline_a')


if __name__ == '__main__':
    test_universe_import()
    test_chan_engine_v5_import()
    test_data_layer_import()
    print('import tests: ALL PASS')
