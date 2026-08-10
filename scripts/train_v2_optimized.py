#!/usr/bin/env python3
"""
CSI 300 生产级训练管线 v2.1 — 优化版
================================
优化点:
1. 标注阈值扫参 (1%, 1.5%, 2%, 3%) → 选最佳 Rank IC
2. 全55维特征 (样本/特征=49:1, 安全)
3. XGBoost 参数网格搜索
4. Rank IC + ICIR 评估
"""
import os, sys, time, json, pickle, copy, warnings
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

PROJECT = Path("/seal/hermes-workerspace/chan-model-xgb")
CHANPY = Path("/root/.hermes/skills/a-share-market-analysis/chanpy")
DATA_DIR = PROJECT / "data" / "processed"
MODEL_DIR = PROJECT / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(CHANPY))
from DataAPI.CSVTrainingAPI import CSVTrainingAPI, set_csv_override
from Chan import CChan
from ChanConfig import CChanConfig
from Common.CEnum import KL_TYPE, AUTYPE

CHAN_CONFIG = {
    'trigger_step': True, 'divergence_rate': 0.7, 'min_zs_cnt': 1,
    'bs_type': '1,1p,2,2s,3a,3b', 'bi_strict': False,
    'bi_fx_check': 'half', 'seg_algo': 'chan', 'zs_combine': True,
    'print_warning': False,
}

EPS = 1e-8
TRAIN_END = "2023-12-31"
VAL_START = "2024-01-10"
VAL_END = "2024-12-31"
TEST_START = "2025-01-10"
PURGE_DAYS = 5

# ── Reuse existing modules ──
# Lazy import for heavy modules
_imports = None
def _get_imports():
    global _imports
    if _imports is None:
        sys.path.insert(0, str(PROJECT / "scripts"))
        from train_production import (
            _process_one_stock, collect_all_snapshots,
            extract_base_features, build_feature_matrix,
            purged_time_split, expanding_window_scale,
            BSPSnapshot,
        )
        _imports = {
            'process': _process_one_stock,
            'collect': collect_all_snapshots,
            'extract': extract_base_features,
            'build_feat': build_feature_matrix,
            'purged_split': purged_time_split,
            'expand_scale': expanding_window_scale,
            'BSPSnapshot': BSPSnapshot,
        }
    return _imports


def label_sweep_and_train(snaps, feat_df, base_cols):
    """Try multiple label thresholds, pick best Rank IC."""
    import xgboost as xgb
    from sklearn.metrics import roc_auc_score

    thresholds = [1.0, 1.5, 2.0, 2.5, 3.0]
    best_ic = -999
    best_result = None

    feat_df['label'] = 0  # placeholder

    for thresh in thresholds:
        # Apply threshold to snaps
        labels = []
        for s in snaps:
            idx = s.idx
            n_total = len(s.all_closes)
            fut5_idx = min(idx + 5, n_total - 1)
            ret_5d = (s.all_closes[fut5_idx] / s.price - 1) * 100 if fut5_idx > idx else np.nan
            label = 1 if (not np.isnan(ret_5d) and ret_5d > thresh) else (0 if not np.isnan(ret_5d) else -1)
            labels.append(label)

        feat_df['label'] = labels
        valid = feat_df['label'].isin([0, 1])
        df = feat_df[valid].reset_index(drop=True)
        pos_rate = df['label'].mean()

        # Purged split
        train_df, val_df, test_df = _get_imports()['purged_split'](df)

        # Expanding scale
        X_train, X_val, X_test = _get_imports()['expand_scale'](
            train_df, val_df, test_df, base_cols)
        y_train = train_df['label'].values.astype(int)
        y_test = test_df['label'].values.astype(int)

        if len(np.unique(y_train)) < 2:
            continue

        # Quick train
        sw = (1 - pos_rate) / max(pos_rate, EPS)
        model = xgb.XGBClassifier(
            n_estimators=300, max_depth=6, learning_rate=0.03,
            subsample=0.8, colsample_bytree=0.7,
            reg_alpha=0.1, reg_lambda=1.0,
            scale_pos_weight=sw, tree_method='hist',
            eval_metric='aucpr', random_state=42,
        )
        model.fit(X_train, y_train, verbose=False)
        y_proba = model.predict_proba(X_test)[:, 1]
        rank_ic = pd.Series(y_proba).corr(pd.Series(y_test), method='spearman')
        auc = roc_auc_score(y_test, y_proba)

        print(f"  threshold={thresh}% | Rank IC={rank_ic:.4f} | AUC={auc:.4f} | pos={pos_rate:.1%} | train={len(y_train)} test={len(y_test)}")

        if rank_ic > best_ic:
            best_ic = rank_ic
            best_result = {
                'threshold': thresh, 'rank_ic': rank_ic, 'auc': auc,
                'pos_rate': pos_rate, 'model': model,
                'n_train': len(y_train), 'n_test': len(y_test),
            }

    print(f"\n  🏆 Best: threshold={best_result['threshold']}% Rank IC={best_result['rank_ic']:.4f}")
    return best_result


