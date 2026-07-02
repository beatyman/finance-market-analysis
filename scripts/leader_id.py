#!/usr/bin/env python3
"""
龙头识别模块 v1.0
集成自 A Stock Leader Identification + 缠论中枢

核心逻辑:
  1. 启动信号: 首板涨停+倍量 → 龙头候选
  2. 强度验证: 连板+封单+换手 → 真龙确认
  3. 辨识度: 板块共振+市场地位 → 龙头溢价
  4. 排除杂毛: 蹭概念+无板块共振+缩量 → 过滤

与缠论中枢结合: 龙头股优先在中枢内筛选
"""


def identify_leader(stock_pool, chan_data, market_data, sector_heat):
    """
    龙头识别主函数
    
    Args:
        stock_pool: [{code, name, price, change_pct, vol_ratio, turnover, limit_up, consecutive_boards}]
        chan_data: {code: {signal, has_zs, in_zs, zs_range}}
        market_data: {up_count, down_count, total_count, index_change}
        sector_heat: {sector_name: {change_pct, leading_stocks}}
    
    Returns:
        [{code, name, leader_score, leader_level, reason}]
    """
    leaders = []
    
    for stock in stock_pool:
        code = stock['code']
        score = 0
        reasons = []
        
        # === 1. 启动信号 (30分) ===
        
        # 涨停/接近涨停 (15分)
        if stock.get('limit_up'):
            score += 15
            reasons.append('涨停')
        elif stock.get('change_pct', 0) >= 7:
            score += 10
            reasons.append(f'大涨+{stock["change_pct"]:.1f}%')
        
        # 放量 (15分)
        vol = stock.get('vol_ratio', 1)
        if vol >= 3.0:
            score += 15
            reasons.append('巨量3x')
        elif vol >= 2.0:
            score += 12
            reasons.append('倍量2x')
        elif vol >= 1.5:
            score += 8
            reasons.append('放量1.5x')
        
        # === 2. 强度验证 (25分) ===
        
        # 连板强度 (15分)
        cb = stock.get('consecutive_boards', 0)
        if cb >= 3:
            score += 15
            reasons.append(f'{cb}连板-强势')
        elif cb == 2:
            score += 12
            reasons.append('2连板')
        elif cb == 1:
            score += 8
            reasons.append('首板')
        
        # 换手健康 (10分)
        turnover = stock.get('turnover', 0)
        if 5 <= turnover <= 20:
            score += 10
            reasons.append(f'换手{turnover:.0f}%-健康')
        elif 2 <= turnover < 5:
            score += 6
            reasons.append(f'换手{turnover:.0f}%-适中')
        elif turnover > 30:
            score += 2  # 换手过高，警惕出货
            reasons.append(f'换手{turnover:.0f}%-过高警告')
        
        # === 3. 辨识度 (25分) ===
        
        # 缠论中枢确认 (15分)
        cd = chan_data.get(code, {})
        if cd.get('in_zs'):
            score += 15
            reasons.append(f"中枢内{cd.get('zs_range','')}")
        elif cd.get('has_zs'):
            zs_str = str(cd.get('zs_range', ''))
            price = stock['price']
            # 在中枢上方 = 突破
            score += 8
            reasons.append(f'中枢附近{zs_str}')
        
        # Buy信号加成 (10分)
        signal = cd.get('signal', '')
        if 'Buy-一买' in str(signal): score += 10
        elif 'Buy-二买' in str(signal): score += 8
        elif 'Buy-三买' in str(signal): score += 6
        elif 'Buy' in str(signal): score += 4
        
        # === 4. 板块共振 (20分) ===
        
        # 所在板块是否领涨 (10分)
        sector_name = stock.get('sector', '')
        if sector_name in sector_heat:
            sh = sector_heat[sector_name]
            if sh['change_pct'] >= 5:
                score += 10
                reasons.append(f'{sector_name}+{sh["change_pct"]:.1f}%')
            elif sh['change_pct'] >= 2:
                score += 6
            elif sh['change_pct'] > 0:
                score += 3
        
        # 板块内地位 (10分)
        leading = sector_heat.get(sector_name, {}).get('leading_stocks', [])
        rank = leading.index(code) if code in leading else len(leading) + 1
        if rank == 0:
            score += 10
            reasons.append('板块龙头')
        elif rank <= 3:
            score += 5
            reasons.append(f'板块第{rank+1}')
        
        # === 5. 市场环境 (-10~0, 仅扣分) ===
        up_ratio = market_data['up_count'] / max(market_data['total_count'], 1)
        limit_down = market_data.get('limit_down_count', 0)
        
        if up_ratio < 0.3:
            score -= 10
            reasons.append('市场冰点')
        elif up_ratio < 0.5:
            score -= 5
            reasons.append('市场偏弱')
        if limit_down > 20:
            score -= 5
            reasons.append(f'{limit_down}只跌停')
        
        # === 过滤杂毛 ===
        if score < 30:
            continue  # 不通过最低门槛
        
        # 没有板块共振但涨停 → 蹭概念嫌疑
        if sector_name not in sector_heat and stock.get('limit_up'):
            score -= 10
            reasons.append('蹭概念-无板块共振')
        
        leaders.append({
            'code': code,
            'name': stock['name'],
            'price': stock['price'],
            'leader_score': max(0, min(100, score)),
            'leader_level': 'S' if score >= 80 else 'A' if score >= 60 else 'B',
            'reasons': reasons,
            'chan_signal': signal,
        })
    
    # 按龙头分排序
    leaders.sort(key=lambda x: -x['leader_score'])
    return leaders


