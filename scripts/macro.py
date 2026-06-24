#!/usr/bin/env python3
"""宏观因子分析 — 实时美债+美元+汇率"""
import yfinance as yf,subprocess as sp,json,os,time
from datetime import datetime

HERE=os.path.dirname(os.path.abspath(__file__))
CACHE={};CACHE_TIME=None

def load_macro(period='5d',use_cache=True):
    """实时宏观 — 5天数据取最新价，缓存5分钟"""
    global CACHE,CACHE_TIME
    now=time.time()
    if use_cache and CACHE and CACHE_TIME and now-CACHE_TIME<300:
        return CACHE
    
    tickers={
        'US10Y':'^TNX','US5Y':'^FVX','US3M':'^IRX','US30Y':'^TYX',
        'DXY':'DX-Y.NYB','USDCNY':'CNY=X'
    }
    macro={'updated':datetime.now().strftime('%H:%M:%S')}
    
    for name,sym in tickers.items():
        try:
            df=yf.download(sym,period=period,interval='1d',progress=False)
            if len(df)>0:
                def fv(x):return float(x.item() if hasattr(x,'item') else x)
                px=fv(df['Close'].values[-1])
                # Intraday: use the last day's high/low for real feel
                px5=fv(df['Close'].values[-5]) if len(df)>=5 else px
                chg_5d=round((px-px5)/px5*100,2)
                hi=fv(df['High'].values[-1]);lo=fv(df['Low'].values[-1])
                macro[name]={
                    'value':round(px,2),'chg_5d':chg_5d,
                    'trend':'↑' if px>px5 else '↓',
                    'day_high':round(hi,2),'day_low':round(lo,2),
                    'is_intraday':True
                }
        except:pass
    
    
    CACHE=macro;CACHE_TIME=now
    return macro

def macro_signal(macro):
    """解读宏观信号"""
    signals=[]
    if 'US10Y' in macro:
        v=macro['US10Y']['value']
        signals.append(('US10Y','%.2f%%'%v,'利率高位' if v>4 else '中性','对成长股/黄金不利' if v>4.5 else '可接受'))
    if 'US5Y' in macro:
        v=macro['US5Y']['value']
        if 'US10Y' in macro:
            spread=macro['US10Y']['value']-v
            inverted=spread<0
            signals.append(('收益率曲线','%.2f'%spread,'倒挂⚠️' if inverted else '正常','衰退信号' if inverted else '经济健康'))
    if 'DXY' in macro:
        v=macro['DXY']['value']
        signals.append(('DXY','%.1f'%v,'强势' if v>101 else('弱势' if v<98 else '中性'),'利空黄金/新兴市场' if v>101 else ''))
    if 'USDCNY' in macro:
        v=macro['USDCNY']['value']
        src=macro['USDCNY'].get('source','')
        signals.append(('USD/CNY','%.2f%s'%(v,'(实时)' if src=='akshare' else ''),'稳定','外资流出压力' if v>7.0 else ''))
    
    dxy=macro.get('DXY',{});us10y=macro.get('US10Y',{})
    if dxy.get('value',100)>101:
        bias='美元强势 — 新兴市场/商品承压'
    elif dxy.get('value',100)<98:bias='美元弱势 — 新兴市场/商品受益'
    else:bias='中性 — 各品种按自身结构操作'
    
    return {'signals':signals,'bias':bias,'updated':macro.get('updated','?')}

if __name__=='__main__':
    macro=load_macro(use_cache=True)
    s=macro_signal(macro)
    print('宏观因子 (更新: %s):'%s['updated'])
    for sig in s['signals']:
        print('  %-12s %-10s %s'%(sig[0],sig[1],sig[3] if sig[3] else sig[2]))
    print('\n基调:',s['bias'])
