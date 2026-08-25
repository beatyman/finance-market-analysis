#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Beneish M-Score 盈余操纵检测 (吸收 equity-research-skill) — 财报质量核查

八变量模型判断财报造假概率。纯函数、零外部依赖。
M > -1.78 → 落入"可能操纵"区(移入逐项手工核查名单)。

用法:
    from beneish_mscore import beneish_mscore, credibility_grade
    r = beneish_mscore(收入t, 应收t, 毛利率t, ppe_t, 流动资产t, 折旧t, sga_t,
                       总资产t, 总负债t, 净利润t, 经营现金流t,
                       收入t1, 应收t1, 毛利率t1, ppe_t1, 流动资产t1, 折旧t1,
                       sga_t1, 总资产t1, 总负债t1)
    # r = {'m_score': ..., 'manipulate': bool, 'vars': {...}}
"""


def beneish_mscore(revenue_t, receivables_t, gross_margin_t, ppe_t, current_assets_t,
                   depreciation_t, sga_t, total_assets_t, total_liabilities_t,
                   net_income_t, cfo_t,
                   revenue_t1, receivables_t1, gross_margin_t1, ppe_t1, current_assets_t1,
                   depreciation_t1, sga_t1, total_assets_t1, total_liabilities_t1):
    """计算 Beneish M-Score (t=本年, t-1=上年)。

    注: 金融/保险不适用(资产负债结构不同); 毛利率传入百分比数值(如 30.5 表示 30.5%)。
    """
    def ratio(num, den, default=1.0):
        return num / den if den not in (0, None) and num is not None else default

    # DSRI 应收/收入指数
    dsri = ratio(receivables_t / revenue_t if revenue_t else 0,
                 receivables_t1 / revenue_t1 if revenue_t1 else 0)
    # GMI 毛利率指数 (毛利率恶化诱发操纵)
    gmi = ratio(gross_margin_t1, gross_margin_t)
    # AQI 资产质量指数 (非流动非PP&E资产占比之比, 费用资本化)
    nca_t = 1 - (ppe_t + current_assets_t) / total_assets_t if total_assets_t else 0
    nca_t1 = 1 - (ppe_t1 + current_assets_t1) / total_assets_t1 if total_assets_t1 else 0
    aqi = ratio(nca_t, nca_t1)
    # SGI 收入增长指数
    sgi = ratio(revenue_t, revenue_t1)
    # DEPI 折旧率指数 (放慢折旧)
    dep_t = depreciation_t / (depreciation_t + ppe_t) if (depreciation_t + ppe_t) else 0
    dep_t1 = depreciation_t1 / (depreciation_t1 + ppe_t1) if (depreciation_t1 + ppe_t1) else 0
    depi = ratio(dep_t1, dep_t)
    # SGAI 费用率指数
    sgai = ratio(sga_t / revenue_t if revenue_t else 0,
                 sga_t1 / revenue_t1 if revenue_t1 else 0)
    # TATA 总应计/总资产 (权重最大项)
    tata = (net_income_t - cfo_t) / total_assets_t if total_assets_t else 0
    # LVGI 杠杆指数
    lvgi = ratio(total_liabilities_t / total_assets_t if total_assets_t else 0,
                 total_liabilities_t1 / total_assets_t1 if total_assets_t1 else 0)

    m = (-4.84 + 0.92 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi
         + 0.115 * depi - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi)

    return {
        'm_score': round(m, 3),
        'manipulate': m > -1.78,
        'vars': {'DSRI': round(dsri, 3), 'GMI': round(gmi, 3), 'AQI': round(aqi, 3),
                 'SGI': round(sgi, 3), 'DEPI': round(depi, 3), 'SGAI': round(sgai, 3),
                 'TATA': round(tata, 3), 'LVGI': round(lvgi, 3)},
    }


def accrual_ratio(net_income, cfo, total_assets):
    """总应计比率 = (净利润 - 经营现金流) / 平均总资产。> 10% 红旗(Sloan 异象)。"""
    if total_assets:
        return round((net_income - cfo) / total_assets * 100, 2)
    return None


def credibility_grade(m_score, accrual, cash_conversion=None):
    """财报可信度评级 A/B/C/D (预注册)。

    Args:
        m_score: Beneish M-Score
        accrual: 总应计比率(%)
        cash_conversion: 现金转化率 CFO/净利润(%)
    Returns:
        (grade, 说明)
    """
    red_flags = []
    if m_score is not None and m_score > -1.78:
        red_flags.append(f'M-Score {m_score:.2f} 越限')
    if accrual is not None and accrual > 10:
        red_flags.append(f'应计比率 {accrual:.1f}% > 10%')
    if cash_conversion is not None and cash_conversion < 80:
        red_flags.append(f'现金转化率 {cash_conversion:.0f}% < 80%')

    if len(red_flags) >= 2:
        return 'D', '多项严重红旗叠加，规避'
    if len(red_flags) == 1:
        return 'C', '单项红旗，动作最高"观望"'
    if accrual is not None and 5 <= accrual < 10:
        return 'B', '轻度应计偏高，列入监控'
    return 'A', '无红旗，现金转化健康'


if __name__ == '__main__':
    # 自测: 健康公司(现金转化高) vs 操纵公司(应收激增+应计高)
    # 健康: 收入增长20%, 应收同步, 应计低
    healthy = beneish_mscore(
        revenue_t=120, receivables_t=12, gross_margin_t=30, ppe_t=50, current_assets_t=40,
        depreciation_t=5, sga_t=10, total_assets_t=150, total_liabilities_t=60,
        net_income_t=20, cfo_t=22,
        revenue_t1=100, receivables_t1=10, gross_margin_t1=30, ppe_t1=45, current_assets_t1=35,
        depreciation_t1=4.5, sga_t1=8, total_assets_t1=130, total_liabilities_t1=55)
    print('健康公司 M-Score:', healthy['m_score'], '操纵?', healthy['manipulate'])

    # 操纵: 收入增长10%但应收激增50%, 应计高(净利润远高于CFO)
    fraud = beneish_mscore(
        revenue_t=110, receivables_t=30, gross_margin_t=25, ppe_t=50, current_assets_t=60,
        depreciation_t=3, sga_t=12, total_assets_t=160, total_liabilities_t=90,
        net_income_t=30, cfo_t=5,
        revenue_t1=100, receivables_t1=20, gross_margin_t1=30, ppe_t1=45, current_assets_t1=40,
        depreciation_t1=5, sga_t1=8, total_assets_t1=130, total_liabilities_t1=55)
    print('操纵公司 M-Score:', fraud['m_score'], '操纵?', fraud['manipulate'])
    print('操纵公司变量:', fraud['vars'])
