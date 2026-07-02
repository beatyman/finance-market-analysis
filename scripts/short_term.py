#!/usr/bin/env python3
"""
短线交易增强模块 v1.0
集成自 agent-stock 超短线框架 + 缠论中枢

六维评分:
  行情(10%) + 技术(25%) + 日内(15%) + 资金(30%) + 板块(10%) + 消息(10%)

决策矩阵: 分数 × 市场状态(主升/震荡/退潮) → 仓位控制
风控: 3%短线止损 | 20%单票上限 | 3日时间止损
"""

import numpy as np
import statistics


def score_stock(code, name, price, chan_signal, rsi, macd, bb, vol_ratio, turnover,
                main_flow, sector_strength, news_score, market_regime='震荡偏弱'):
    """
    六维评分 — 结合缠论中枢
    
    Args:
        chan_signal: 缠论买卖点 (Buy-一买/Buy-二买/Sell-一卖等)
        rsi: RSI(14) 数值
        macd: dict with 'trend' (bullish/bearish)
        bb: dict with 'position' (布林带位置百分比)
        vol_ratio: 量比
        turnover: 换手率
        main_flow: 主力净流入方向 (positive/negative/neutral)
        sector_strength: 板块强度 (0-10)
        news_score: 消息面 (0-10)
        market_regime: 主升/震荡偏强/震荡偏弱/退潮/冰点
    
    Returns:
        dict with total_score, grade, position, decision
    """
    
    # 1. 实时行情 (10%)
    price_score = 5  # neutral base
    if vol_ratio > 1.5 and price > 0: price_score += 3
    elif vol_ratio < 0.8: price_score -= 2
    if turnover > 5: price_score += 2
    elif turnover < 1: price_score -= 1
    price_score = min(10, max(0, price_score))
    
    # 2. 技术面 (25%) — 核心: 缠论信号
    tech_score = 0
    
    # 缠论权重最高
    if 'Buy-一买' in str(chan_signal): tech_score += 15
    elif 'Buy-二买' in str(chan_signal): tech_score += 12
    elif 'Buy-三买' in str(chan_signal): tech_score += 10
    elif 'Sell' in str(chan_signal): tech_score -= 10
    else: tech_score += 5  # Hold
    
    # RSI
    if 30 <= rsi <= 40: tech_score += 3  # 超卖反弹
    elif rsi < 20: tech_score += 5  # 极端超卖
    elif rsi > 80: tech_score -= 4  # 超买
    
    # MACD
    if macd.get('trend') == 'bullish': tech_score += 3
    else: tech_score -= 2
    
    # 布林带
    if bb.get('position', 50) < 20: tech_score += 2  # 下轨附近
    elif bb.get('position', 50) > 80: tech_score -= 2  # 上轨附近
    
    tech_score = min(25, max(0, tech_score))
    
    # 3. 资金流向 (30%) — 超短线最核心
    if main_flow == 'strong_inflow': flow_score = 28
    elif main_flow == 'inflow': flow_score = 22
    elif main_flow == 'neutral': flow_score = 15
    elif main_flow == 'outflow': flow_score = 8
    else: flow_score = 5  # strong_outflow
    flow_score = min(30, flow_score)
    
    # 4. 日内走势 (15%) — 简化版(无5分钟数据时用代理指标)
    intraday = 8  # neutral
    if bb['position'] < 30 and rsi < 40: intraday += 4  # 可能超卖反弹
    if bb['position'] > 70 and rsi > 60: intraday -= 3
    intraday = min(15, max(0, intraday))
    
    # 5. 板块强度 (10%)
    sector_score = min(10, sector_strength)
    
    # 6. 消息面 (10%)
    news = min(10, news_score)
    
    # === 汇总 ===
    total = price_score + tech_score + flow_score + intraday + sector_score + news
    
    # 维度冲突修正
    corrections = []
    # 资金强 + 技术超买
    if flow_score >= 24 and rsi > 75:
        total -= 5
        corrections.append('资金强但技术超买-5')
    # 资金弱 + 技术强
    if flow_score <= 8 and tech_score >= 18:
        total -= 3
        corrections.append('技术好但资金不配合-3')
    # 板块强 + 资金弱
    if sector_score >= 8 and flow_score <= 8:
        total -= 2
        corrections.append('板块强但个股资金不跟-2')
    
    total = max(0, min(100, total))
    
    # 决策矩阵
    regime_matrix = {
        '主升':       [(80, 'A', '低吸建仓', 20), (65, 'B', '试探仓', 15), (50, 'C', '试探仓', 10), (0, 'D', '不介入', 0)],
        '震荡偏强':   [(80, 'A', '低吸建仓', 15), (65, 'B', '试探仓', 10), (50, 'C', '微量试探', 5), (0, 'D', '不介入', 0)],
        '震荡偏弱':   [(80, 'A', '试探仓', 10), (65, 'B', '微量试探', 5), (50, 'C', '不介入', 0), (0, 'D', '不介入', 0)],
        '退潮':       [(80, 'A', '微量试探', 5), (65, 'B', '不介入', 0), (50, 'C', '不介入', 0), (0, 'D', '不介入', 0)],
        '冰点':       [(80, 'D', '不介入', 0), (65, 'D', '不介入', 0), (50, 'D', '不介入', 0), (0, 'D', '不介入', 0)],
    }
    
    regime = regime_matrix.get(market_regime, regime_matrix['震荡偏弱'])
    grade = None
    position = 0
    decision = '不介入'
    
    for threshold, g, dec, pos in regime:
        if total >= threshold:
            grade = g
            decision = dec
            position = pos
            break
    
    # 风控规则
    risk_rules = {
        'single_max': 20,  # 单票上限20%
        'stop_loss_pct': 3,  # 短线止损-3%
        'time_stop_days': 3,  # 3日时间止损
        'no_averaging': True,  # 禁止亏损加仓
        'no_chasing': True,  # 禁止追高>7%
    }
    
    return {
        'total_score': total,
        'grade': grade,
        'decision': decision,
        'position_pct': position,
        'scores': {
            '行情': price_score,
            '技术面': tech_score,
            '日内走势': intraday,
            '资金流向': flow_score,
            '板块强度': sector_score,
            '消息面': news,
        },
        'corrections': corrections,
        'risk_rules': risk_rules,
        'market_regime': market_regime,
    }


def quick_decision(price, chan_signal, rsi=50, vol_ratio=1.0, main_flow='neutral',
                   market='震荡偏弱', bb_pos=50, macd_trend='neutral'):
    """
    快速决策 — 最少参数版
    """
    return score_stock(
        code='', name='', price=price,
        chan_signal=chan_signal, rsi=rsi, macd={'trend': macd_trend},
        bb={'position': bb_pos}, vol_ratio=vol_ratio, turnover=2,
        main_flow=main_flow, sector_strength=5, news_score=5,
        market_regime=market
    )


if __name__ == '__main__':
    # 测试: 腾讯
    r = quick_decision('0700', '腾讯', 439, 'Buy-一买', rsi=39, vol_ratio=0.8,
                        main_flow='neutral', market='震荡偏弱', bb_pos=44, macd_trend='bearish')
    print(f"腾讯: {r['total_score']}分 {r['grade']}级 {r['decision']} {r['position_pct']}%仓")
    
    # 测试: 江铜
    r = quick_decision('600362', '江西铜业', 42, 'Buy-二买', rsi=35, vol_ratio=1.2,
                        main_flow='inflow', market='震荡偏弱', bb_pos=35, macd_trend='bearish')
    print(f"江铜: {r['total_score']}分 {r['grade']}级 {r['decision']} {r['position_pct']}%仓")
