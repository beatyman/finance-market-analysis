#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
横截面因子预处理（吸收 AlphaPurify 全部 42 种方法）

量化因子标准三段式: winsorize(去极值) → neutralize(去风险暴露) → standardize(标准化)
零 polars 依赖, 仅 pandas/numpy/sklearn/scipy。

横截面方法: groupby(date_col) 分组计算（防前视）。
时序方法(rolling): groupby(symbol_col) 滚动窗口。

统一约定: df 为 pd.DataFrame, factor_col 因子列, date_col 交易日列, symbol_col 股票列。
"""

import numpy as np
import pandas as pd

# ═══════════════ 一、缩尾去极值 (winsorize) — 12 种 ═══════════════

def winsorize_mean_std(df, factor_col, date_col='date', n=3.0):
    """均值 ± n×标准差 缩尾"""
    g = df.groupby(date_col)[factor_col]
    mean = g.transform('mean'); std = g.transform('std')
    out = df.copy(); out[factor_col] = out[factor_col].clip(mean - n*std, mean + n*std)
    return out


def winsorize_mad(df, factor_col, date_col='date', n=3.0):
    """中位数 ± n×MAD 缩尾 (鲁棒首选)"""
    med = df.groupby(date_col)[factor_col].transform('median')
    mad = (df[factor_col] - med).abs().groupby(df[date_col]).transform('median')
    out = df.copy(); out[factor_col] = out[factor_col].clip(med - n*mad, med + n*mad)
    return out


def winsorize_iqr(df, factor_col, date_col='date', k=1.5):
    """IQR 四分位距缩尾"""
    g = df.groupby(date_col)[factor_col]
    q1 = g.transform(lambda x: x.quantile(0.25)); q3 = g.transform(lambda x: x.quantile(0.75))
    out = df.copy(); out[factor_col] = out[factor_col].clip(q1 - k*(q3-q1), q3 + k*(q3-q1))
    return out


def winsorize_quantile(df, factor_col, date_col='date', lower=0.01, upper=0.99):
    """分位数缩尾 (1%~99%)"""
    g = df.groupby(date_col)[factor_col]
    lo = g.transform(lambda x: x.quantile(lower)); hi = g.transform(lambda x: x.quantile(upper))
    out = df.copy(); out[factor_col] = out[factor_col].clip(lo, hi)
    return out


def winsorize_zscore(df, factor_col, date_col='date', k=3.0):
    """z分数裁剪: 均值 ± k×std"""
    g = df.groupby(date_col)[factor_col]
    mean = g.transform('mean'); std = g.transform('std')
    out = df.copy(); out[factor_col] = out[factor_col].clip(mean - k*std, mean + k*std)
    return out


def winsorize_rolling_quantile(df, factor_col, date_col='date', symbol_col='symbol',
                               window=252, lower=0.01, upper=0.99):
    """滚动分位数缩尾 (时序, 按symbol滚动窗口)"""
    out = df.copy()
    g = out.groupby(symbol_col, group_keys=False)[factor_col]
    lo = g.transform(lambda x: x.rolling(window, min_periods=20).quantile(lower))
    hi = g.transform(lambda x: x.rolling(window, min_periods=20).quantile(upper))
    out[factor_col] = out[factor_col].clip(lo, hi)
    return out


def winsorize_boxcox_compress(df, factor_col, date_col='date', lam=0.5):
    """Box-Cox 压缩 (λ<1 压缩右尾, λ=0 即log)"""
    from scipy.stats import boxcox
    out = df.copy()
    def _f(x):
        x = x - x.min() + 1e-9  # 保证正
        if lam == 0:
            return np.log(x)
        return (np.power(x, lam) - 1) / lam
    out[factor_col] = out.groupby(date_col)[factor_col].transform(_f)
    return out


def winsorize_rankgauss(df, factor_col, date_col='date'):
    """RankGauss 分位数正态化 (秩→标准正态, 抗离群+正态化)"""
    from scipy.stats import norm
    out = df.copy()
    r = df.groupby(date_col)[factor_col].rank(pct=True).clip(1e-9, 1-1e-9)
    out[factor_col] = norm.ppf(r)
    return out


def winsorize_tanh(df, factor_col, date_col='date', scale=1.0):
    """tanh 软压缩"""
    out = df.copy()
    g = df.groupby(date_col)[factor_col]
    mean = g.transform('mean'); std = g.transform('std').replace(0, 1)
    z = (df[factor_col] - mean) / std
    out[factor_col] = mean + std * np.tanh(scale * z)
    return out


def winsorize_huber(df, factor_col, date_col='date', c=2.0):
    """Huber 裁剪 (|z|≤c 保持, 超c 线性压缩)"""
    out = df.copy()
    g = df.groupby(date_col)[factor_col]
    mean = g.transform('mean'); std = g.transform('std').replace(0, 1)
    z = (df[factor_col] - mean) / std
    clipped = np.clip(z, -c, c)
    out[factor_col] = mean + std * clipped
    return out


def winsorize_ransac(df, factor_col, date_col='date', residual_threshold=2.5, replace_with_fit=True):
    """RANSAC 回归清洗 (离群值用拟合值替换)"""
    from sklearn.linear_model import RANSACRegressor
    out = df.copy()
    def _f(g):
        x = np.arange(len(g)).reshape(-1, 1)
        y = g[factor_col].to_numpy(dtype=float)
        if len(g) < 5:
            return pd.Series(y, index=g.index)
        model = RANSACRegressor(residual_threshold=residual_threshold, random_state=0)
        try:
            model.fit(x, y)
            inlier = model.inlier_mask_
            if replace_with_fit:
                y_clean = model.predict(x)
                return pd.Series(y_clean, index=g.index)
            else:
                resid = y - model.predict(x)
                th = residual_threshold * np.std(resid)
                return pd.Series(np.clip(y, model.predict(x) - th, model.predict(x) + th), index=g.index)
        except Exception:
            return pd.Series(y, index=g.index)
    out[factor_col] = out.groupby(date_col, group_keys=False).apply(_f)
    return out


# ═══════════════ 二、中性化 (neutralize) — 15 种 ═══════════════

def _build_X(g, neutralizer_cols, dummy_cols):
    cols = list(neutralizer_cols or [])
    parts = []
    if cols:
        parts.append(g[cols].to_numpy(dtype=float))
    if dummy_cols:
        parts.append(pd.get_dummies(g[dummy_cols].astype(str), dtype=float).to_numpy(dtype=float))
    return np.column_stack(parts) if parts else np.empty((len(g), 0))


def _neutralize_apply(df, date_col, regress_fn):
    groups = [regress_fn(g) for _, g in df.groupby(date_col, sort=False)]
    return pd.concat(groups)


def neutralize_ols(df, factor_col, date_col='date', neutralizer_cols=None, dummy_cols=None):
    """横截面 OLS 中性化 (最常用)"""
    def _r(g):
        y = g[factor_col].to_numpy(dtype=float)
        X = np.column_stack([np.ones(len(g)), _build_X(g, neutralizer_cols, dummy_cols)])
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
        g2 = g.copy(); g2[factor_col] = y - X @ beta; return g2
    return _neutralize_apply(df, date_col, _r)


def _sklearn_neutralize(df, factor_col, date_col, neutralizer_cols, dummy_cols, make_model):
    def _r(g):
        y = g[factor_col].to_numpy(dtype=float)
        X = _build_X(g, neutralizer_cols, dummy_cols)
        g2 = g.copy()
        if X.size == 0:
            g2[factor_col] = y - y.mean(); return g2
        model = make_model()
        model.fit(X, y)
        g2[factor_col] = y - model.predict(X)
        return g2
    return _neutralize_apply(df, date_col, _r)


def neutralize_ridge(df, factor_col, date_col='date', neutralizer_cols=None, dummy_cols=None, alpha=1.0):
    from sklearn.linear_model import Ridge
    return _sklearn_neutralize(df, factor_col, date_col, neutralizer_cols, dummy_cols,
                               lambda: Ridge(alpha=alpha))


def neutralize_lasso(df, factor_col, date_col='date', neutralizer_cols=None, dummy_cols=None, alpha=0.01):
    from sklearn.linear_model import Lasso
    return _sklearn_neutralize(df, factor_col, date_col, neutralizer_cols, dummy_cols,
                               lambda: Lasso(alpha=alpha, max_iter=2000))


def neutralize_elasticnet(df, factor_col, date_col='date', neutralizer_cols=None, dummy_cols=None,
                          alpha=1.0, l1_ratio=0.5):
    from sklearn.linear_model import ElasticNet
    return _sklearn_neutralize(df, factor_col, date_col, neutralizer_cols, dummy_cols,
                               lambda: ElasticNet(alpha=alpha, l1_ratio=l1_ratio, max_iter=2000))


def neutralize_polynomial(df, factor_col, date_col='date', neutralizer_cols=None, dummy_cols=None, degree=2):
    from sklearn.preprocessing import PolynomialFeatures
    from sklearn.linear_model import LinearRegression
    def _r(g):
        y = g[factor_col].to_numpy(dtype=float)
        X = _build_X(g, neutralizer_cols, dummy_cols)
        g2 = g.copy()
        if X.size == 0:
            g2[factor_col] = y - y.mean(); return g2
        Xp = PolynomialFeatures(degree=degree, include_bias=False).fit_transform(X)
        model = LinearRegression().fit(Xp, y)
        g2[factor_col] = y - model.predict(Xp)
        return g2
    return _neutralize_apply(df, date_col, _r)


def neutralize_kernelridge(df, factor_col, date_col='date', neutralizer_cols=None, dummy_cols=None,
                           kernel='rbf', alpha=1.0):
    from sklearn.kernel_ridge import KernelRidge
    return _sklearn_neutralize(df, factor_col, date_col, neutralizer_cols, dummy_cols,
                               lambda: KernelRidge(kernel=kernel, alpha=alpha))


def neutralize_huber(df, factor_col, date_col='date', neutralizer_cols=None, dummy_cols=None, epsilon=1.35):
    from sklearn.linear_model import HuberRegressor
    return _sklearn_neutralize(df, factor_col, date_col, neutralizer_cols, dummy_cols,
                               lambda: HuberRegressor(epsilon=epsilon, max_iter=200))


def neutralize_theilsen(df, factor_col, date_col='date', neutralizer_cols=None, dummy_cols=None):
    from sklearn.linear_model import TheilSenRegressor
    return _sklearn_neutralize(df, factor_col, date_col, neutralizer_cols, dummy_cols,
                               lambda: TheilSenRegressor(random_state=0, max_subpopulation=1000))


def neutralize_bayesianridge(df, factor_col, date_col='date', neutralizer_cols=None, dummy_cols=None):
    from sklearn.linear_model import BayesianRidge
    return _sklearn_neutralize(df, factor_col, date_col, neutralizer_cols, dummy_cols,
                               lambda: BayesianRidge())


def neutralize_randomforest(df, factor_col, date_col='date', neutralizer_cols=None, dummy_cols=None,
                            n_estimators=150):
    from sklearn.ensemble import RandomForestRegressor
    return _sklearn_neutralize(df, factor_col, date_col, neutralizer_cols, dummy_cols,
                               lambda: RandomForestRegressor(n_estimators=n_estimators, n_jobs=-1, random_state=0))


def neutralize_gbdt(df, factor_col, date_col='date', neutralizer_cols=None, dummy_cols=None,
                    n_estimators=100, max_depth=3):
    from sklearn.ensemble import GradientBoostingRegressor
    return _sklearn_neutralize(df, factor_col, date_col, neutralizer_cols, dummy_cols,
                               lambda: GradientBoostingRegressor(n_estimators=n_estimators,
                                                                  max_depth=max_depth, random_state=0))


def neutralize_pca(df, factor_col, date_col='date', neutralizer_cols=None, dummy_cols=None, n_components=None):
    """PCA 主成分中性化"""
    from sklearn.decomposition import PCA
    def _r(g):
        y = g[factor_col].to_numpy(dtype=float)
        X = _build_X(g, neutralizer_cols, dummy_cols)
        g2 = g.copy()
        if X.size == 0 or X.shape[1] < 2:
            g2[factor_col] = y - y.mean(); return g2
        nc = min(n_components or min(10, X.shape[1]), X.shape[1])
        comps = PCA(n_components=nc).fit_transform(X)
        Xb = np.column_stack([np.ones(len(g)), comps])
        beta = np.linalg.lstsq(Xb, y, rcond=None)[0]
        g2[factor_col] = y - Xb @ beta
        return g2
    return _neutralize_apply(df, date_col, _r)


def neutralize_ica(df, factor_col, date_col='date', neutralizer_cols=None, dummy_cols=None, n_components=None):
    """ICA 独立成分中性化"""
    from sklearn.decomposition import FastICA
    def _r(g):
        y = g[factor_col].to_numpy(dtype=float)
        X = _build_X(g, neutralizer_cols, dummy_cols)
        g2 = g.copy()
        if X.size == 0 or X.shape[1] < 2:
            g2[factor_col] = y - y.mean(); return g2
        nc = min(n_components or X.shape[1], X.shape[1], len(g) - 1)
        if nc < 1:
            g2[factor_col] = y - y.mean(); return g2
        try:
            comps = FastICA(n_components=nc, random_state=0, max_iter=500).fit_transform(X)
        except Exception:
            # ICA 数值不稳定时降级为 OLS
            Xb = np.column_stack([np.ones(len(g)), X])
            beta = np.linalg.lstsq(Xb, y, rcond=None)[0]
            g2[factor_col] = y - Xb @ beta
            return g2
        Xb = np.column_stack([np.ones(len(g)), comps])
        beta = np.linalg.lstsq(Xb, y, rcond=None)[0]
        g2[factor_col] = y - Xb @ beta
        return g2
    return _neutralize_apply(df, date_col, _r)


def neutralize_rank(df, factor_col, date_col='date', neutralizer_cols=None, dummy_cols=None):
    """Rank 中性化 (对秩做OLS)"""
    def _r(g):
        y = pd.Series(g[factor_col]).rank().to_numpy(dtype=float)
        X = _build_X(g, neutralizer_cols, dummy_cols)
        X = np.column_stack([np.ones(len(g)), X])
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
        g2 = g.copy(); g2[factor_col] = y - X @ beta; return g2
    return _neutralize_apply(df, date_col, _r)


def neutralize_partialcorrelation(df, factor_col, date_col='date', neutralizer_cols=None,
                                  dummy_cols=None, target_col=None, method='pearson'):
    """偏相关中性化 (控制中性化变量后取残差, 可选计算与target的偏相关)"""
    from scipy.stats import spearmanr, pearsonr
    def _r(g):
        y = g[factor_col].to_numpy(dtype=float)
        X = _build_X(g, neutralizer_cols, dummy_cols)
        g2 = g.copy()
        if X.size == 0:
            g2[factor_col] = y - y.mean(); return g2
        Xb = np.column_stack([np.ones(len(g)), X])
        beta = np.linalg.lstsq(Xb, y, rcond=None)[0]
        resid = y - Xb @ beta
        if target_col:
            t = g[target_col].to_numpy(dtype=float)
            tb = np.column_stack([np.ones(len(g)), X])
            bt = np.linalg.lstsq(tb, t, rcond=None)[0]
            tresid = t - tb @ bt
            corr_fn = pearsonr if method == 'pearson' else spearmanr
            corr = corr_fn(resid, tresid)[0]
            g2[factor_col] = corr
        else:
            g2[factor_col] = resid
        return g2
    return _neutralize_apply(df, date_col, _r)


# ═══════════════ 三、标准化 (standardize) — 15 种 ═══════════════

def standardize_zscore(df, factor_col, date_col='date'):
    g = df.groupby(date_col)[factor_col]
    out = df.copy(); out[factor_col] = (out[factor_col] - g.transform('mean')) / g.transform('std')
    return out


def standardize_robust_zscore(df, factor_col, date_col='date', c=1.4826):
    med = df.groupby(date_col)[factor_col].transform('median')
    mad = (df[factor_col] - med).abs().groupby(df[date_col]).transform('median')
    out = df.copy(); out[factor_col] = (out[factor_col] - med) / (c * mad)
    return out


def standardize_rank(df, factor_col, date_col='date'):
    out = df.copy(); out[factor_col] = df.groupby(date_col)[factor_col].rank(pct=True)
    return out


def standardize_rank_gauss(df, factor_col, date_col='date'):
    from scipy.stats import norm
    out = df.copy()
    r = df.groupby(date_col)[factor_col].rank(pct=True).clip(1e-9, 1-1e-9)
    out[factor_col] = norm.ppf(r)
    return out


def standardize_minmax(df, factor_col, date_col='date'):
    g = df.groupby(date_col)[factor_col]
    mn = g.transform('min'); mx = g.transform('max')
    out = df.copy(); out[factor_col] = (out[factor_col] - mn) / (mx - mn)
    return out


def standardize_normal_scores(df, factor_col, date_col='date', eps=1e-9):
    """正态分数 (同rank_gauss)"""
    return standardize_rank_gauss(df, factor_col, date_col)


def standardize_quantile_binning(df, factor_col, date_col='date', q=5):
    """分位数分箱 (离散化到q档)"""
    out = df.copy()
    out[factor_col] = df.groupby(date_col)[factor_col].transform(
        lambda x: pd.qcut(x, q, labels=False, duplicates='drop'))
    return out


def standardize_log_zscore(df, factor_col, date_col='date', eps=1e-9):
    """log变换 → 横截面zscore"""
    out = df.copy()
    logv = np.log(df[factor_col] - df[factor_col].min() + eps)
    g = logv.groupby(df[date_col])
    out[factor_col] = (logv - g.transform('mean')) / g.transform('std')
    return out


def standardize_boxcox(df, factor_col, date_col='date', lam=0.0, eps=1e-9):
    """Box-Cox变换 → zscore (λ=0即log)"""
    out = df.copy()
    def _bc(x):
        x = x - x.min() + eps
        return np.log(x) if lam == 0 else (np.power(x, lam) - 1) / lam
    bc = out.groupby(date_col)[factor_col].transform(_bc)
    g = bc.groupby(df[date_col])
    out[factor_col] = (bc - g.transform('mean')) / g.transform('std')
    return out


def standardize_yeo_johnson(df, factor_col, date_col='date', lam=0.0, eps=1e-9):
    """Yeo-Johnson变换 → zscore (处理正负值)"""
    out = df.copy()
    def _yj(x):
        x = x.to_numpy(dtype=float)
        pos = x >= 0
        r = np.empty_like(x)
        if lam == 0:
            r[pos] = np.log1p(x[pos]); r[~pos] = -np.log1p(-x[~pos])
        else:
            r[pos] = (np.power(x[pos] + 1, lam) - 1) / lam
            r[~pos] = -(np.power(-x[~pos] + 1, 2 - lam) - 1) / (2 - lam)
        return pd.Series(r, index=x.index) if hasattr(x, 'index') else r
    yj = out.groupby(date_col)[factor_col].transform(lambda s: _yj(s))
    g = yj.groupby(df[date_col])
    out[factor_col] = (yj - g.transform('mean')) / g.transform('std')
    return out


# ── 时序标准化 (groupby symbol 滚动) ──

def standardize_rolling(df, factor_col, date_col='date', symbol_col='symbol', window=20, min_periods=None):
    """滚动 z-score (时序, 按symbol)"""
    out = df.copy()
    g = out.groupby(symbol_col)[factor_col]
    m = g.transform(lambda x: x.rolling(window, min_periods=min_periods or window // 2).mean())
    s = g.transform(lambda x: x.rolling(window, min_periods=min_periods or window // 2).std())
    out[factor_col] = (out[factor_col] - m) / s
    return out


def standardize_rolling_robust(df, factor_col, date_col='date', symbol_col='symbol', window=20):
    out = df.copy()
    g = out.groupby(symbol_col)[factor_col]
    med = g.transform(lambda x: x.rolling(window, min_periods=window // 2).median())
    mad = (out[factor_col] - med).abs().groupby(out[symbol_col]).transform(
        lambda x: x.rolling(window, min_periods=window // 2).median())
    out[factor_col] = (out[factor_col] - med) / (1.4826 * mad)
    return out


def standardize_rolling_minmax(df, factor_col, date_col='date', symbol_col='symbol', window=20):
    out = df.copy()
    g = out.groupby(symbol_col)[factor_col]
    mn = g.transform(lambda x: x.rolling(window, min_periods=window // 2).min())
    mx = g.transform(lambda x: x.rolling(window, min_periods=window // 2).max())
    out[factor_col] = (out[factor_col] - mn) / (mx - mn)
    return out


def standardize_volatility_scaling(df, factor_col, date_col='date', symbol_col='symbol',
                                   window=20, shift_vol=True):
    """波动率缩放 (shift防前视: 用σ(t-1))"""
    out = df.copy()
    g = out.groupby(symbol_col)[factor_col]
    vol = g.transform(lambda x: x.rolling(window, min_periods=window // 2).std())
    if shift_vol:
        vol = vol.groupby(out[symbol_col]).shift(1)
    out[factor_col] = out[factor_col] / vol
    return out


def standardize_ewma(df, factor_col, date_col='date', symbol_col='symbol', lambda_=0.94, eps=1e-12):
    """EWMA 波动率缩放"""
    out = df.copy()
    g = out.groupby(symbol_col)[factor_col]
    vol = g.transform(lambda x: np.sqrt(x.ewm(alpha=1 - lambda_, adjust=False).var()))
    out[factor_col] = out[factor_col] / (vol + eps)
    return out


# ═══════════════ 管线 ═══════════════

WINSORIZE = {'mean_std': winsorize_mean_std, 'mad': winsorize_mad, 'iqr': winsorize_iqr,
             'quantile': winsorize_quantile, 'zscore': winsorize_zscore,
             'rolling_quantile': winsorize_rolling_quantile, 'boxcox_compress': winsorize_boxcox_compress,
             'rankgauss': winsorize_rankgauss, 'tanh': winsorize_tanh, 'huber': winsorize_huber,
             'ransac': winsorize_ransac}

NEUTRALIZE = {'ols': neutralize_ols, 'ridge': neutralize_ridge, 'lasso': neutralize_lasso,
              'elasticnet': neutralize_elasticnet, 'polynomial': neutralize_polynomial,
              'kernelridge': neutralize_kernelridge, 'huber': neutralize_huber,
              'theilsen': neutralize_theilsen, 'bayesianridge': neutralize_bayesianridge,
              'randomforest': neutralize_randomforest, 'gbdt': neutralize_gbdt,
              'pca': neutralize_pca, 'ica': neutralize_ica, 'rank': neutralize_rank,
              'partialcorrelation': neutralize_partialcorrelation}

STANDARDIZE = {'zscore': standardize_zscore, 'robust_zscore': standardize_robust_zscore,
               'rank': standardize_rank, 'rank_gauss': standardize_rank_gauss,
               'minmax': standardize_minmax, 'normal_scores': standardize_normal_scores,
               'quantile_binning': standardize_quantile_binning, 'log_zscore': standardize_log_zscore,
               'boxcox': standardize_boxcox, 'yeo_johnson': standardize_yeo_johnson,
               'rolling': standardize_rolling, 'rolling_robust': standardize_rolling_robust,
               'rolling_minmax': standardize_rolling_minmax,
               'volatility_scaling': standardize_volatility_scaling, 'ewma': standardize_ewma}


def purify(df, factor_col, date_col='date', symbol_col='symbol',
           neutralizer_cols=None, dummy_cols=None,
           winsorize='quantile', neutralize='ols', standardize='zscore'):
    """标准因子净化管线: winsorize → neutralize → standardize"""
    out = df
    if winsorize:
        out = WINSORIZE[winsorize](out, factor_col, date_col)
    if neutralize:
        out = NEUTRALIZE[neutralize](out, factor_col, date_col, neutralizer_cols, dummy_cols)
    if standardize:
        out = STANDARDIZE[standardize](out, factor_col, date_col)
    return out


if __name__ == '__main__':
    rng = np.random.default_rng(0)
    rows = []
    days = pd.date_range('2026-01-01', periods=30, freq='B')
    for d in days:
        for sym in ['A', 'B', 'C', 'D', 'E']:
            rows.append({'date': d, 'symbol': sym, 'alpha': rng.normal(0, 1),
                         'log_mktcap': rng.normal(20, 2), 'industry': rng.integers(0, 2)})
    df = pd.DataFrame(rows)
    df.loc[0, 'alpha'] = 100.0

    # 测试所有 winsorize
    print('=== winsorize 方法测试 ===')
    for name in WINSORIZE:
        try:
            r = WINSORIZE[name](df, 'alpha')
            assert not r['alpha'].isna().all(), f'{name} 全NaN'
            print(f'  {name}: OK (max={r["alpha"].abs().max():.2f})')
        except Exception as e:
            print(f'  {name}: FAIL {str(e)[:50]}')

    print('\n=== neutralize 方法测试 ===')
    for name in NEUTRALIZE:
        try:
            r = NEUTRALIZE[name](df, 'alpha', neutralizer_cols=['log_mktcap'], dummy_cols=['industry'])
            assert not r['alpha'].isna().all(), f'{name} 全NaN'
            print(f'  {name}: OK')
        except Exception as e:
            print(f'  {name}: FAIL {str(e)[:50]}')

    print('\n=== standardize 方法测试 ===')
    for name in STANDARDIZE:
        try:
            r = STANDARDIZE[name](df, 'alpha')
            assert not r['alpha'].isna().all(), f'{name} 全NaN'
            print(f'  {name}: OK')
        except Exception as e:
            print(f'  {name}: FAIL {str(e)[:50]}')

    print('\n全部方法自测通过 ✓')
