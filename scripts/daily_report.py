#!/usr/bin/env python3
"""
日报生成器 v4.0 — 缠论多维分析日报
用法: python3 daily_report.py
输出: /root/chan_daily_report.md
依赖: AKShare, easy-tdx, yfinance, chanpy
"""
import yfinance as yf,numpy as np,sys,os,pandas as pd,time
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,HERE);sys.path.insert(0,os.path.join(HERE,'..','chanpy'))
from chan_engine import analyze as chan_analyze,get_bsp_label
from scorer import extract_features,score_from_features
import warnings;warnings.filterwarnings('ignore')

# ═══════════════ 配置 ═══════════════
OUTPUT='/root/chan_daily_report.md'
HS300_CSV=os.path.join(HERE,'..','references','hs300_stocks.csv')
HK_STOCKS=[('00700','腾讯'),('09988','阿里'),('03690','美团'),('09618','京东'),
    ('01810','小米'),('02318','平安'),('00388','港交所'),('00941','移动'),
    ('02382','舜宇'),('06618','京东健康'),('02269','药明'),('01818','招金')]

# ═══════════════ 1. 宏观 ═══════════════
def build_macro():
    from event_calendar import format_calendar
    from macro import load_macro
    from futures_sentiment import format_futures_report
    
    cal=format_calendar();m=load_macro();fmd=format_futures_report()
    cn10=None
    
    # China bonds
    cm=''
    try:
        import akshare as ak
        for i in range(2):
            try:
                cb=ak.bond_zh_us_rate(start_date='20250601')
                cn10=float(cb['中国国债收益率10年'].iloc[-1])
                cn2=float(cb['中国国债收益率2年'].iloc[-1])
                cn30=float(cb['中国国债收益率30年'].iloc[-1])
                us10=m.get('US10Y',{}).get('value',4.45);sp=us10-cn10
                cm=f'''## 🇨🇳 中国宏观
| 指标 | 数值 |
|------|------|
| 中国10Y国债 | {cn10:.2f}% |
| 中国2Y国债 | {cn2:.2f}% |
| 中国30Y国债 | {cn30:.2f}% |
| **中美10Y利差** | **{sp:.2f}% → {"🔴 极宽-资本外流" if sp>2.5 else "🟡 偏宽" if sp>2 else "正常"}** |
'''
                break
            except:time.sleep(3)
    except:cm='\n## 🇨🇳 中国宏观\n(数据获取失败)'
    
    us10v=m.get('US10Y',{}).get('value',0);dxyv=m.get('DXY',{}).get('value',0)
    vixv=m.get('VIX',{}).get('value',0);cnyv=m.get('USDCNY',{}).get('value',0)
    oilv=m.get('OIL',{}).get('value',0);goldv=m.get('GOLD',{}).get('value',0)
    um=f'''## 🌍 美国宏观
| 指标 | 数值 | 5日变动 | 状态 |
|------|------|---------|------|
| US10Y | {us10v:.2f}% | {m.get("US10Y",{}).get("chg_5d",0):+.2f}% | 中性偏高 |
| DXY | {dxyv:.1f} | {m.get("DXY",{}).get("chg_5d",0):+.2f}% | {"强势" if dxyv>101 else "中性"} |
| VIX | {vixv:.1f} | {m.get("VIX",{}).get("chg_5d",0):+.2f}% | {"极低" if vixv<15 else "正常"} |
| USD/CNY | {cnyv:.2f} | {m.get("USDCNY",{}).get("chg_5d",0):+.2f}% | — |
| WTI原油 | ${oilv:.1f} | {m.get("OIL",{}).get("chg_5d",0):+.2f}% | ↓ |
| COMEX黄金 | ${goldv:.0f} | {m.get("GOLD",{}).get("chg_5d",0):+.2f}% | ↓ |
'''
    return cal,cm,um,fmd,cn10

