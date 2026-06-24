#!/usr/bin/env python3
"""股指期货持仓分析 — CFFEX数据 + AKShare"""
import akshare as ak
from datetime import datetime,timedelta

def get_futures_position(days=3, symbols=['IF','IM']):
    """获取最近N天股指期货持仓变化"""
    today=datetime.now()
    start=(today-timedelta(days=days)).strftime('%Y%m%d')
    end=today.strftime('%Y%m%d')
    try:
        df=ak.get_rank_sum_daily(start_day=start,end_day=end,vars_list=symbols)
        return df
    except:return None

def analyze_sentiment(df):
    """分析期货持仓情绪"""
    if df is None or len(df)==0:return {'bias':'无数据','detail':[],'summary':''}
    
    latest=df[df['date']==df['date'].max()]
    views=[]
    for _,r in latest.iterrows():
        if '综合' in str(r.get('symbol','')):
            long=int(r.get('long_open_interest_chg_top20',0))
            short=int(r.get('short_open_interest_chg_top20',0))
            net=long-short
            bias='偏多' if net>2000 else('偏空' if net<-2000 else '中性')
            views.append({'index':r['variety'],'long':long,'short':short,'net':net,'bias':bias})
    
    # Summary
    nets=[v['net'] for v in views]
    all_long=all(n>0 for n in nets)
    all_short=all(n<0 for n in nets)
    if all_long:summary='全市场多头共振 — 适合寻找买入机会'
    elif all_short:summary='全市场空头共振 — 谨慎观望'
    else:summary='市场分化 — 选结构最强的方向'
    
    return {'bias':'偏多' if all_long else('偏空' if all_short else '分化'),'detail':views,'summary':summary}

if __name__=='__main__':
    df=get_futures_position()
    if df is not None:
        r=analyze_sentiment(df)
        print('股指期货情绪:',r['bias'])
        for v in r['detail']:
            print('  %s: net %+d %s'%(v['index'],v['net'],v['bias']))
        print(r['summary'])