def leader_level_advice(score, level):
    """
    龙头级别对应的操作建议
    """
    if level == 'S' and score >= 80:
        return {
            'action': '龙头-重仓',
            'position': '15-20%',
            'entry': '回踩5日线或分时承接',
            'stop': '-3%短线止损',
            'cycle': '3-5天',
        }
    elif level == 'A' or (level == 'S' and score >= 60):
        return {
            'action': '强股-试探',
            'position': '10-15%',
            'entry': '放量突破前高或中枢上沿',
            'stop': '-3%短线止损',
            'cycle': '2-3天',
        }
    else:
        return {
            'action': '观察',
            'position': '≤5%',
            'entry': '等回踩中枢下沿确认',
            'stop': '买入价-3%',
            'cycle': '1-2天',
        }


if __name__ == '__main__':
    # 测试
    pool = [
        {'code': '002475', 'name': '立讯精密', 'price': 66, 'change_pct': -3, 'vol_ratio': 0.8, 'turnover': 2, 'limit_up': False, 'consecutive_boards': 0, 'sector': '消费电子'},
        {'code': '002837', 'name': '英维克', 'price': 72, 'change_pct': 5, 'vol_ratio': 2.5, 'turnover': 8, 'limit_up': False, 'consecutive_boards': 0, 'sector': '液冷'},
    ]
    chan = {'002475': {'signal': 'Buy-二买', 'in_zs': False, 'has_zs': True, 'zs_range': '67~78'},
            '002837': {'signal': 'Buy-二买', 'in_zs': True, 'has_zs': True, 'zs_range': '70~85'}}
    mkt = {'up_count': 1200, 'down_count': 2800, 'total_count': 4000, 'limit_down_count': 15}
    sectors = {'液冷': {'change_pct': 3.5, 'leading_stocks': ['002837']}}
    
    leaders = identify_leader(pool, chan, mkt, sectors)
    for l in leaders:
        adv = leader_level_advice(l['leader_score'], l['leader_level'])
        print(f"{l['name']} 龙头分{l['leader_score']} {l['leader_level']}级 {adv['action']}")
        print(f"  理由: {', '.join(l['reasons'])}")
