#!/usr/bin/env python3
"""多源数据层 — Tencent/AKShare/yfinance/baostock 自动回退"""
import subprocess as sp,csv,os,time,yfinance as yf
import numpy as np

HERE=os.path.dirname(os.path.abspath(__file__))
REF=os.path.join(HERE,'..','references')

# ═══════════════ Stock Lists ═══════════════
def load_a_stocks():
    codes=[]
    with open(os.path.join(REF,'a_stock_codes.csv')) as f:
        for r in csv.DictReader(f):
            c=r['code'];n=r['name']
            if 'ST' in n or '退' in n:continue
            if c.startswith(('688','8','4','83','87','200','900','920')):continue
            codes.append((c,n))
    return codes

def load_hk_stocks():
    codes=[]
    with open(os.path.join(REF,'hk_stock_codes.csv')) as f:
        for r in csv.DictReader(f):codes.append((r['code'],r['name']))
    return codes

# ═══════════════ Source Priority ═══════════════
# K-line: Tencent → yfinance → AKShare → baostock
# Quotes: Tencent → AKShare
# All return: (dates,opens,closes,highs,lows,vols) or None

# ── Tencent K-line (fast, free) ──
def _tencent_kline(sym,days=200):
    """腾讯K线"""
    url='http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=%s,day,,,%d,qfq'%(sym,days)
    try:
        r=sp.run(['curl','-s','--max-time','5',url],stdout=sp.PIPE,stderr=sp.PIPE,timeout=7)
        if not r.stdout:return None
        import json;d=json.loads(r.stdout)
        key=sym if sym.startswith('hk') else sym
        data=d['data'][key]
        rows=data.get('qfqday') or data.get('day')  # A-share=qfqday, HK=day
        if not rows:return None
        dates=[str(r[0]) for r in rows];opens=[float(r[1]) for r in rows]
        closes=[float(r[2]) for r in rows];highs=[float(r[3]) for r in rows]
        lows=[float(r[4]) for r in rows];vols=[1.0]*len(rows)
        return dates,opens,closes,highs,lows,vols
    except:return None

# ── yfinance K-line ──
def _yf_kline(sym,period='1y'):
    """yfinance K线"""
    try:
        df=yf.download(sym,period=period,progress=False)
        if len(df)<30:return None
        def fv(x):return float(x.item() if hasattr(x,'item') else x)
        closes=np.array(df['Close']).ravel();highs=np.array(df['High']).ravel()
        lows=np.array(df['Low']).ravel();opens=np.array(df['Open']).ravel()
        vols=np.array(df['Volume']).ravel()
        dates=[x.strftime('%Y-%m-%d') for x in df.index.tolist()]
        return dates,[fv(x) for x in opens],[fv(x) for x in closes],[fv(x) for x in highs],[fv(x) for x in lows],[fv(x) for x in vols]
    except:return None

# ── AKShare K-line ──
def _ak_kline(code,market='a',days=200):
    """AKShare K线"""
    try:
        import akshare as ak
        if market=='a':
            df=ak.stock_zh_a_hist(symbol=code,period='daily',start_date='20200101',end_date='20260624',adjust='qfq')
            if df is None or len(df)<30:return None
            dates=df['日期'].tolist();opens=df['开盘'].tolist();closes=df['收盘'].tolist()
            highs=df['最高'].tolist();lows=df['最低'].tolist();vols=df['成交量'].tolist()
            return dates,opens,closes,highs,lows,vols
        else:
            df=ak.stock_hk_hist(symbol=code,period='daily',start_date='20200101',end_date='20260624',adjust='qfq')
            if df is None or len(df)<30:return None
            dates=df['日期'].tolist();opens=df['开盘'].tolist();closes=df['收盘'].tolist()
            highs=df['最高'].tolist();lows=df['最低'].tolist();vols=df['成交量'].tolist()
            return dates,opens,closes,highs,lows,vols
    except:return None