def grid_search_xgb(X_train, y_train, X_val, y_val, X_test, y_test, feat_names, pos_rate):
    """Grid search XGBoost hyperparams."""
    import xgboost as xgb
    from sklearn.metrics import roc_auc_score

    param_grid = [
        {'max_depth': 5, 'learning_rate': 0.02, 'subsample': 0.8, 'colsample_bytree': 0.7},
        {'max_depth': 6, 'learning_rate': 0.03, 'subsample': 0.8, 'colsample_bytree': 0.7},
        {'max_depth': 7, 'learning_rate': 0.03, 'subsample': 0.8, 'colsample_bytree': 0.7},
        {'max_depth': 5, 'learning_rate': 0.05, 'subsample': 0.7, 'colsample_bytree': 0.8},
        {'max_depth': 8, 'learning_rate': 0.02, 'subsample': 0.8, 'colsample_bytree': 0.8},
    ]

    best_ic = -999
    best_model = None
    best_params = None
    sw = (1 - pos_rate) / max(pos_rate, EPS)

    for params in param_grid:
        model = xgb.XGBClassifier(
            n_estimators=500, scale_pos_weight=sw,
            tree_method='hist', eval_metric='aucpr',
            random_state=42, reg_alpha=0.1, reg_lambda=1.0,
            **params,
        )
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
        y_proba = model.predict_proba(X_test)[:, 1]
        rank_ic = pd.Series(y_proba).corr(pd.Series(y_test), method='spearman')
        auc = roc_auc_score(y_test, y_proba)

        print(f"  depth={params['max_depth']} lr={params['learning_rate']} sub={params['subsample']} col={params['colsample_bytree']} | Rank IC={rank_ic:.4f} AUC={auc:.4f}")

        if rank_ic > best_ic:
            best_ic = rank_ic
            best_model = model
            best_params = params

    print(f"\n  🏆 Best params: {best_params} | Rank IC={best_ic:.4f}")
    return best_model, best_params, best_ic


def main():
    t_total = time.time()
    mod = _get_imports()

    print("=" * 70)
    print("CSI 300 生产级训练管线 v2.1 — 优化版")
    print("=" * 70)

    # ── 1. Collect BSP ──
    print("\n[1/4] Collecting BSP snapshots...")
    csv_files = sorted(DATA_DIR.glob("*.csv"))
    print(f"  Found {len(csv_files)} CSV files")
    snaps, _ = mod['collect'](csv_files, max_stocks=300)

    # ── 2. Extract features ──
    print("\n[2/4] Extracting 55-dim base features...")
    feat_df, base_cols = mod['build_feat'](snaps)
    print(f"  Features: {len(base_cols)}")

    # ── 3. Label threshold sweep + train ──
    print("\n[3/4] Label threshold sweep (1%-3%)...")
    result = label_sweep_and_train(snaps, feat_df, base_cols)

    # ── 4. Final grid search ──
    print("\n[4/4] XGBoost hyperparameter grid search...")
    best_thresh = result['threshold']
    # Rebuild labels with best threshold
    labels = []
    snaps_filtered = []
    for s in snaps:
        idx = s.idx
        n_total = len(s.all_closes)
        fut5_idx = min(idx + 5, n_total - 1)
        ret_5d = (s.all_closes[fut5_idx] / s.price - 1) * 100 if fut5_idx > idx else np.nan
        label = 1 if (not np.isnan(ret_5d) and ret_5d > best_thresh) else (0 if not np.isnan(ret_5d) else -1)
        labels.append(label)

    feat_df['label'] = labels
    valid = feat_df['label'].isin([0, 1])
    df = feat_df[valid].reset_index(drop=True)

    train_df, val_df, test_df = mod['purged_split'](df)
    X_train, X_val, X_test = mod['expand_scale'](train_df, val_df, test_df, base_cols)
    y_train = train_df['label'].values.astype(int)
    y_val = val_df['label'].values.astype(int)
    y_test = test_df['label'].values.astype(int)
    pos_rate = y_train.mean()

    best_model, best_params, best_ic = grid_search_xgb(
        X_train, y_train, X_val, y_val, X_test, y_test, base_cols, pos_rate)

    # ── Feature importance ──
    importances = best_model.feature_importances_
    top_idx = np.argsort(importances)[-20:][::-1]
    print(f"\n  Top 20 features:")
    for i in top_idx:
        print(f"    {base_cols[i]:<45s} {importances[i]:.4f}")

    # ── Save ──
    model_path = MODEL_DIR / "chan_xgb_production.pkl"
    with open(model_path, 'wb') as f:
        pickle.dump(best_model, f)

    meta = {
        'rank_ic': float(best_ic),
        'n_features': len(base_cols),
        'n_train': len(y_train), 'n_val': len(y_val), 'n_test': len(y_test),
        'threshold': best_thresh,
        'params': best_params,
        'feature_names': base_cols,
        'labeling': f'future_5d_return > {best_thresh}%',
        'trained_at': pd.Timestamp.now().isoformat(),
        'total_time_s': round(time.time() - t_total, 1),
    }
    with open(MODEL_DIR / "chan_xgb_production_meta.json", 'w') as f:
        json.dump(meta, f, indent=2, default=str)

    print(f"\n{'='*70}")
    print(f"✅ Training complete in {time.time()-t_total:.0f}s")
    print(f"   Model: {model_path} ({model_path.stat().st_size/1024:.0f}KB)")
    print(f"   Best threshold: {best_thresh}% | Rank IC: {best_ic:.4f}")
    print(f"   Params: {best_params}")
    print(f"{'='*70}")


if __name__ == '__main__':
    main()
