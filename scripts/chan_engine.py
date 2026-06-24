#!/usr/bin/env python3
"""缠论引擎 — chan.py BSP/ZS 提取"""
import re,os,sys
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.join(HERE,"..","chanpy"))
from Common.CEnum import KL_TYPE,DATA_FIELD
from Common.CTime import CTime
from KLine.KLine_Unit import CKLine_Unit
from Chan import CChan;from ChanConfig import CChanConfig

CONFIG=CChanConfig({'trigger_step':True,'divergence_rate':0.7,'min_zs_cnt':0,'bs_type':'1,2,3a,1p,2s,3b'})

def analyze(dates, opens, closes, highs, lows, code='unknown'):
    """运行 chan.py 分析，返回 (chan_level, bsp_buy, bsp_types, price, zs_range, position)"""
    n=len(dates)
    if n<30:return None,False,[],closes[-1],'','-'
    
    klines=[]
    for i in range(n):
        p=dates[i].split('-')
        # Handle both "2026-06-24" and "2026-06-24 09:30" formats
        if ' ' in p[2]:
            day_part,time_part=p[2].split(' ')
            hh,mm=time_part.split(':')[:2]
        else:
            day_part=p[2];hh=0;mm=0
        t=CTime(int(p[0]),int(p[1]),int(day_part),int(hh),int(mm),auto=False)
        klines.append(CKLine_Unit({DATA_FIELD.FIELD_TIME:t,DATA_FIELD.FIELD_OPEN:opens[i],
            DATA_FIELD.FIELD_HIGH:highs[i],DATA_FIELD.FIELD_LOW:lows[i],DATA_FIELD.FIELD_CLOSE:closes[i]},autofix=True))
    
    chan=CChan(code=code,begin_time=None,end_time=None,data_src=1,lv_list=[KL_TYPE.K_DAY],config=CONFIG)
    for klu in klines:chan.trigger_load({KL_TYPE.K_DAY:[klu]})
    cur=chan[0]
    
    bsp_buy=False;bsp_types=[]
    for b in chan.get_latest_bsp():
        t=re.findall(r"'([^']+)'",str(b.type))
        bsp_buy=b.is_buy;bsp_types=[x.strip("'") for x in t]
    
    px=closes[-1]
    zs_str='';pos='-'
    if cur.zs_list:
        zl=sorted([(float(z.low),float(z.high)) for z in cur.zs_list],key=lambda x:x[0])
        zs_str=','.join(['%d~%d'%z for z in zl[-2:]])
        lo=zl[-1][0];hi=zl[-1][1]
        pos='内' if lo<=px<=hi else('上' if px>hi else '下')
    
    return cur,bsp_buy,bsp_types,px,zs_str,pos

def get_bsp_label(bsp_buy,bsp_types,position):
    """BSP标签"""
    if bsp_buy:
        if position=='内':return 'Buy-中枢内买点'
        if '3' in str(bsp_types):return 'Buy-三买'
        if '2' in str(bsp_types):return 'Buy-二买'
        if '1' in str(bsp_types):return 'Buy-一买'
        return 'Buy'
    if bsp_types:
        if '3' in str(bsp_types):return 'Sell-三卖'
        if '2' in str(bsp_types):return 'Sell-二卖'
        if '1' in str(bsp_types):return 'Sell-一卖'
        return 'Sell'
    return 'Hold'
