#!/usr/bin/env python3
"""
A股组合优化 — Alpha-Risk 混合 + HRP 风险平价 + 仓位约束

Pipeline:
  1. Quality Filter: Buy + 中枢内 + R:R≥1.0 + prod_xgb≥40
  2. Alpha Score: 生产XGB(35%) + 3D分(25%) + V4.5(20%) + R:R(20%)
  3. HRP 风险结构 → 纯风险平价权重
  4. Alpha 倾斜: 风险权重 × (1 + α_zscore × tilt) 
  5. 仓位约束: max≤20%, min≥2%, 归一化
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple


def fetch_prices(codes, start='2025-08-01', end='2026-08-01'):
    """拉取多只股票的1年日线价格(新浪数据源, baostock已拉黑)"""
    import sys, os
    HERE = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, HERE)
    from tencent_data import fetch_kline
    prices = pd.DataFrame()
    for code in codes:
        try:
            dates, opens, highs, lows, closes, vols = fetch_kline(code)
            if len(dates) < 100:
                continue
            s = pd.Series(closes, index=pd.to_datetime(dates), name=code)
            prices[code] = s
        except:
            continue
    return prices


def hrp_optimize(prices, min_weight=0.01):
    """分层风险平价 — 协方差聚类 + 递归二分"""
    from pypfopt import HRPOpt
    if len(prices.columns) < 3:
        return {c: 1.0 / len(prices.columns) for c in prices.columns}
    hrp = HRPOpt(prices)
    try:
        hrp.optimize()
        weights = hrp.clean_weights()
        weights = {k: v for k, v in weights.items() if v >= min_weight}
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}
        return weights
    except:
        n = len(prices.columns)
        return {c: 1.0 / n for c in prices.columns}


def compute_alpha_score(prod_xgb: float, score3d: float, v45: float, 
                         rr: float, gzk: float) -> float:
    """
    多因子 Alpha 评分 (0-100)
    
    因子权重:
      - 生产XGB (35%): 纯技术面信号强度
      - 3D综合分 (25%): 技术+基本+消息共振
      - V4.5经验 (20%): 回测验证过的买卖规则
      - R:R归一化 (20%): 盈亏比映射到0-100
      - GZK bonus: <5分不加, ≥5额外+3
    """
    # 归一化 R:R: cap at 5, linear to 0-100
    rr_norm = min(max(rr, 0), 5.0) / 5.0 * 100
    
    alpha = (prod_xgb * 0.35 + 
             score3d * 0.25 + 
             v45 * 0.20 + 
             rr_norm * 0.20)
    
    # GZK bonus (fundamental quality bonus)
    if gzk >= 5:
        alpha += 3
    
    return round(min(100, max(0, alpha)), 1)


def quality_filter(results: List[dict]) -> List[dict]:
    """
    Stage 1: 质量过滤
    
    条件:
      - Buy 信号
      - 中枢内 (有安全边界)
      - R:R ≥ 1.5 (盈亏比划算, 止损空间≤盈利空间的2/3)
      - 生产XGB ≥ 40 (信号有效)
    """
    filtered = []
    for r in results:
        if not ('Buy' in str(r.get('bsp', ''))):
            continue
        if r.get('in_zs') != '是':
            continue
        if r.get('rr', 0) < 1.5:
            continue
        if r.get('prod_xgb', 0) < 40:
            continue
        filtered.append(r)
    return filtered


def alpha_blended_hrp(
    filtered_stocks: List[dict],
    tilt_factor: float = 0.5,
    max_position: float = 0.20,
    min_position: float = 0.02,
    max_stocks: int = 30,
) -> Tuple[Dict[str, float], Dict[str, dict]]:
    """
    Stage 3-5: Alpha-Risk 混合优化
    
    Args:
        filtered_stocks: quality_filter 输出
        tilt_factor: alpha倾斜力度 (0=纯HRP, 1=全额倾斜)
        max_position: 单只最大仓位
        min_position: 单只最小仓位(低于此剔除)
        max_stocks: 最大股票数
    
    Returns:
        (weights: {code: weight}, metrics: {code: {alpha, hrp_w, final_w, ...}})
    """
    if len(filtered_stocks) < 3:
        print(f'  组合优化: 仅{len(filtered_stocks)}只通过质量过滤, 跳过')
        return {}, {}
    
    # Sort by alpha desc, take top N
    codes = [s['code'] for s in filtered_stocks[:max_stocks]]
    
    # Step 1: Fetch prices & run HRP
    prices = fetch_prices(codes)
    valid_codes = list(prices.columns)
    if len(valid_codes) < 3:
        print(f'  组合优化: 仅{len(valid_codes)}只有效价格数据, 跳过')
        return {}, {}
    
    hrp_weights = hrp_optimize(prices)
    
    # Step 2: Compute alpha scores for each stock
    alpha_map = {}
    for s in filtered_stocks:
        if s['code'] in valid_codes:
            alpha_map[s['code']] = compute_alpha_score(
                s.get('prod_xgb', 0),
                s.get('score3d', 0),
                s.get('v45', 0),
                s.get('rr', 0),
                s.get('gzk', 0),
            )
    
    if not alpha_map:
        return {}, {}
    
    # Step 3: Alpha z-score normalization
    alphas = list(alpha_map.values())
    alpha_mean = np.mean(alphas)
    alpha_std = np.std(alphas) if len(alphas) > 1 else 1.0
    if alpha_std < 1e-8:
        alpha_std = 1.0
    
    # Step 4: Blend HRP with alpha tilt
    blended = {}
    metrics = {}
    
    for code in valid_codes:
        hrp_w = hrp_weights.get(code, 0)
        alpha = alpha_map.get(code, 50)
        alpha_z = (alpha - alpha_mean) / alpha_std
        
        # HRP base × alpha tilt multiplier
        tilt_multiplier = 1.0 + alpha_z * tilt_factor
        # Floor negative tilt at 0.3 (still some allocation for diversification)
        tilt_multiplier = max(0.3, tilt_multiplier)
        
        blended[code] = hrp_w * tilt_multiplier
        metrics[code] = {
            'alpha': alpha,
            'alpha_z': round(alpha_z, 2),
            'hrp_w': round(hrp_w * 100, 1),
            'tilt': round(tilt_multiplier, 2),
        }
    
    # Step 5: Normalize + apply position caps
    total = sum(blended.values())
    if total <= 0:
        return {}, {}
    
    # Normalize
    for code in blended:
        blended[code] /= total
    
    # Apply caps iteratively
    for _ in range(5):  # max 5 iterations for convergence
        capped = False
        for code in list(blended.keys()):
            if blended[code] > max_position:
                excess = blended[code] - max_position
                blended[code] = max_position
                # Redistribute excess to others
                others = [c for c in blended if c != code and blended[c] < max_position]
                if others:
                    total_other = sum(blended[c] for c in others)
                    if total_other > 0:
                        for c in others:
                            blended[c] += excess * (blended[c] / total_other)
                capped = True
        if not capped:
            break
    
    # Normalize one final time
    total = sum(blended.values())
    blended = {k: v / total for k, v in blended.items()}
    
    # Remove below min_position
    blended = {k: v for k, v in blended.items() if v >= min_position}
    total = sum(blended.values())
    if total > 0:
        blended = {k: round(v / total, 4) for k, v in blended.items()}
    
    # Sort by weight desc
    blended = dict(sorted(blended.items(), key=lambda x: -x[1]))
    
    # Update metrics with final weight
    for code in metrics:
        metrics[code]['final_w'] = round(blended.get(code, 0) * 100, 1)
    
    print(f'  组合优化(A+R): {len(blended)}只 | 前3: ' +
          ' '.join(f'{c}({w:.0%})' for c, w in list(blended.items())[:3]))
    
    return blended, metrics


def optimize_portfolio(buy_codes, max_stocks=20, method='hrp'):
    """旧版兼容接口 — 纯HRP，无alpha"""
    if not buy_codes or len(buy_codes) == 0:
        return None
    codes = buy_codes[:max_stocks]
    prices = fetch_prices(codes)
    valid_codes = list(prices.columns)
    if len(valid_codes) < 3:
        print(f'  组合优化: 仅{len(valid_codes)}只有效标的, 跳过')
        return None
    if method == 'hrp':
        weights = hrp_optimize(prices)
    else:
        weights = hrp_optimize(prices)
    print(f'  组合优化({method.upper()}): {sum(weights.values()):.0%}权重')
    return weights


if __name__ == '__main__':
    codes = ['600019', '000630', '600030', '002475', '601138']
    w = optimize_portfolio(codes, method='hrp')
    if w:
        for c, wt in sorted(w.items(), key=lambda x: -x[1]):
            print(f'  {c}: {wt:.1%}')
