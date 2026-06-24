#!/usr/bin/env python3
"""股指期货持仓 — 多空详细数据"""
import akshare as ak,time
from datetime import datetime,timedelta

def get_detailed_positions(days=3):
    """获取最近N天详细持仓"""
    today=datetime.now()
    start=(today-timedelta(days=days+5)).strftime('%Y%m%d')
    end=today.strftime('%Y%m%d')
    
    for i in range(3):
        try:
            df=ak.get_rank_sum_daily(start_day=start,end_day=end,vars_list=['IF','IM'])
            return df
        except:time.sleep(5*(i+1))
    return None

def format_futures_report():
    """格式化股指期货报告"""
    df=get_detailed_positions()
    if df is None:return '期货数据获取失败'
    
    latest_date=df['date'].max()
    prev_date=df[df['date']<latest_date]['date'].max()
    
    latest=df[df['date']==latest_date]
    prev=df[df['date']==prev_date]
    
    lines=['## 📈 股指期货持仓 (Top20席位)\n']
    lines.append('| 品种 | 多头持仓 | 空头持仓 | 净持仓 | 多头变动 | 空头变动 | 净变动 | 方向 |')
    lines.append('|------|----------|----------|--------|----------|----------|--------|------|')
    
    for variety in ['IF','IM']:
        l_row=latest[latest['variety']==variety]
        p_row=prev[prev['variety']==variety]
        
        if len(l_row)==0:continue
        l_sym=l_row[l_row['symbol'].str.contains('综合',na=False)]
        # Try aggregate first, then just take the last row
        if len(l_sym)>0:l_agg=l_sym.iloc[0]
        else:l_agg=l_row.iloc[-1]
        
        ll=float(l_agg['long_open_interest_top20']);ls=float(l_agg['short_open_interest_top20'])
        net=ll-ls
        
        if len(p_row)>0:
            p_sym=p_row[p_row['symbol'].str.contains('综合',na=False)]
            if len(p_sym)>0:p_agg=p_sym.iloc[0]
            else:p_agg=p_row.iloc[-1]
            pll=float(p_agg['long_open_interest_top20']);pls=float(p_agg['short_open_interest_top20'])
            lchg=ll-pll;schg=ls-pls;nchg=lchg-schg
        else:lchg=schg=nchg=0
        
        direction='🟢 偏多' if nchg>1000 else('🔴 偏空' if nchg<-1000 else '🟡 中性')
        lines.append(f'| **{variety}** | {int(ll):,} | {int(ls):,} | **{int(net):+,}** | {int(lchg):+,} | {int(schg):+,} | **{int(nchg):+,}** | {direction} |')
    
    lines.append('\n> 数据来源: CFFEX中金所 | AKShare | %s vs %s'%(prev_date,latest_date))
    
    return '\n'.join(lines)

if __name__=='__main__':
    print(format_futures_report())
