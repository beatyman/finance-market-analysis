#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基本面六项评分 (吸收 Stock-Analysis-3D) — 30 分制

PE 5 + PB 5 + ROE 5 + 营收增速 5 + 毛利率 5 + 负债率 5 = 30 分
纯函数、零外部依赖。

用法:
    from fundamental_score import fundamental_score
    r = fundamental_score(pe=13.5, pb=1.76, roe=15.06,
                          revenue_yoy=15.5, gross_margin=30.66, debt_to_asset=17.93)
    # r = {'total': 26, 'max': 30, 'rating': '优秀', 'breakdown': {...}, 'notes': {...}}

用途: 补上三维评分里"基本面"的真缺口(原 fund_score = v45经验分 + gzk 都是技术面)。
     配合缠论中枢 + S&R + 筹码 + 资金流做五维交叉验证。
"""


def score_pe(pe):
    """PE 估值 (5分)。低=便宜; 负值=亏损。"""
    if pe is None:
        return 2, '数据缺失'
    if pe <= 0:
        return 0, f'PE={pe:.1f} 亏损或负值'
    if pe < 15:
        return 5, f'PE={pe:.1f} 便宜'
    if pe < 25:
        return 4, f'PE={pe:.1f} 合理'
    if pe < 40:
        return 3, f'PE={pe:.1f} 偏贵'
    if pe < 60:
        return 1, f'PE={pe:.1f} 高估'
    return 0, f'PE={pe:.1f} 极度高估'


def score_pb(pb):
    """PB 估值 (5分)。"""
    if pb is None:
        return 2, '数据缺失'
    if pb <= 0:
        return 0, f'PB={pb:.2f} 异常'
    if pb < 2:
        return 5, f'PB={pb:.2f} 便宜'  # <1 破净也 5 分
    if pb < 4:
        return 4, f'PB={pb:.2f} 合理'
    if pb < 6:
        return 2, f'PB={pb:.2f} 偏贵'
    return 0, f'PB={pb:.2f} 昂贵'


def score_roe(roe):
    """ROE (5分)。%"""
    if roe is None:
        return 2, '数据缺失'
    if roe >= 20:
        return 5, f'ROE={roe:.1f}% 高质量'
    if roe >= 15:
        return 4, f'ROE={roe:.1f}% 优秀'
    if roe >= 10:
        return 3, f'ROE={roe:.1f}% 一般'
    if roe >= 5:
        return 2, f'ROE={roe:.1f}% 偏弱'
    if roe >= 0:
        return 1, f'ROE={roe:.1f}% 很弱'
    return 0, f'ROE={roe:.1f}% 亏损'


def score_revenue_yoy(yoy):
    """营收增速 (5分)。%"""
    if yoy is None:
        return 2, '数据缺失'
    if yoy >= 50:
        return 5, f'营收YoY={yoy:.1f}% 高速增长'
    if yoy >= 20:
        return 4, f'营收YoY={yoy:.1f}% 强劲'
    if yoy >= 10:
        return 3, f'营收YoY={yoy:.1f}% 稳健'
    if yoy >= 0:
        return 2, f'营收YoY={yoy:.1f}% 缓慢'
    if yoy >= -10:
        return 1, f'营收YoY={yoy:.1f}% 下滑'
    return 0, f'营收YoY={yoy:.1f}% 大幅下滑'


def score_gross_margin(gm):
    """毛利率 (5分)。%"""
    if gm is None:
        return 2, '数据缺失'
    if gm >= 50:
        return 5, f'毛利率={gm:.1f}% 高毛利'
    if gm >= 30:
        return 4, f'毛利率={gm:.1f}% 健康'
    if gm >= 20:
        return 3, f'毛利率={gm:.1f}% 一般'
    if gm >= 10:
        return 2, f'毛利率={gm:.1f}% 偏低'
    if gm > 0:
        return 1, f'毛利率={gm:.1f}% 低毛利'
    return 0, f'毛利率={gm:.1f}% 负毛利'


def score_debt(da):
    """资产负债率 (5分)。%"""
    if da is None:
        return 2, '数据缺失'
    if da < 30:
        return 5, f'负债率={da:.1f}% 非常健康'
    if da < 50:
        return 4, f'负债率={da:.1f}% 健康'
    if da < 65:
        return 3, f'负债率={da:.1f}% 一般'
    if da < 80:
        return 1, f'负债率={da:.1f}% 高杠杆'
    return 0, f'负债率={da:.1f}% 高风险'


def fundamental_score(pe=None, pb=None, roe=None, revenue_yoy=None,
                      gross_margin=None, debt_to_asset=None):
    """基本面六项评分, 30分制。返回 {total, max, breakdown, notes, rating}"""
    items = [
        ('pe', score_pe, pe),
        ('pb', score_pb, pb),
        ('roe', score_roe, roe),
        ('revenue_yoy', score_revenue_yoy, revenue_yoy),
        ('gross_margin', score_gross_margin, gross_margin),
        ('debt_to_asset', score_debt, debt_to_asset),
    ]
    breakdown, notes = {}, {}
    for key, fn, val in items:
        s, n = fn(val)
        breakdown[key] = s
        notes[key] = n
    total = sum(breakdown.values())
    if total >= 24:
        rating = '优秀'
    elif total >= 18:
        rating = '良好'
    elif total >= 12:
        rating = '中等'
    elif total >= 6:
        rating = '偏弱'
    else:
        rating = '差'
    return {
        'total': total, 'max': 30,
        'breakdown': breakdown, 'notes': notes, 'rating': rating,
    }


if __name__ == '__main__':
    # 自测: 沃尔核材(README示例) + 茅台
    r1 = fundamental_score(pe=13.51, pb=1.76, roe=15.06,
                           revenue_yoy=15.5, gross_margin=30.66, debt_to_asset=17.93)
    print('沃尔核材示例:', r1['total'], '/', r1['max'], r1['rating'], r1['breakdown'])
    r2 = fundamental_score(pe=28.5, pb=9.8, roe=31.2,
                           revenue_yoy=18.0, gross_margin=91.5, debt_to_asset=21.0)
    print('贵州茅台:', r2['total'], '/', r2['max'], r2['rating'], r2['breakdown'])
