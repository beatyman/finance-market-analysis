#!/usr/bin/env python3
"""
基本面因子筛选模块 v1.0
集成自 Stock Filter Skills — 多条件筛选+热门因子预设

因子预设:
  成长股: roe>15% + 营收增速>20% + 毛利率>30%
  价值股: PE<15 + PB<2 + 股息率>2%
  质优股: ROE>20% + 毛利率>40% + 负债率<50%
  困境反转: PE<10(历史低位) + 营收降速收窄
  
与缠论结合: 基本面过滤 → 缠论中枢筛选 → 阿娇三买确认
"""


# === 因子预设 ===
FACTOR_PRESETS = {
    '成长股': {
        'roe_min': 15,
        'revenue_growth_min': 20,
        'gross_margin_min': 30,
        'description': 'ROE>15% + 营收增速>20% + 毛利率>30% — 高成长标的'
    },
    '价值股': {
        'pe_max': 15,
        'pb_max': 2,
        'dividend_min': 2,
        'description': 'PE<15 + PB<2 + 股息率>2% — 低估值高分红'
    },
    '质优股': {
        'roe_min': 20,
        'gross_margin_min': 40,
        'debt_ratio_max': 50,
        'description': 'ROE>20% + 毛利率>40% + 负债率<50% — 护城河标的'
    },
    '困境反转': {
        'pe_max': 10,
        'pe_historical_pct_max': 20,  # PE处于历史最低20%分位
        'revenue_decline_narrowing': True,  # 营收降速收窄
        'description': 'PE历史低位 + 营收降速收窄 — 周期底部'
    },
    '小盘成长': {
        'market_cap_max': 200,  # 亿
        'roe_min': 12,
        'revenue_growth_min': 25,
        'description': '市值<200亿 + ROE>12% + 营收增速>25% — 小盘弹性'
    },
    '高现金流': {
        'fcf_positive': True,
        'cash_to_debt_min': 1.0,
        'roe_min': 10,
        'description': '自由现金流为正 + 现金/负债>1 + ROE>10% — 财务安全'
    },
}


def screen_by_preset(stocks, preset_name):
    """
    按因子预设筛选股票
    
    Args:
        stocks: [{code, name, pe, pb, roe, gross_margin, debt_ratio, 
                  revenue_growth, dividend_yield, market_cap, fcf, cash, 
                  pe_historical_pct}]
        preset_name: 预设名称
    
    Returns:
        passed, failed lists
    """
    preset = FACTOR_PRESETS.get(preset_name)
    if not preset:
        return [], []
    
    passed = []
    failed = []
    
    for s in stocks:
        ok = True
        reasons = []
        
        if 'roe_min' in preset and s.get('roe', 0) < preset['roe_min']:
            ok = False
            reasons.append(f"ROE{s.get('roe',0):.0f}%<{preset['roe_min']}%")
        
        if 'revenue_growth_min' in preset and s.get('revenue_growth', 0) < preset['revenue_growth_min']:
            ok = False
            reasons.append(f"营收增速{s.get('revenue_growth',0):.0f}%<{preset['revenue_growth_min']}%")
        
        if 'gross_margin_min' in preset and s.get('gross_margin', 0) < preset['gross_margin_min']:
            ok = False
            reasons.append(f"毛利率{s.get('gross_margin',0):.0f}%<{preset['gross_margin_min']}%")
        
        if 'pe_max' in preset and s.get('pe', 999) > preset['pe_max']:
            ok = False
            reasons.append(f"PE{s.get('pe',0):.0f}>{preset['pe_max']}")
        
        if 'pb_max' in preset and s.get('pb', 999) > preset['pb_max']:
            ok = False
            reasons.append(f"PB{s.get('pb',0):.1f}>{preset['pb_max']}")
        
        if 'dividend_min' in preset and s.get('dividend_yield', 0) < preset['dividend_min']:
            ok = False
            reasons.append(f"股息率{s.get('dividend_yield',0):.1f}%<{preset['dividend_min']}%")
        
        if 'debt_ratio_max' in preset and s.get('debt_ratio', 0) > preset['debt_ratio_max']:
            ok = False
            reasons.append(f"负债率{s.get('debt_ratio',0):.0f}%>{preset['debt_ratio_max']}%")
        
        if 'market_cap_max' in preset and s.get('market_cap', 99999) > preset['market_cap_max']:
            ok = False
            reasons.append(f"市值{s.get('market_cap',0):.0f}亿>{preset['market_cap_max']}亿")
        
        if preset.get('fcf_positive') and not s.get('fcf', 0) > 0:
            ok = False
            reasons.append('自由现金流为负')
        
        if 'cash_to_debt_min' in preset:
            ratio = s.get('cash', 0) / max(s.get('debt', 1), 1)
            if ratio < preset['cash_to_debt_min']:
                ok = False
                reasons.append(f'现金/负债{ratio:.1f}<{preset["cash_to_debt_min"]}')
        
        if ok:
            passed.append(s)
        else:
            failed.append({**s, 'fail_reasons': reasons})
    
    return passed, failed


