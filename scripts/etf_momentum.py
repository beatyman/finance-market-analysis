#!/usr/bin/env python3
"""
Quanti5 ETF动量轮动 — 20万账户最佳组合
算法: 混合动量(1月×0.15 + 3月×0.35 + 6月×0.50) + 趋势门控(>MA120) + 仓位调节(80%)
"""
import yfinance as yf,numpy as np
import warnings;warnings.filterwarnings('ignore')

ETF_UNIVERSE={
    '510300.SS':'沪深300','510500.SS':'中证500','159915.SZ':'创业板','588000.SS':'科创50',
    '510050.SS':'上证50','512100.SS':'中证1000','512760.SS':'半导体','159995.SZ':'芯片',
    '512480.SS':'半导体设备','588200.SS':'科创芯片','159819.SZ':'人工智能','515790.SS':'光伏',
    '515030.SS':'新能源车','512660.SS':'军工','512010.SS':'医药','512170.SS':'医疗',
    '512000.SS':'券商','512800.SS':'银行','510880.SS':'红利','512690.SS':'酒',
    '159928.SZ':'消费','512400.SS':'有色金属','515880.SS':'通信','512720.SS':'计算机',
    '562500.SS':'机器人','516510.SS':'云计算','513180.SS':'恒生科技',
}

def calculate_momentum(bars):
    """混合动量: 20日×0.15 + 60日×0.35 + 120日×0.50"""
    n=len(bars);c=bars[-1]
    r20=(c/bars[-21]-1) if n>=21 else 0
    r60=(c/bars[-61]-1) if n>=61 else 0
    r120=(c/bars[-121]-1) if n>=121 else 0
    return r20*0.15+r60*0.35+r120*0.50, r20, r60, r120

def in_uptrend(bars):
    """趋势门控: 价格>MA120 且 6月回报>0"""
    n=len(bars);c=bars[-1]
    if n<130:return False
    ma120=sum(bars[-120:])/120
    r120=c/bars[-121]-1
    return c>ma120 and r120>0

def get_etf_portfolio(capital=200000, deploy_pct=80, top_k=5):
    """获取ETF动量轮动组合"""
    scored=[]
    for sym,name in ETF_UNIVERSE.items():
        try:
            df=yf.download(sym,period='1y',progress=False)
            if len(df)<130:continue
            C=[float(x.item() if hasattr(x,'item') else x) for x in np.array(df['Close']).ravel()]
            score,r20,r60,r120=calculate_momentum(C)
            trend=in_uptrend(C)
            px=C[-1];ma120=sum(C[-120:])/120
            if trend:
                scored.append((name,sym,px,score,r20,r60,r120,ma120))
        except:pass
    
    scored.sort(key=lambda x:-x[3])
    top=scored[:top_k]
    
    budget=capital*(deploy_pct/100)/top_k
    picks=[]
    for name,sym,px,score,r20,r60,r120,ma in top:
        lots=int(budget/(px*100))
        cost=lots*100*px
        picks.append({
            'name':name,'code':sym,'price':px,'score':score,
            'r1m':r20*100,'r3m':r60*100,'r6m':r120*100,
            'lots':lots,'cost':cost
        })
    return picks,budget

def format_etf_report(capital=200000):
    """格式化ETF动量组合报告"""
    picks,budget=get_etf_portfolio(capital)
    total=sum(p['cost'] for p in picks)
    cash=capital-total
    
    lines=['## 📊 Quanti5 ETF动量组合','']
    lines.append('| # | ETF | 代码 | 价格 | 动量分 | 1月 | 3月 | 6月 | 手数 | 金额 |')
    lines.append('|---|------|------|------|--------|------|------|------|------|------|')
    for i,p in enumerate(picks):
        lines.append('| %d | %s | %s | ¥%.2f | %.3f | %+.1f%% | %+.1f%% | %+.1f%% | %d | ¥%d |'%(
            i+1,p['name'],p['code'],p['price'],p['score'],p['r1m'],p['r3m'],p['r6m'],p['lots'],int(p['cost'])))
    
    lines.append('')
    lines.append('| 项目 | 金额 |')
    lines.append('|------|------|')
    lines.append('| 总投资 | ¥% d |'%total)
    lines.append('| 现金 | ¥% d (%.0f%%) |'%(cash,cash/capital*100))
    lines.append('| 配置率 | %.0f%% |'%(total/capital*100))
    
    return '\n'.join(lines)

if __name__=='__main__':
    print(format_etf_report(200000))