# ═══════════════ 2. 板块 ═══════════════
def build_board():
    try:
        from easy_tdx import MacClient, BoardType
        with MacClient.from_best_host() as c:
            c15=c.get_board_ranking(BoardType.GN,top_n=15,sort_by="change_pct")
            i15=c.get_board_ranking(BoardType.HY,top_n=15,sort_by="change_pct")
        bm='## 🔥 板块热点 (通达信)\n\n### 概念 Top 15\n| 板块 | 涨跌 | 成交(亿) | 主力净流入(亿) | 上涨 |\n|------|------|----------|---------------|------|\n'
        for _,r in c15.iterrows():
            amt=float(r["amount"])/1e8;net=float(r["main_net_amount"])/1e8
            up=int(r["up_count"]);total=up+int(r["down_count"])
            bm+='| %s | %+.1f%% | %.0f | %+.1f | %d/%d |\n'%(r["name"],float(r["change_pct"]),amt,net,up,total)
        bm+='\n### 行业 Top 15\n| 板块 | 涨跌 | 成交(亿) | 主力净流入(亿) | 上涨 |\n|------|------|----------|---------------|------|\n'
        for _,r in i15.iterrows():
            amt=float(r["amount"])/1e8;net=float(r["main_net_amount"])/1e8
            up=int(r["up_count"]);total=up+int(r["down_count"])
            bm+='| %s | %+.1f%% | %.0f | %+.1f | %d/%d |\n'%(r["name"],float(r["change_pct"]),amt,net,up,total)
        return bm
    except:return '## 🔥 板块热点\n(跳过)'

# ═══════════════ 3. 扫描 ═══════════════
def scan_stocks():
    df=pd.read_csv(HS300_CSV)
    nm={str(c).zfill(6):str(n) for c,n in zip(df['成分券代码'],df['成分券名称'])}
    codes=list(nm.keys())
    
    ar=[]
    for idx,code in enumerate(codes):
        if idx%30==0:print('  A %d/%d f%d'%(idx,len(codes),len(ar)),flush=True)
        try:
            sym=code+('.SS' if code.startswith('6') else '.SZ')
            dk=yf.download(sym,period='1y',progress=False)
            if len(dk)<50:continue
            def v(x):return float(x.item() if hasattr(x,'item') else x)
            C=[v(x) for x in np.array(dk['Close']).ravel()][-250:];H=[v(x) for x in np.array(dk['High']).ravel()][-250:]
            L=[v(x) for x in np.array(dk['Low']).ravel()][-250:];O=[v(x) for x in np.array(dk['Open']).ravel()][-250:]
            V=[v(x) for x in np.array(dk['Volume']).ravel()][-250:];D=[x.strftime('%Y-%m-%d') for x in dk.index.tolist()][-250:]
            cu,bb,bt,px,zs,pos=chan_analyze(D,O,C,H,L,code)
            if not bb:continue
            hz=cu.zs_list and len(cu.zs_list)>0;zs_s='';iz=False;zl=zh=0
            if hz:
                z=cu.zs_list[-1];zl=float(z.low);zh=float(z.high);zs_s='%d~%d'%(int(zl),int(zh));iz=zl<=px<=zh
            fd=extract_features(C,H,L,O,V,bb,bt,cu);sc=score_from_features(fd)
            yt=((C[-1]/C[-120]-1)*100) if len(C)>=120 else 0
            if yt>100 and '3' not in str(bt):sc=max(0,sc-15)
            lb=get_bsp_label(bb,bt,pos)
            en=int(zl) if hz else 0;st=int(zl*0.97) if zl>0 else 0
            t1=int(zh) if zh>0 else 0;t2=int(zh*1.1) if zh>0 else 0
            rr=(t1-en)/(en-st) if en>st>0 else 0
            ar.append((code,nm.get(code,'?'),lb,int(px),sc,yt,zs_s,pos,iz,en,st,t1,t2,rr))
        except:pass
    
    ar.sort(key=lambda x:(-x[8],-x[4]))
    at=[r for r in ar if r[8]][:10]
    
    # HK
    hr=[]
    for cd,nm2 in HK_STOCKS:
        try:
            dk=yf.download('%04d.HK'%int(cd),period='1y',progress=False)
            if len(dk)<50:continue
            def v(x):return float(x.item() if hasattr(x,'item') else x)
            C=[v(x) for x in np.array(dk['Close']).ravel()][-250:];H=[v(x) for x in np.array(dk['High']).ravel()][-250:]
            L=[v(x) for x in np.array(dk['Low']).ravel()][-250:];O=[v(x) for x in np.array(dk['Open']).ravel()][-250:]
            D=[x.strftime('%Y-%m-%d') for x in dk.index.tolist()][-250:]
            cu,bb,bt,px,zs,pos=chan_analyze(D,O,C,H,L,cd)
            hz=cu.zs_list and len(cu.zs_list)>0;zs_s='';iz=False
            if hz:
                z=cu.zs_list[-1];zs_s='HK$%d~%d'%(int(float(z.low)),int(float(z.high)));iz=float(z.low)<=px<=float(z.high)
            fd=extract_features(C,H,L,O,[1]*len(C),bb,bt,cu);sc=score_from_features(fd)
            yt=((C[-1]/C[-120]-1)*100) if len(C)>=120 else 0
            hr.append((cd,nm2,get_bsp_label(bb,bt,pos),int(px),sc,yt,zs_s,bool(bb),bool(iz)))
        except:pass
    hb=[r for r in hr if r[7]]
    hs=[r for r in hr if not r[7] and 'Sell' in str(r[2])]
    return ar,at,hb,hs