def quality_score(stock):
    """
    基本面质量评分 (0-100)
    """
    score = 0
    
    # ROE (30分)
    roe = stock.get('roe', 0)
    if roe >= 25: score += 30
    elif roe >= 20: score += 25
    elif roe >= 15: score += 20
    elif roe >= 10: score += 10
    elif roe >= 5: score += 5
    
    # 毛利率 (20分)
    gm = stock.get('gross_margin', 0)
    if gm >= 60: score += 20
    elif gm >= 40: score += 15
    elif gm >= 30: score += 10
    elif gm >= 20: score += 5
    
    # 营收增速 (15分)
    rg = stock.get('revenue_growth', 0)
    if rg >= 30: score += 15
    elif rg >= 20: score += 12
    elif rg >= 10: score += 8
    elif rg >= 0: score += 3
    
    # 估值 (15分) — PE越低越好
    pe = stock.get('pe', 50)
    if 0 < pe <= 10: score += 15
    elif pe <= 15: score += 12
    elif pe <= 20: score += 8
    elif pe <= 30: score += 4
    elif pe > 50: score -= 5
    
    # 负债率 (10分)
    dr = stock.get('debt_ratio', 50)
    if dr <= 20: score += 10
    elif dr <= 40: score += 8
    elif dr <= 60: score += 4
    
    # 现金流 (10分)
    if stock.get('fcf', 0) > 0:
        score += 10
    elif stock.get('operating_cf', 0) > 0:
        score += 5
    
    return max(0, min(100, score))


def best_match_preset(stock):
    """
    自动匹配最佳因子预设
    """
    scores = {}
    for name in FACTOR_PRESETS:
        passed, _ = screen_by_preset([stock], name)
        if passed:
            q = quality_score(stock)
            scores[name] = q
    
    if not scores:
        return '无匹配', quality_score(stock)
    
    best = max(scores, key=scores.get)
    return best, scores[best]


if __name__ == '__main__':
    # 测试: 江西铜业基本面
    jx = {
        'code': '600362', 'name': '江西铜业',
        'pe': 9, 'pb': 0.8, 'roe': 8, 'gross_margin': 12,
        'debt_ratio': 55, 'revenue_growth': 15, 'dividend_yield': 3.5,
        'market_cap': 800, 'fcf': 5, 'cash': 200, 'debt': 300, 'operating_cf': 30,
        'pe_historical_pct': 5
    }
    
    preset, qs = best_match_preset(jx)
    print(f"江西铜业: 最佳预设={preset} 质量分={qs}")
    
    passed, failed = screen_by_preset([jx], '价值股')
    print(f"价值股筛选: {'✅通过' if passed else '❌未通过'}")
    if failed: print(f"  原因: {failed[0]['fail_reasons']}")