# ── Baostock K-line ──
def _bs_kline(code,market='a',days=200):
    """Baostock K线"""
    try:
        import baostock as bs
        bs.login()
        if market=='a':
            sym=('sh.'+code if code.startswith('6') else 'sz.'+code)
        else:
            sym='hk.'+code.replace('hk','')
        rs=bs.query_history_k_data_plus(sym,'date,open,high,low,close,volume',frequency='d',adjustflag='2')
        if rs.error_code!='0':return None
        rows=[]
        while rs.next():rows.append(rs.get_row_data())
        bs.logout()
        if len(rows)<30:return None
        dates=[str(r[0]) for r in rows];opens=[float(r[1]) for r in rows];closes=[float(r[4]) for r in rows]
        highs=[float(r[2]) for r in rows];lows=[float(r[3]) for r in rows];vols=[float(r[5]) for r in rows]
        return dates,opens,closes,highs,lows,vols
    except:return None

# ═══════════════ Unified API ═══════════════
def fetch_kline(code,market='a',period='1y',sources=None):
    """
    多源K线获取 — 按优先级自动回退
    sources: ['tencent','yfinance','akshare','baostock'] 或 None=全部试
    """
    if sources is None:
        sources=['tencent','yfinance','akshare','baostock']
    
    # Build symbol
    if market=='a':
        sym=(code+'.SS' if code.startswith('6') else code+'.SZ')
    else:
        sym='%04d.HK'%int(code.replace('hk',''))
    
    for src in sources:
        try:
            if src=='tencent':
                r=_tencent_kline(sym)
            elif src=='yfinance':
                r=_yf_kline(sym)
            elif src=='akshare':
                r=_ak_kline(code,market)
            elif src=='baostock':
                r=_bs_kline(code,market)
            else:continue
            
            if r and len(r[1])>=30:
                # Limit to last 250 bars
                r=(r[0][-250:],r[1][-250:],r[2][-250:],r[3][-250:],r[4][-250:],r[5][-250:])
                return r
        except:pass
    
    return None

def fetch_kline_a(code,period='1y'):
    """A股K线快捷入口"""
    return fetch_kline(code,'a',period)

def fetch_kline_hk(code,period='1y'):
    """港股K线快捷入口"""
    return fetch_kline(code,'hk',period)

# ═══════════════ Quotes ═══════════════
def fetch_a_quotes(codes,batch=80):
    """A股批量行情(Tencent)"""
    quotes={}
    for i in range(0,len(codes),batch):
        if i%2000==0:print('  行情 %d/%d'%(i,len(codes)),flush=True)
        qt=','.join([('sh'+c if c.startswith('6') else 'sz'+c) for c,_ in codes[i:i+batch]])
        try:
            r=sp.run(['curl','-s','--max-time','4','http://qt.gtimg.cn/q='+qt],stdout=sp.PIPE,stderr=sp.PIPE,timeout=6)
            for line in r.stdout.decode('gbk','ignore').strip().split('\n'):
                p=line.split('~')
                if len(p)<40:continue
                try:px=float(p[3]);ch=float(p[32])
                except:continue
                if px>0:quotes[line.split('=')[0].replace('v_','').replace('_','')[2:]]={'price':px,'change_pct':ch}
        except:pass
    return quotes

def fetch_hk_quotes(codes,batch=80):
    """港股批量行情(Tencent)"""
    quotes={}
    for i in range(0,len(codes),batch):
        if i%500==0:print('  行情 %d/%d'%(i,len(codes)),flush=True)
        qt=','.join([c for c,_ in codes[i:i+batch]])
        try:
            r=sp.run(['curl','-s','--max-time','4','http://qt.gtimg.cn/q='+qt],stdout=sp.PIPE,stderr=sp.PIPE,timeout=6)
            for line in r.stdout.decode('gbk','ignore').strip().split('\n'):
                p=line.split('~')
                if len(p)<10:continue
                try:px=float(p[3]);ch=float(p[32]) if len(p)>32 else 0
                except:continue
                if px>0:quotes[line.split('=')[0].replace('v_','').replace('_','')]={'price':px,'change_pct':ch}
        except:pass
    return quotes