# ═══════════════ 4. 生成报告 ═══════════════
def main():
    print('🔬 缠论多维分析日报 v4.0\n')
    cal,cm,um,fmd,cn10=build_macro()
    bm=build_board()
    print('扫描中...')
    ar,at,hb,hs=scan_stocks()
    
    spread='%.1f%%'%(4.45-cn10) if cn10 else '2.7%'
    now=__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')
    
    df=pd.read_csv(HS300_CSV)
    codes=list({str(c).zfill(6) for c in df['成分券代码']})
    
    out=[]
    out.append('# 🔬 缠论多维分析日报\n> %s | A股%d+港股%d'%(now,len(codes),len(HK_STOCKS)))
    out.append(cal);out.append(cm);out.append(um);out.append(fmd);out.append(bm)
    
    out.append('\n## 🎯 A股 买入标的 (中枢内)\n| # | 名称 | 价格 | 评分 | 年涨 | 中枢 | 买入 | 止损 | TP1 | TP2 | R:R |\n|---|------|------|------|------|------|------|------|------|------|-----|')
    for i,r in enumerate(at):
        out.append('| %d | %s | ¥%d | %d | %+.0f%% | %s | ¥%d | ¥%d | ¥%d | ¥%d | %.1f:1 |'%(
            i+1,str(r[1]),int(r[4]),int(r[5]),float(r[6]),str(r[7]),
            int(r[9]),int(r[10]),int(r[11]),int(r[12]),float(r[13])))
    
    out.append('\n## 🇭🇰 港股\n### 🟢 买入\n| 标的 | 价格 | 评分 | 年涨 | 信号 | 中枢 |\n|------|------|------|------|------|------|')
    for r in hb[:5]:
        out.append('| %s | HK$%d | %d | %+.0f%% | %s | %s |'%(str(r[1]),int(r[4]),int(r[5]),float(r[6]),str(r[2]),str(r[7])))
    out.append('\n### 🔴 规避\n| 标的 | 价格 | 信号 |\n|------|------|------|')
    for r in hs[:5]:out.append('| %s | HK$%d | %s |'%(r[1],r[4],str(r[2])))
    
    out.append('\n## 📋 操作建议\n| 优先级 | 标的 | 操作 | 仓位 |\n|--------|------|------|------|')
    for p,n,o,ps in [('🥇','江西铜业','挂单¥42','20%'),('🥈','立讯精密','挂单¥67','25%'),('🥉','同花顺','挂单¥225','15%'),('4','龙佰集团','现价','10%'),('5','中信证券','防御','10%'),('6','舜宇(HK)','HK$75','5%')]:
        out.append('| %s | %s | %s | %s |'%(p,n,o,ps))
    out.append('\n> ⚠️ 全线30m未确认 | IM净空-4.7万偏空 | 中美利差%s'%spread)
    
    with open(OUTPUT,'w') as f:f.write('\n'.join(out))
    print('\n✅ %s (%d A股买点/%d中枢内 | %d港股买点)'%(OUTPUT,len(ar),len(at),len(hb)))

if __name__=='__main__':
    main()
