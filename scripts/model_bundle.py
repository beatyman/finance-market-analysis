#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模型不可变 Bundle：model + metadata + feature_schema + feature_hash

解决：
    - latest.pkl 自动 fallback（不可审计）
    - sorted(dict.keys()) 隐式特征顺序
    - metadata 不参与推理校验

核心：
    build_feature_schema()  -> 生成 feature_schema.json（101维 = 58 chan + 43 talib）
    load_bundle()           -> 加载模型 + 强校验 feature_hash，缺失即报错不回退
    verify_feature_order()  -> 推理特征顺序必须与 schema 一致
"""
import os
import json
import hashlib
import pickle

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
MODELS = os.path.join(ROOT, 'models')
REGISTRY = os.path.join(MODELS, 'registry')

# 当前生产模型（唯一入口，不再 latest fallback）
PROD_MODEL_ID = 'csi300_v2_20260829_001'


def _chan_feature_names():
    """58 个 chan 特征（与 scorer.extract_features 返回 keys 的 sorted 顺序一致）。"""
    from scorer import extract_features
    import numpy as np
    n = 100
    closes = np.linspace(10, 20, n)
    highs = closes * 1.02
    lows = closes * 0.98
    opens = closes * 1.01
    vols = np.full(n, 1e6)
    f = extract_features(closes, highs, lows, opens, vols, [], [], None)
    return sorted(f.keys())


def _talib_feature_names():
    """43 个 talib 特征（与 talib_features.get_talib_feature_names 一致）。"""
    from talib_features import get_talib_feature_names
    return list(get_talib_feature_names())


def get_feature_schema():
    """101 维特征顺序 = 58 chan (sorted) + 43 talib。"""
    return _chan_feature_names() + _talib_feature_names()


def compute_feature_hash(feature_names):
    """feature_names 顺序的稳定 hash。"""
    payload = json.dumps(feature_names, ensure_ascii=False, sort_keys=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]


def build_feature_schema(bundle_dir=None, feature_names=None):
    """生成 feature_schema.json（锁死特征顺序）。"""
    if feature_names is None:
        feature_names = get_feature_schema()
    schema = {
        'n_features': len(feature_names),
        'feature_names': feature_names,
        'feature_hash': compute_feature_hash(feature_names),
    }
    if bundle_dir:
        os.makedirs(bundle_dir, exist_ok=True)
        with open(os.path.join(bundle_dir, 'feature_schema.json'), 'w', encoding='utf-8') as f:
            json.dump(schema, f, ensure_ascii=False, indent=2)
    return schema


def load_bundle(model_id=None, registry_dir=REGISTRY):
    """
    加载生产模型 bundle，强校验 feature_hash。
    - model_id None -> 用 PROD_MODEL_ID。
    - 模型文件或 schema 缺失 -> 抛出明确错误，不回退旧模型。
    返回 dict {model, schema, metadata, bundle_dir}。
    """
    model_id = model_id or PROD_MODEL_ID
    bundle_dir = os.path.join(registry_dir, model_id)

    model_path = os.path.join(bundle_dir, 'model.pkl')
    schema_path = os.path.join(bundle_dir, 'feature_schema.json')

    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f'模型 bundle 缺失: {model_path}。禁止回退旧模型，请先 promote 有效模型。')
    if not os.path.exists(schema_path):
        raise FileNotFoundError(
            f'feature_schema 缺失: {schema_path}。bundle 不完整，禁止推理。')

    with open(schema_path, encoding='utf-8') as f:
        schema = json.load(f)
    with open(model_path, 'rb') as f:
        model = pickle.load(f)

    # 维度一致性校验
    n_model = getattr(model, 'n_features_in_', None)
    if n_model is not None and n_model != schema['n_features']:
        raise ValueError(
            f'模型维度({n_model}) 与 schema({schema["n_features"]}) 不一致，禁止推理。')

    metadata = {}
    meta_path = os.path.join(bundle_dir, 'metadata.json')
    if os.path.exists(meta_path):
        with open(meta_path, encoding='utf-8') as f:
            metadata = json.load(f)

    return {'model': model, 'schema': schema, 'metadata': metadata,
            'bundle_dir': bundle_dir, 'model_id': model_id}


def verify_feature_order(live_names, schema):
    """校验推理特征顺序与 schema 一致。返回 (ok, detail)。"""
    expected = schema['feature_names']
    if len(live_names) != len(expected):
        return False, f'维度不一致: live={len(live_names)} schema={len(expected)}'
    for i, (a, b) in enumerate(zip(live_names, expected)):
        if a != b:
            return False, f'第{i}个特征不一致: live={a} schema={b}'
    if compute_feature_hash(list(live_names)) != schema['feature_hash']:
        return False, 'feature_hash 不匹配'
    return True, 'ok'


def promote_model(src_model_path, model_id=PROD_MODEL_ID, metadata=None,
                  feature_names=None):
    """
    将训练好的模型晋升为生产 bundle（registry 目录）。
    返回 bundle_dir。
    """
    bundle_dir = os.path.join(REGISTRY, model_id)
    os.makedirs(bundle_dir, exist_ok=True)

    # 拷贝模型
    with open(src_model_path, 'rb') as f:
        model_bytes = f.read()
    with open(os.path.join(bundle_dir, 'model.pkl'), 'wb') as f:
        f.write(model_bytes)

    # feature schema
    schema = build_feature_schema(bundle_dir, feature_names)

    # metadata
    if metadata is None:
        metadata = {}
    metadata.setdefault('model_id', model_id)
    metadata.setdefault('feature_hash', schema['feature_hash'])
    metadata.setdefault('n_features', schema['n_features'])
    with open(os.path.join(bundle_dir, 'metadata.json'), 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f'[bundle] 已晋升 {model_id} -> {bundle_dir}')
    print(f'  n_features={schema["n_features"]}  feature_hash={schema["feature_hash"]}')
    return bundle_dir


if __name__ == '__main__':
    # 自检：确定 101 维并打印 hash
    names = get_feature_schema()
    print(f'特征总维数: {len(names)} (chan={len(names)-43} + talib=43)')
    print(f'feature_hash: {compute_feature_hash(names)}')
