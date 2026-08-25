#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关系特征 (吸收 skill-dl-gnn-stock-graph) — 图结构维度

纯 numpy 零外部依赖(不依赖 pandas/torch)。补上 XGBoost 树模型无法捕捉的"图结构维度"：
1. DTW 形态相似度 — 找形态相似的股票(龙头涨停→形态相似跟风股)
2. PageRank 中心性 — 图节点重要性
3. 度数中心性 — 联动密度
4. 行业超额收益 — 同行业平均超额

用法:
    from relation_features import dtw_similarity, pagerank, find_similar_peers
    # 找形态相似股: 给一个收益率序列, 找最相似的 top_k
"""

import numpy as np


# ══════════ DTW 形态相似度 (O(T²), Sakoe-Chiba band 10%) ══════════

def dtw_distance(x, y):
    """两序列 DTW 距离 (平方欧氏 + Sakoe-Chiba band 10% 加速)。"""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    T = len(x)
    if T == 0 or len(y) == 0:
        return 0.0
    w = max(1, int(T * 0.1))  # band 宽度
    dtw = np.full((T + 1, T + 1), np.inf)
    dtw[0, 0] = 0.0
    for i in range(1, T + 1):
        lo = max(1, i - w)
        hi = min(T, i + w)
        for j in range(lo, hi + 1):
            cost = (x[i - 1] - y[j - 1]) ** 2
            dtw[i, j] = cost + min(dtw[i - 1, j], dtw[i, j - 1], dtw[i - 1, j - 1])
    return float(np.sqrt(dtw[T, T]))


def dtw_similarity(x, y):
    """DTW 距离 → 相似度 [0,1] (1=完全相同形态)。"""
    dist = dtw_distance(x, y)
    max_dist = (np.sqrt(np.sum((np.asarray(x) - np.asarray(y)) ** 2))
                + np.sqrt(np.sum(np.asarray(x) ** 2))
                + np.sqrt(np.sum(np.asarray(y) ** 2)))
    if max_dist < 1e-8:
        return 1.0
    return float(max(0.0, 1.0 - dist / max_dist))


# ══════════ PageRank 中心性 (纯 numpy) ══════════

def pagerank(A, alpha=0.85, max_iter=100):
    """PageRank on (N,N) 邻接矩阵。返回 (N,) 中心性向量。"""
    A = np.asarray(A, dtype=np.float64)
    N = A.shape[0]
    if N == 0:
        return np.array([])
    out = np.ones(N, dtype=np.float64) / N
    deg = A.sum(axis=1)
    deg_safe = np.where(deg > 0, deg, 1.0)
    M = A / deg_safe[:, None]  # 转移矩阵
    for _ in range(max_iter):
        new_out = alpha * (M.T @ out) + (1 - alpha) / N
        if np.abs(new_out - out).sum() < 1e-8:
            break
        out = new_out
    return out


def degree_centrality(A):
    """归一化度数中心性 (0-1)。"""
    A = np.asarray(A, dtype=np.float64)
    deg = A.sum(axis=1)
    mx = deg.max()
    return deg / mx if mx > 0 else deg


# ══════════ 关系特征 + 形态相似股 ══════════

def find_similar_peers(target_returns, returns_matrix, symbols, top_k=10):
    """找与 target 形态最相似的 top_k 只股票。

    Args:
        target_returns: (T,) 目标股收益率序列
        returns_matrix: (N, T) 所有股票收益率矩阵
        symbols: (N,) 股票代码列表
        top_k: 返回前 k 只
    Returns:
        [(symbol, similarity), ...] 按相似度降序
    """
    sims = []
    for i, sym in enumerate(symbols):
        s = dtw_similarity(target_returns, returns_matrix[i])
        sims.append((sym, s))
    sims.sort(key=lambda x: -x[1])
    return sims[:top_k]


def build_correlation_adjacency(returns_matrix, threshold=0.5):
    """Pearson 相关性邻接矩阵 (|corr| >= threshold 建边, 权重=|corr|)。"""
    corr = np.corrcoef(returns_matrix)
    corr = np.nan_to_num(corr, nan=0.0)
    A = np.abs(corr) >= threshold
    return (A * np.abs(corr)).astype(np.float64)


def relation_features(returns_matrix, adjacency=None):
    """关系特征: degree_centrality + pagerank + dtw_similarity_mean。

    Args:
        returns_matrix: (N, T) 收益率矩阵
        adjacency: (N, N) 邻接矩阵(可选, 默认用相关性构建)
    Returns:
        dict {degree_centrality, pagerank, dtw_similarity_mean} 各 (N,) 数组
    """
    N = returns_matrix.shape[0]
    if adjacency is None:
        adjacency = build_correlation_adjacency(returns_matrix)
    deg = degree_centrality(adjacency)
    pr = pagerank(adjacency)
    # DTW 均值: 每只股票 vs 所有 peers 的平均相似度
    dtw_mean = np.zeros(N)
    for i in range(N):
        sims = [dtw_similarity(returns_matrix[i], returns_matrix[j]) for j in range(N) if j != i]
        dtw_mean[i] = np.mean(sims) if sims else 0.0
    return {
        'degree_centrality': deg,
        'pagerank': pr,
        'dtw_similarity_mean': dtw_mean,
    }


if __name__ == '__main__':
    # 自测: 合成数据
    rng = np.random.default_rng(42)
    N, T = 8, 30
    base = np.cumsum(rng.normal(0, 0.02, T))  # 基准序列
    returns = np.array([base + np.cumsum(rng.normal(0, 0.01, T)) for _ in range(N)])
    symbols = [f'00000{i}' for i in range(N)]

    # DTW 相似度
    s = dtw_similarity(returns[0], returns[1])
    print(f'股票0 vs 股票1 形态相似度: {s:.3f}')

    # 找形态相似股
    peers = find_similar_peers(returns[0], returns, symbols, top_k=3)
    print('最相似 peers:', [(p[0], round(p[1], 3)) for p in peers])

    # 关系特征
    feat = relation_features(returns)
    print('度数中心性:', np.round(feat['degree_centrality'], 3))
    print('PageRank:', np.round(feat['pagerank'], 3))
    print('DTW相似度均值:', np.round(feat['dtw_similarity_mean'], 3))
