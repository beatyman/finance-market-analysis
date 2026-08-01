#!/usr/bin/env python3
"""A股组合优化 — HRP风险平价 + Black-Litterman + Mean-Variance"""
import numpy as np, pandas as pd
import baostock as bs

def fetch_prices(codes, start='2025-08-01', end='2026-08-01'):
    """拉取多只股票的1年日线价格"""
    bs.login()
    prices = pd.DataFrame()
    for code in codes:
        sym = ('sh.' if code.startswith('6') else 'sz.') + code
        rs = bs.query_history_k_data_plus(sym, 'date,close',
            start_date=start, end_date=end, frequency='d', adjustflag='2')
        rows = []
        while rs.error_code == '0' and rs.next():
            rows.append(rs.get_row_data())
        if len(rows) < 100: continue
        s = pd.Series([float(r[1]) for r in rows],
                      index=pd.to_datetime([r[0] for r in rows]),
                      name=code)
        prices[code] = s
    bs.logout()
    return prices

def hrp_optimize(prices, min_weight=0.01):
    """分层风险平价 — 最稳健，适合A股高噪声"""
    from pypfopt import HRPOpt
    if len(prices.columns) < 3:
        return {c: 1.0/len(prices.columns) for c in prices.columns}
    hrp = HRPOpt(prices)
    try:
        hrp.optimize()
        weights = hrp.clean_weights()
        weights = {k: v for k, v in weights.items() if v >= min_weight}
        total = sum(weights.values())
        if total > 0:
            weights = {k: v/total for k, v in weights.items()}
        return weights
    except:
        n = len(prices.columns)
        return {c: 1.0/n for c in prices.columns}

def bl_optimize(prices, views, market_weights=None, risk_aversion=2.5):
    """Black-Litterman — 结合主观观点与市场均衡"""
    from pypfopt import BlackLittermanModel, EfficientFrontier
    from pypfopt.expected_returns import mean_historical_return
    from pypfopt.risk_models import CovarianceShrinkage

    mu = mean_historical_return(prices)
    S = CovarianceShrinkage(prices).ledoit_wolf()
    if market_weights is None:
        mc = {c: 1.0/len(prices.columns) for c in prices.columns}
    else:
        mc = market_weights

    bl = BlackLittermanModel(S, pi=mu, absolute_views=views, mc_sigma_override=0.01)
    ret_bl = bl.bl_returns()
    S_bl = bl.bl_cov()

    ef = EfficientFrontier(ret_bl, S_bl)
    ef.max_sharpe(risk_free_rate=0.017)
    return ef.clean_weights()

def mv_optimize(prices, risk_free=0.017):
    """均值-方差优化 — 最大化夏普比率"""
    from pypfopt import EfficientFrontier
    from pypfopt.expected_returns import mean_historical_return
    from pypfopt.risk_models import CovarianceShrinkage

    mu = mean_historical_return(prices)
    S = CovarianceShrinkage(prices).ledoit_wolf()
    ef = EfficientFrontier(mu, S)
    ef.max_sharpe(risk_free_rate=risk_free)
    return ef.clean_weights()

def optimize_portfolio(buy_codes, max_stocks=20, method='hrp'):
    """主入口: 从买入信号列表生成组合权重
    
    Args:
        buy_codes: list of 6-digit stock codes
        max_stocks: cap stocks for data quality
        method: 'hrp' | 'bl' | 'mv'
    
    Returns:
        dict: {code: weight} or None
    """
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
    elif method == 'bl':
        # Convert BSP signals to views: 3D score > 50 → bullish
        views = {}  # Placeholder — pass scores from caller
        weights = bl_optimize(prices, views)
    else:
        weights = mv_optimize(prices)
    
    print(f'  组合优化({method.upper()}): {sum(weights.values()):.0%}权重')
    return weights

if __name__ == '__main__':
    # Quick demo
    codes = ['600019','000630','600030','002475','601138']
    w = optimize_portfolio(codes, method='hrp')
    if w:
        for c, wt in sorted(w.items(), key=lambda x: -x[1]):
            print(f'  {c}: {wt:.1%}')
