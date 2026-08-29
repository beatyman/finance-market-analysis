#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FeaturePipeline：split-before-fit 的无泄漏特征管线

解决 P0-05（特征选择泄漏）+ P0-06（训练/推理特征不一致）：
    - fit 只在 TRAIN 上执行（NaN policy / constant removal / winsor 阈值 /
      correlation filter / IC filter）
    - transform 对 train/val/test/live 只应用 fit 时保存的参数，绝不重新 fit
    - 所有 fit 参数可序列化，作为 model bundle 的 preprocessing 工件保存

用法（与方案伪代码一致）：
    pipeline = FeaturePipeline()
    pipeline.fit(train_df, feat_cols, label_col='label')
    X_train = pipeline.transform(train_df)
    X_val   = pipeline.transform(val_df)
    X_test  = pipeline.transform(test_df)
"""
import os
import json
import numpy as np
import pandas as pd


class FeaturePipeline:
    def __init__(self, max_missing_rate=0.80, winsor_low=0.01, winsor_high=0.99,
                 corr_threshold=0.85, ic_min_abs=0.02, fill_value=0.0):
        self.max_missing_rate = max_missing_rate
        self.winsor_low = winsor_low
        self.winsor_high = winsor_high
        self.corr_threshold = corr_threshold
        self.ic_min_abs = ic_min_abs
        self.fill_value = fill_value
        # fit 后填充
        self.keep_features = None        # 最终保留的特征（严格顺序）
        self.winsor_bounds = None        # {feat: (lo, hi)} 从 train 拟合
        self.constants_removed = []      # nunique<=1 的常量特征
        self.correlation_drop = []       # Spearman 冗余剔除
        self.ic_drop = []                # |IC| 低于阈值的特征
        self.missing_dropped = []        # 缺失率超阈值的特征
        self._fitted = False

    # ── fit 系列（只在 TRAIN 上调用）──────────────────────────────
    def fit(self, train_df, feat_cols, label_col='label'):
        df = train_df.reset_index(drop=True)
        n = len(df)

        # 1) missing rate -> drop
        na_ratio = df[feat_cols].isna().mean()
        self.missing_dropped = na_ratio[na_ratio > self.max_missing_rate].index.tolist()
        keep = [c for c in feat_cols if c not in self.missing_dropped]

        # 2) constant removal
        for c in keep:
            if df[c].nunique(dropna=True) <= 1:
                self.constants_removed.append(c)
        keep = [c for c in keep if c not in self.constants_removed]

        # 3) winsor bounds（只在 train 上算分位数）
        self.winsor_bounds = {}
        for c in keep:
            col = df[c].astype(float)
            lo = np.nanpercentile(col, self.winsor_low * 100)
            hi = np.nanpercentile(col, self.winsor_high * 100)
            if np.isnan(lo) or np.isnan(hi):
                lo, hi = 0.0, 0.0
            self.winsor_bounds[c] = (float(lo), float(hi))

        # 4) correlation filter（Spearman，只用 train）
        keep = self._correlation_filter(df, keep)

        # 5) IC filter（用 label，只用 train）
        if label_col is not None and label_col in df.columns:
            keep = self._ic_filter(df, keep, label_col)

        self.keep_features = keep
        self._fitted = True
        return self

    def _correlation_filter(self, df, keep):
        """Spearman 冗余过滤：|corr|>阈值 时按优先级剔除。"""
        if len(keep) <= 1:
            return keep
        corr = df[keep].corr(method='spearman').abs()
        drop = set()
        # 按列顺序遍历，后出现的与前面高相关则剔除（保留靠前 = 优先级高）
        for i in range(len(keep)):
            if keep[i] in drop:
                continue
            for j in range(i + 1, len(keep)):
                if keep[j] in drop:
                    continue
                if pd.notna(corr.loc[keep[i], keep[j]]) and \
                        corr.loc[keep[i], keep[j]] > self.corr_threshold:
                    drop.add(keep[j])
        self.correlation_drop = sorted(drop)
        return [c for c in keep if c not in drop]

    def _ic_filter(self, df, keep, label_col):
        """滚动 IC 过滤（只在 train 上，用 label）。|mean IC| < 阈值 则剔除。"""
        y = df[label_col].astype(float).values
        drop = []
        for c in keep:
            x = df[c].astype(float).values
            mask = ~np.isnan(x) & ~np.isnan(y)
            if mask.sum() < 30:
                drop.append(c)
                continue
            ic = np.corrcoef(x[mask], y[mask])[0, 1]
            if abs(ic) < self.ic_min_abs:
                drop.append(c)
        self.ic_drop = drop
        return [c for c in keep if c not in drop]

    # ── transform 系列（train/val/test/live 一致）─────────────────
    def transform(self, df):
        if not self._fitted:
            raise RuntimeError('FeaturePipeline 未 fit，禁止 transform')
        df = df.reset_index(drop=True)
        out = df.copy()
        for c in self.keep_features:
            if c not in out.columns:
                out[c] = self.fill_value
            col = out[c].astype(float)
            lo, hi = self.winsor_bounds[c]
            col = np.clip(col, lo, hi)
            out[c] = col.fillna(self.fill_value)
        return out[self.keep_features]

    def fit_transform(self, train_df, feat_cols, label_col='label'):
        self.fit(train_df, feat_cols, label_col)
        return self.transform(train_df)

    # ── 序列化（作为 bundle 的 preprocessing.json 工件）────────────
    def to_dict(self):
        return {
            'keep_features': self.keep_features,
            'winsor_bounds': self.winsor_bounds,
            'constants_removed': self.constants_removed,
            'correlation_drop': self.correlation_drop,
            'ic_drop': self.ic_drop,
            'missing_dropped': self.missing_dropped,
            'params': {
                'max_missing_rate': self.max_missing_rate,
                'winsor_low': self.winsor_low,
                'winsor_high': self.winsor_high,
                'corr_threshold': self.corr_threshold,
                'ic_min_abs': self.ic_min_abs,
                'fill_value': self.fill_value,
            },
        }

    def save(self, path):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2, default=float)
        return path

    def load(self, path):
        with open(path, encoding='utf-8') as f:
            d = json.load(f)
        self.keep_features = d['keep_features']
        self.winsor_bounds = {k: tuple(v) for k, v in d['winsor_bounds'].items()}
        self.constants_removed = d['constants_removed']
        self.correlation_drop = d['correlation_drop']
        self.ic_drop = d['ic_drop']
        self.missing_dropped = d['missing_dropped']
        p = d['params']
        self.max_missing_rate = p['max_missing_rate']
        self.winsor_low = p['winsor_low']
        self.winsor_high = p['winsor_high']
        self.corr_threshold = p['corr_threshold']
        self.ic_min_abs = p['ic_min_abs']
        self.fill_value = p['fill_value']
        self._fitted = True
        return self


if __name__ == '__main__':
    # 自检：构造合成数据，验证 fit/transform 无泄漏
    rng = np.random.RandomState(42)
    n = 500
    df = pd.DataFrame({
        'date': np.repeat(pd.date_range('2026-01-01', periods=10), 50).astype(str),
        'label': rng.randint(0, 2, n),
        'f1': rng.randn(n),
        'f2': rng.randn(n) * 2,
        'f3': rng.randn(n) + 0.5,
        'const': np.ones(n),
        'f_redundant': None,  # 将与 f1 高相关
    })
    df['f_redundant'] = df['f1'] + rng.randn(n) * 0.05

    # split
    dates = sorted(df['date'].unique())
    tr = df[df['date'].isin(dates[:6])]
    te = df[df['date'].isin(dates[6:])]

    pipe = FeaturePipeline()
    pipe.fit(tr, ['f1', 'f2', 'f3', 'const', 'f_redundant'], 'label')
    X_tr = pipe.transform(tr)
    X_te = pipe.transform(te)
    print(f'fit 后保留特征: {pipe.keep_features}')
    print(f'常量剔除: {pipe.constants_removed}')
    print(f'冗余剔除: {pipe.correlation_drop}')
    print(f'transform 维度: train={X_tr.shape} test={X_te.shape}')
    assert 'const' not in pipe.keep_features, '常量特征应被剔除'
    assert len(X_tr.columns) == len(pipe.keep_features)
    print('FeaturePipeline 自检通过')
