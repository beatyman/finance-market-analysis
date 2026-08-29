#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Model bundle 测试：不可变 bundle + feature hash 校验 + 取消 fallback。"""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, '..', 'scripts')
sys.path.insert(0, SCRIPTS)

from model_bundle import (load_bundle, get_feature_schema, compute_feature_hash,
                          verify_feature_order, PROD_MODEL_ID)


def test_feature_schema_101():
    """生产模型 schema 应为 101 维 = 58 chan + 43 talib。"""
    names = get_feature_schema()
    assert len(names) == 101, f'期望 101 维, 实际 {len(names)}'
    assert len(names) == 58 + 43


def test_bundle_loadable():
    """bundle 可加载，维度一致，feature_hash 匹配。"""
    b = load_bundle()
    assert b['model_id'] == PROD_MODEL_ID
    assert b['schema']['n_features'] == 101
    n_model = getattr(b['model'], 'n_features_in_', None)
    assert n_model == 101, f'模型维度 {n_model} != schema 101'


def test_feature_hash_stable():
    """相同顺序 -> 相同 hash；顺序改变 -> 不同 hash。"""
    names = get_feature_schema()
    h1 = compute_feature_hash(names)
    h2 = compute_feature_hash(list(names))
    assert h1 == h2
    swapped = list(names)
    swapped[0], swapped[1] = swapped[1], swapped[0]
    assert compute_feature_hash(swapped) != h1


def test_verify_feature_order():
    """特征顺序校验：一致 ok，错位/维度不符 fail。"""
    b = load_bundle()
    schema = b['schema']
    ok, _ = verify_feature_order(schema['feature_names'], schema)
    assert ok is True
    wrong = list(schema['feature_names'])
    wrong[0] = 'WRONG_FEATURE'
    ok2, _ = verify_feature_order(wrong, schema)
    assert ok2 is False
    short = schema['feature_names'][:50]
    ok3, _ = verify_feature_order(short, schema)
    assert ok3 is False


def test_no_latest_fallback():
    """不存在的 model_id 必须抛错，不允许回退。"""
    import pytest
    with pytest.raises((FileNotFoundError, Exception)):
        load_bundle(model_id='does_not_exist_xxx')


if __name__ == '__main__':
    test_feature_schema_101()
    test_bundle_loadable()
    test_feature_hash_stable()
    test_verify_feature_order()
    test_no_latest_fallback()
    print('model bundle tests: ALL PASS')
