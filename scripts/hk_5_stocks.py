#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""5大龙头四维交叉验证 + 关键点位"""
import sys
sys.path.insert(0, '/root/.hermes/skills/a-share-market-analysis/scripts')
import pandas as pd
from hk_warrant import AAStocksWarrantFetcher
from hk_short import HKShortAnalyzer

STOCKS = {
    '00700': '腾讯控股', '09988': '阿里巴巴-W', '03690': '美团-W',
    '01024': '快手-W', '01810': '小米集团-W',
}

def parse_amount(s):
    if s is None: return 0.0
    s = str(s).strip()
    if not s or s in ('-', 'N/A', '0.00', '0'): return 0.0
    mult = 1.0
    if '亿' in s: mult = 1e8
    elif '百万' in s: mult = 1e6
    elif '万' in s: mult = 1e4
    try: return float(s.replace('亿','').replace('百万','').replace('万','').replace(',','')) * mult
    except: return 0.0

def parse_pct(s):
    if s is None: return 0.0
    s = str(s).strip().replace('%','').replace(',','')
    try: return float(s)
    except: return 0.0

f = AAStocksWarrantFetcher()
hs = HKShortAnalyzer()

results = []
for code, name in STOCKS.items():
    # 窝轮 + 牛熊证
    try:
        dw = f.fetch_derivative_data(code, data_type=1)
        dc = f.fetch_derivative_data(code, data_type=2)
    except Exception as e:
        dw = dc = None
    # 沽空流量
    try:
        hs_r = hs.analyze_single_stock(code, name, days=15)
    except Exception:
        hs_r = None

    r = {'code': code, 'name': name}

    # 窝轮: 认购/认沽成交额比
    if dw is not None and len(dw):
        dw['turn_num'] = dw['turnover'].apply(parse_amount)
        call_t = dw[dw['type']=='认购']['turn_num'].sum()
        put_t = dw[dw['type']=='认沽']['turn_num'].sum()
        r['warrant_call_put'] = round(call_t/put_t, 2) if put_t > 0 else float('inf')
        r['warrant_n'] = len(dw)
        r['warrant_call_n'] = len(dw[dw['type']=='认购'])
        r['warrant_put_n'] = len(dw[dw['type']=='认沽'])
    else:
        r['warrant_call_put'] = None

    # 牛熊证: 牛/熊街货比 + 重货收回价
    if dc is not None and len(dc):
        dc['out_num'] = dc['outstanding'].apply(parse_amount)
        bull = dc[dc['type']=='牛']
        bear = dc[dc['type']=='熊']
        bull_out = bull['out_num'].sum()
        bear_out = bear['out_num'].sum()
        r['cbbc_bull_bear'] = round(bull_out/bear_out, 2) if bear_out > 0 else float('inf')
        r['cbbc_n'] = len(dc)
        # 牛证重货收回价(街货Top3) = 散户防守位
        if len(bull):
            bull_top = bull.nlargest(3, 'out_num')
            r['bull_call_levels'] = [str(x) for x in bull_top['call_level'].tolist()]
        else:
            r['bull_call_levels'] = []
        # 熊证重货收回价(街货Top3) = 散户压力位
        if len(bear):
            bear_top = bear.nlargest(3, 'out_num')
            r['bear_call_levels'] = [str(x) for x in bear_top['call_level'].tolist()]
        else:
            r['bear_call_levels'] = []
    else:
        r['cbbc_bull_bear'] = None

    # 沽空流量 + 淡仓存量
    if hs_r and hs_r.get('status') == 'success':
        s = hs_r['summary']
        r['short_ratio_latest'] = s.get('latest_short_ratio')
        r['short_ratio_avg15'] = s.get('avg_short_ratio')
        r['open_short_pct'] = s.get('open_short_pct_mktcap')
    else:
        r['short_ratio_latest'] = r['short_ratio_avg15'] = r['open_short_pct'] = None

    results.append(r)

def classify_divergence(r):
    """背离象限分类: 散户(窝轮+牛熊) vs 机构(沽空+淡仓)。"""
    w = r.get('warrant_call_put')
    c = r.get('cbbc_bull_bear')
    sr = r.get('short_ratio_latest')
    os_ = r.get('open_short_pct')

    # 散户方向合成: 窝轮+牛熊各一票, >1.2看多 <0.8看空
    retail_bull = retail_bear = 0
    if w is not None:
        if w > 1.2:
            retail_bull += 1
        elif w < 0.8:
            retail_bear += 1
    if c is not None:
        if c > 1.2:
            retail_bull += 1
        elif c < 0.8:
            retail_bear += 1
    retail = '看多' if retail_bull > retail_bear else ('看空' if retail_bear > retail_bull else '中性')

    # 机构方向: 淡仓存量(累计空头,主信号) + 当日沽空率(短期做空,辅信号)
    if os_ is not None and os_ >= 5:
        inst = '看空'      # 淡仓重仓(累计空头最重, 最高置信度)
    elif sr is not None and sr >= 25:
        inst = '看空'      # 当日沽空率高(短期做空)
    elif os_ is not None and os_ >= 1:
        inst = '中性'
    elif sr is not None and sr >= 15:
        inst = '中性'
    else:
        inst = '看多'

    # 淡仓压力(累计空头)
    short_pos = '重仓' if (os_ is not None and os_ >= 5) else ('中等' if (os_ is not None and os_ >= 1) else '轻仓')

    # 背离象限
    if retail == '看多' and inst == '看空':
        label = '🔴逼空燃料(散多+机空重)' if short_pos == '重仓' else '🟠接飞刀(机空+散买)'
    elif retail == '看空' and inst == '看空':
        label = '🔴双看空(回避)'
    elif retail == '看多' and inst in ('看多', '中性'):
        label = '🟢健康(散多+机不空)'
    elif retail == '看空' and inst in ('看多', '中性'):
        label = '🔵底部候选(散恐慌+机回补)'
    else:
        label = '⚪中性/分歧'
    return label, retail, inst, short_pos


# 输出对比表
print('=' * 105)
print('5大龙头 四维交叉验证对比 (窝轮/牛熊证/沽空流量/淡仓存量)')
print('=' * 105)
hdr = f"{'名称':<10} {'窝轮购/沽':<10} {'牛熊牛/熊':<10} {'沽空率':<8} {'淡仓%':<8} {'散户':<6} {'机构':<6} {'背离象限'}"
print(hdr)
print('-' * 105)
for r in results:
    w = r.get('warrant_call_put')
    c = r.get('cbbc_bull_bear')
    sr = r.get('short_ratio_latest')
    os_ = r.get('open_short_pct')
    label, retail, inst, short_pos = classify_divergence(r)
    print(f"{r['name']:<10} {str(w)+'x':<10} {str(c)+'x':<10} {str(sr)+'%':<8} {str(os_)+'%':<8} "
          f"{retail:<6} {inst:<6} {label}")

print()
print('=' * 100)
print('关键点位 (牛熊证重货收回价)')
print('=' * 100)
for r in results:
    bull = r.get('bull_call_levels', [])
    bear = r.get('bear_call_levels', [])
    print(f"{r['name']} ({r['code']}):")
    print(f"  牛证重货收回价(散户防守位): {', '.join(bull) if bull else '无'}")
    print(f"  熊证重货收回价(散户压力位): {', '.join(bear) if bear else '无'}")
