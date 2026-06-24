#!/usr/bin/env python3
"""
阿娇版缠论筛选模板 — 用于板块/个股二次确认
用法: from references.ajiao_screening import ajiao_filter
"""
import sys,os
# Assumes caller has sys.path set to scripts/ and chanpy/

def ajiao_filter(stocks, chan_analyze, yf_download, np):
    """
    阿娇标准筛选买点
    stocks: [(code, name), ...]
    chan_analyze: from chan_engine import analyze
    yf_download: yf.download
    np: numpy module
    返回: (buys, sells, holds)
    """
    buys=[];sells=[];holds=[]
    for code,name in stocks:
        try:
            sym=code+('.SS' if code.startswith('6') else '.SZ')
            df=yf_download(sym,period='1y',progress=False)
            if len(df)<50:continue
            def fv(x):return float(x.item() if hasattr(x,'item') else x)
            C=[fv(x) for x in np.array(df['Close']).ravel()][-250:]
            H=[fv(x) for x in np.array(df['High']).ravel()][-250:]
            L=[fv(x) for x in np.array(df['Low']).ravel()][-250:]
            O=[fv(x) for x in np.array(df['Open']).ravel()][-250:]
            D=[x.strftime('%Y-%m-%d') for x in df.index.tolist()][-250:]
            cur,bsp_buy,bsp_types,px,_,pos=chan_analyze(D,O,C,H,L,code)
            
            has_zs=cur.zs_list and len(cur.zs_list)>0
            if not has_zs:
                holds.append((name,code,int(px),'无中枢'))
                continue
            
            zl=float(cur.zs_list[-1].low);zh=float(cur.zs_list[-1].high)
            in_zs=zl<=px<=zh;above_zs=px>zh
            
            if bsp_buy and (in_zs or above_zs):
                label='盘整买' if in_zs else '三买'
                score=75 if in_zs else 70
                if '3a' in str(bsp_types) or '3b' in str(bsp_types):score+=5
                buys.append((name,code,int(px),label,int(zl),int(zh),score))
            elif not bsp_buy and bsp_types:
                sells.append((name,code,int(px),'卖出'))
            else:
                pos_str='中枢内' if in_zs else('中枢上' if above_zs else '中枢下')
                holds.append((name,code,int(px),f'{pos_str} 无信号'))
        except:pass
    
    buys.sort(key=lambda x:-x[6])
    return buys,sells,holds
