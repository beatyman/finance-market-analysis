#!/usr/bin/env python3
"""宏观因子分析 — 全维度数据支撑"""
import yfinance as yf,subprocess as sp,json,time,os
from datetime import datetime

HERE=os.path.dirname(os.path.abspath(__file__))
CACHE={};CACHE_TIME=None

TICKERS={
    # US Treasuries
    'US3M':'^IRX','US2Y':'^UST2Y','US5Y':'^FVX','US10Y':'^TNX','US30Y':'^TYX',
    # FX & Index
    'DXY':'DX-Y.NYB','USDCNY':'CNY=X','USDJPY':'JPY=X','EURUSD':'EURUSD=X',
    # Risk
    'VIX':'^VIX','SPX':'^GSPC','N225':'^N225','HSI':'^HSI',
    # Commodity proxy
    'OIL':'CL=F','GOLD':'GC=F','COPPER':'HG=F',
}

def load_macro(period='1mo',use_cache=True):
    """全维度宏观 — 5天K线取最新价"""
    global CACHE,CACHE_TIME
    now=time.time()
    if use_cache and CACHE and CACHE_TIME and now-CACHE_TIME<300:
        return CACHE
    
    macro={'updated':datetime.now().strftime('%H:%M:%S')}
    
    for name,sym in TICKERS.items():
        try:
            df=yf.download(sym,period=period,interval='1d',progress=False)
            if len(df)<2:continue
            def fv(x):return float(x.item() if hasattr(x,'item') else x)
            px=fv(df['Close'].values[-1])
            px5=fv(df['Close'].values[-5]) if len(df)>=5 else px
            px20=fv(df['Close'].values[-20]) if len(df)>=20 else px
            hi=fv(df['High'].values[-1]);lo=fv(df['Low'].values[-1])
            macro[name]={
                'value':round(px,2),'chg_5d':round((px-px5)/px5*100,2),
                'chg_20d':round((px-px20)/px20*100,2),
                'trend':'↑' if px>px20 else '↓',
                'day_high':round(hi,2),'day_low':round(lo,2)
            }
        except:pass
    
    CACHE=macro;CACHE_TIME=now
    return macro

def macro_report():
    """详细宏观报告"""
    m=load_macro()
    
    lines=[]
    lines.append('## 🌍 宏观全维度')
    
    # ── Rate & Curve ──
    us10=m.get('US10Y',{});us2=m.get('US2Y',{});us30=m.get('US30Y',{});us3m=m.get('US3M',{})
    us5=m.get('US5Y',{})
    
    lines.append('\n### 📊 美债收益率')
    if us10 and us3m:
        spread10_3m=us10['value']-us3m['value']
        inverted10_3m='⚠️ 倒挂' if spread10_3m<0 else '正常'
        lines.append('| 期限 | 收益率 | 5日变动 | 20日变动 | 趋势 |')
        lines.append('|------|--------|---------|----------|------|')
        for label,data in [('3个月',us3m),('2年',us2),('5年',us5),('10年',us10),('30年',us30)]:
            if data:
                lines.append('| %s | %.2f%% | %+.2f%% | %+.2f%% | %s |'%(
                    label,data['value'],data.get('chg_5d',0),data.get('chg_20d',0),data['trend']))
        lines.append('')
        lines.append('**10Y-3M利差: %.2f (%s)**'%(spread10_3m,inverted10_3m))
        lines.append('- 倒挂=衰退预警 | 正常=经济健康')
    
    # ── USD / FX ──
    dxy=m.get('DXY',{});cny=m.get('USDCNY',{});jpy=m.get('USDJPY',{});eur=m.get('EURUSD',{})
    lines.append('\n### 💵 汇率市场')
    if dxy:
        dxy_str='强势' if dxy['value']>101 else('弱势' if dxy['value']<98 else '中性')
        lines.append('| 指标 | 数值 | 5日变动 | 20日变动 | 状态 |')
        lines.append('|------|------|---------|----------|------|')
        lines.append('| **DXY 美元指数** | **%.1f** | %+.2f%% | %+.2f%% | %s |'%(
            dxy['value'],dxy.get('chg_5d',0),dxy.get('chg_20d',0),dxy_str))
        for label,data in [('USD/CNY',cny),('USD/JPY',jpy),('EUR/USD',eur)]:
            if data:
                lines.append('| %s | %.2f | %+.2f%% | %+.2f%% | %s |'%(
                    label,data['value'],data.get('chg_5d',0),data.get('chg_20d',0),data['trend']))
        
        impact=[]
        if dxy['value']>101:impact.append('🔴 利空新兴市场/商品/黄金')
        elif dxy['value']<98:impact.append('🟢 利好新兴市场/商品')
        if cny and cny.get('chg_5d',0)>0.3:impact.append('⚠️ 人民币贬值—港股承压')
        if impact:lines.append('\n**影响:** '+' | '.join(impact))
    
    # ── Risk ──
    vix=m.get('VIX',{});spx=m.get('SPX',{});n225=m.get('N225',{});hsi=m.get('HSI',{})
    lines.append('\n### ⚡ 风险偏好')
    if vix and spx:
        lines.append('| 指标 | 数值 | 5日变动 | 20日变动 | 状态 |')
        lines.append('|------|------|---------|----------|------|')
        vix_level='极度恐慌' if vix['value']>30 else('恐慌' if vix['value']>25 else('偏恐慌' if vix['value']>20 else('正常' if vix['value']>15 else'极度乐观')))
        lines.append('| **VIX 恐慌指数** | **%.1f** | %+.2f%% | %+.2f%% | %s |'%(
            vix['value'],vix.get('chg_5d',0),vix.get('chg_20d',0),vix_level))
        for label,data in [('标普500',spx),('日经225',n225),('恒生指数',hsi)]:
            if data:
                lines.append('| %s | %.0f | %+.2f%% | %+.2f%% | %s |'%(
                    label,data['value'],data.get('chg_5d',0),data.get('chg_20d',0),data['trend']))
    
    # ── Commodity ──
    oil=m.get('OIL',{});gold=m.get('GOLD',{});copper=m.get('COPPER',{})
    lines.append('\n### 🛢️ 大宗商品')
    if oil and gold:
        lines.append('| 品种 | 价格 | 5日变动 | 20日变动 | 趋势 |')
        lines.append('|------|------|---------|----------|------|')
        for label,data,unit in [('WTI原油',oil,'$'),('COMEX黄金',gold,'$'),('COMEX铜',copper,'$')]:
            if data:
                lines.append('| %s | %s%.1f | %+.2f%% | %+.2f%% | %s |'%(
                    label,unit,data['value'],data.get('chg_5d',0),data.get('chg_20d',0),data['trend']))
    
    # ── Summary ──
    lines.append('\n### 🎯 综合判断')
    summaries=[]
    if dxy.get('value',100)>101:summaries.append('美元强势 → 商品/新兴市场承压')
    elif dxy.get('value',100)<98:summaries.append('美元弱势 → 商品/新兴市场受益')
    if vix.get('value',100)>25:summaries.append('🔴 高恐慌 → 仓位降至50%以下')
    elif vix.get('value',100)<18:summaries.append('🟢 低波动 → 正常仓位')
    if us10.get('value',0)>4.5:summaries.append('高利率 → 成长股估值承压')
    if not summaries:summaries.append('中性 — 各品种按自身结构操作')
    for s in summaries:lines.append('- '+s)
    
    return '\n'.join(lines)

if __name__=='__main__':
    print(macro_report())
