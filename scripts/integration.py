#!/usr/bin/env python3
"""
外部集成模块 v1.0
- Kalman滤波波动率追踪 (Financial-Models-Numerical-Methods)
- 做T增强信号

用法:
  from integration import kalman_volatility
  signal = kalman_volatility(prices)
"""

import numpy as np

def kalman_volatility(prices, delta=1e-4, vt=1e-3):
    """
    Kalman滤波实时波动率追踪
    
    Args:
        prices: 价格序列
        delta: 观测噪声 (默认1e-4)
        vt: 状态噪声 (默认1e-3)
    
    Returns:
        dict: {volatility, upper_band, lower_band, signal}
    
    原理: Kalman滤波从价格序列中分离出趋势+波动率,
          比传统布林带更快响应波动率突变
    """
    n = len(prices)
    if n < 5:
        return {'volatility': 0, 'signal': 'insufficient_data'}
    
    # Initialize
    x = prices[0]  # state (true price)
    p = 1.0        # state covariance
    v = 0.01       # volatility estimate
    
    filtered = [x]
    vol_est = [v]
    
    for i in range(1, n):
        # Predict
        x_pred = x
        p_pred = p + vt
        
        # Update
        K = p_pred / (p_pred + delta)
        x = x_pred + K * (prices[i] - x_pred)
        p = (1 - K) * p_pred
        
        # Volatility estimate (EMA of squared errors)
        err = prices[i] - filtered[-1]
        v = 0.94 * v + 0.06 * (err ** 2)
        
        filtered.append(x)
        vol_est.append(v)
    
    # Current volatility (annualized)
    cur_vol = np.sqrt(vol_est[-1])
    ann_vol = cur_vol * np.sqrt(252) / prices[-1] * 100  # annualized %
    
    # Simple bands
    upper = filtered[-1] + 2 * cur_vol
    lower = filtered[-1] - 2 * cur_vol
    
    # Signal
    if prices[-1] < lower:
        signal = 'oversold'
    elif prices[-1] > upper:
        signal = 'overbought'
    else:
        signal = 'neutral'
    
    return {
        'volatility': round(cur_vol, 4),
        'annualized_vol': round(ann_vol, 1),
        'filtered_price': round(filtered[-1], 2),
        'upper_band': round(upper, 2),
        'lower_band': round(lower, 2),
        'signal': signal
    }


def t0_signal(prices_5m, daily_vol_threshold=2.0):
    """
    做T信号增强 — 结合Kalman滤波+振幅判断
    
    Returns:
        str: 'buy_t' / 'sell_t' / 'hold'
    """
    kf = kalman_volatility(prices_5m)
    
    if kf['signal'] == 'insufficient_data':
        return 'hold'
    
    # Amplitude check
    amplitude = (max(prices_5m[-20:]) - min(prices_5m[-20:])) / prices_5m[-1] * 100
    
    if amplitude < daily_vol_threshold:
        return 'hold'
    
    if kf['signal'] == 'oversold' and amplitude > 3:
        return 'buy_t'
    elif kf['signal'] == 'overbought' and amplitude > 3:
        return 'sell_t'
    
    return 'hold'


if __name__ == '__main__':
    # Quick test
    import random
    test_prices = [100 + random.gauss(0, 1) for _ in range(50)]
    result = kalman_volatility(test_prices)
    print(f"Kalman: vol={result['volatility']:.4f}, signal={result['signal']}")
    print(f"T0 Signal: {t0_signal(test_prices)}")
