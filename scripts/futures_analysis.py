#!/usr/bin/env python3
"""期货市场分析 — COMEX贵金属/铜 + yfinance K线 + chan.py"""
import yfinance as yf,re,os,sys
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,HERE)
sys.path.insert(0,os.path.join(HERE,'..','chanpy'))

from chan_engine import analyze as chan_analyze,get_bsp_label
from scorer import extract_features,score_from_features

FUTURES={
    'COMEX黄金':'GC=F','COMEX白银':'SI=F','COMEX铜':'HG=F',
    'SHFE铜(CFD)':'CUF','SHFE黄金(CFD)':'AUF','SHFE白银(CFD)':'AGF',
}

def analyze_future(sym,name=None):
    """分析单个期货品种"""
    df=yf.download(sym,period='1y',progress=False)
    if len(df)<30:return None
    def fv(x):return float(x.item() if hasattr(x,'item') else x)
    closes=[fv(x) for x in df['Close'].values];highs=[fv(x) for x in df['High'].values]
    lows=[fv(x) for x in df['Low'].values];opens=[fv(x) for x in df['Open'].values]
    vols=[fv(x) for x in df['Volume'].values]
    dates=[x.strftime('%Y-%m-%d') for x in df.index.tolist()]
    px=closes[-1];n=len(dates)
    
    cur,bsp_buy,bsp_types,_,zs,pos=chan_analyze(dates,opens,closes,highs,lows,sym)
    label=get_bsp_label(bsp_buy,bsp_types,pos)
    fd=extract_features(closes,highs,lows,opens,vols,bsp_buy,bsp_types,cur)
    score=score_from_features(fd)
    
    # Trend: 5-day vs 20-day MA
    ma5=sum(closes[-5:])/5 if n>=5 else px
    ma20=sum(closes[-20:])/20 if n>=20 else px
    trend='↑' if ma5>ma20 else '↓'
    
    return {
        'name':name or sym,'price':px,'score':score,'bsp':label,
        'pos':pos,'zs':zs,'trend':trend,'chg_pct':round((closes[-1]/closes[-5]-1)*100,1)
    }

def analyze_all_futures():
    """全品种分析"""
    results=[]
    for name,sym in FUTURES.items():
        try:
            r=analyze_future(sym,name)
            if r:results.append(r)
        except:pass
    return results

def futures_signal_for_stock(stock_type):
    """根据股票类型返回相关期货信号"""
    results=analyze_all_futures()
    signal={}
    
    for r in results:
        if stock_type=='gold' and '黄金' in r['name']:signal['gold']=r
        if stock_type=='gold' and '白银' in r['name']:signal['silver']=r
        if stock_type=='copper' and '铜' in r['name']:signal['copper']=r
    
    # Composite signal
    if not signal:return {'summary':'无相关期货数据','detail':[]}
    
    trend_signals=sum(1 for s in signal.values() if s['trend']=='↑')
    total=len(signal)
    summary='偏多' if trend_signals>total/2 else('偏空' if trend_signals<total/2 else '中性')
    
    return {'summary':summary,'detail':list(signal.values())}

if __name__=='__main__':
    results=analyze_all_futures()
    print('期货市场分析:')
    for r in results:
        print('%-15s $%-8s %2d分 %-12s %s %+5.1f%%'%(r['name'],str(round(r['price'],1)),r['score'],r['bsp'],r['trend'],r['chg_pct']))
    print()
    # Gold stock analysis
    for stock in ['gold','copper']:
        s=futures_signal_for_stock(stock)
        print('%s: %s'%(stock,s['summary']))
        for d in s['detail']:print('  %-15s $%s %s %s'%(d['name'],round(d['price'],1),d['bsp'],d['trend']))
