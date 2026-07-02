#!/usr/bin/env python3
"""
指标增强模块 v1.0
- 替代TradingView API (TradingView-API Node.js项目 → Python直连)
- 在线获取RSI/MACD/布林带等指标

用法:
  from indicators import get_rsi, get_macd
"""

import numpy as np


def calc_rsi(prices, period=14):
    """计算RSI(14)"""
    if len(prices) < period + 1:
        return 50
    
    deltas = np.diff(prices[-period-1:])
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 1)


def calc_macd(prices, fast=12, slow=26, signal=9):
    """计算MACD"""
    if len(prices) < slow + signal:
        return {'macd': 0, 'signal': 0, 'histogram': 0}
    
    def ema(data, period):
        alpha = 2 / (period + 1)
        result = [data[0]]
        for i in range(1, len(data)):
            result.append(alpha * data[i] + (1 - alpha) * result[-1])
        return np.array(result)
    
    ema_fast = ema(prices, fast)
    ema_slow = ema(prices, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    
    return {
        'macd': round(macd_line[-1], 4),
        'signal': round(signal_line[-1], 4),
        'histogram': round(macd_line[-1] - signal_line[-1], 4),
        'trend': 'bullish' if macd_line[-1] > signal_line[-1] else 'bearish'
    }


def calc_bollinger(prices, period=20, std=2):
    """计算布林带"""
    if len(prices) < period:
        return {'upper': prices[-1], 'middle': prices[-1], 'lower': prices[-1]}
    
    recent = prices[-period:]
    ma = np.mean(recent)
    sigma = np.std(recent)
    
    return {
        'upper': round(ma + std * sigma, 2),
        'middle': round(ma, 2),
        'lower': round(ma - std * sigma, 2),
        'bandwidth': round(2 * std * sigma / ma * 100, 1),
        'position': round((prices[-1] - ma + std * sigma) / (2 * std * sigma) * 100, 0)
    }


def indicator_summary(prices, close_only=True):
    """
    一键汇总所有指标
    
    Returns:
        dict: {rsi, macd, bollinger, signal_strength}
    """
    rsi = calc_rsi(prices)
    macd = calc_macd(prices)
    bb = calc_bollinger(prices)
    
    # Combined signal
    score = 0
    if 30 <= rsi <= 40: score += 1  # oversold
    elif rsi < 20: score += 2
    if macd['trend'] == 'bullish': score += 1
    if bb['position'] < 20: score += 1  # near lower band
    
    strength = 'strong_buy' if score >= 4 else 'buy' if score == 3 else 'neutral' if score == 2 else 'weak'
    
    return {
        'rsi': rsi,
        'macd': macd,
        'bollinger': bb,
        'score': score,
        'signal': strength
    }


if __name__ == '__main__':
    import random
    test = [100 + random.gauss(0, 2) for _ in range(100)]
    s = indicator_summary(test)
    print(f"RSI={s['rsi']} MACD={s['macd']['trend']} BB_pos={s['bollinger']['position']}%")
    print(f"Signal: {s['signal']} (score={s['score']}/4)")
