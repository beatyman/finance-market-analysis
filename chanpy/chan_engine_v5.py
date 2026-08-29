#!/usr/bin/env python3
"""chan_engine v5 wrapper — 生产级适配, 兼容chan_engine.analyze()接口"""
import sys, os
import pandas as pd
import numpy as np

HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.join(HERE,'..','chanpy'))
from chan_core_v5 import ChanCoreV5

# Map v5 BSP types to our internal format
def _bsp_classify(pts, px, pivots):
    """Extract BSP signals + latest BSP date — match v4's behavior"""
    buy_pts=[p for p in pts if p['point_type']=='buy']
    sell_pts=[p for p in pts if p['point_type']=='sell']
    
    # Use ALL recent BSPs (not just after July 2026)
    # v4 uses the latest BSP regardless of age
    recent_buy=[p for p in buy_pts if p['date'] > pd.Timestamp('2026-01-01')]
    recent_sell=[p for p in sell_pts if p['date'] > pd.Timestamp('2026-01-01')]
    
    bsp_buy=len(recent_buy)>0
    bsp_types=[]
    
    for p in recent_buy:
        bsp_types.append('Buy-{}'.format(p['full_name']))
    for p in recent_sell:
        bsp_types.append('Sell-{}'.format(p['full_name']))
    
    if not bsp_types:
        if pivots and px <= pivots[-1].get('high',0) and px >= pivots[-1].get('low',0):
            bsp_types=['中枢内']  # In pivot, neutral
        else:
            bsp_types=['中枢外']  # Outside pivot
    
    # 最新 BSP 日期（供 fresh gate 判定 signal_age）
    latest_bsp_date = None
    all_recent = recent_buy + recent_sell
    if all_recent:
        latest_bsp_date = max(p['date'] for p in all_recent)
    return bsp_buy, bsp_types, latest_bsp_date

def analyze(dates, opens, closes, highs, lows, code=''):
    """Compatible with chan_engine.analyze() — returns (cur, bsp_buy, bsp_types, px, zs_str, pos_str)"""
    if len(closes) < 50: return None, False, [], closes[-1], '', ''
    
    df=pd.DataFrame({
        'date':pd.to_datetime(dates),
        'open':[float(o) for o in opens],
        'high':[float(h) for h in highs],
        'low':[float(l) for l in lows],
        'close':[float(c) for c in closes],
        'volume':[1e6]*len(closes)
    })
    
    v5=ChanCoreV5(df, min_amplitude=0.005, pivot_min_amplitude=0.02, symbol=code)
    result=v5.analyze()
    
    px=closes[-1]
    pivots=result.get('pivots',[])
    pts=result.get('buy_sell_points',[])
    trend=result.get('trend_type',{})
    
    # Build ZS string
    zs_parts=[]
    for pv in pivots[-3:]:  # last 3 pivots
        zd=pv.get('low',pv.get('dd',0))
        zg=pv.get('high',pv.get('gg',0))
        if zd and zg and zd!=zg:
            zs_parts.append('{:.2f}~{:.2f}'.format(zd,zg))
    zs_str=','.join(zs_parts)
    
    # Position: relative to last pivot
    pos_str=''
    if pivots:
        last_pv=pivots[-1]
        zd=last_pv.get('low',0)
        zg=last_pv.get('high',0)
        if px<zd: pos_str='下'
        elif px>zg: pos_str='上'
        else: pos_str='内'
    
    # Trend summary
    trend_summary=trend.get('summary','?') if isinstance(trend,dict) else '?'
    
    # BSP
    bsp_buy,bsp_types,latest_bsp_date=_bsp_classify(pts, px, pivots)
    
    # Build compatible cur object with bi_list/zs_list/seg_list
    class FakeKL:
        def __init__(self,price,idx):
            self.low=price; self.high=price; self.idx=idx
    
    class FakeBI:
        def __init__(self,start,end,dir_str,start_idx,end_idx):
            self._start=start; self._end=end
            self.dir=dir_str
            self.is_down=(dir_str=='down')
            self.is_up=(dir_str=='up')
            self.begin_klc=FakeKL(start,start_idx)
            self.end_klc=FakeKL(end,end_idx)
            self.amp_val=abs(end-start)
        def high(self): return max(self._start,self._end)
        def low(self): return min(self._start,self._end)
        def get_end(self): return self._end
        def amp(self): return self.amp_val
    
    class FakeZS:
        def __init__(self,low_val,high_val):
            self.low=low_val; self.high=high_val
    
    class FakeSeg:
        def __init__(self,dir_str):
            self.dir=dir_str
            self.bi_list=[]
    
    class FakeCur:
        def __init__(self):
            self.kl_type=type('KL',(),{'value':0})()
            self.bi_list=[]
            self.zs_list=[]
            self.seg_list=[]
            self.bsp_event_date=None
            self.signal_age_bars=None
            self.is_fresh_bsp=True
        def __bool__(self): return True
        def high(self): return max(h for h in highs[-20:])
        def low(self): return min(l for l in lows[-20:])
    
    cur=FakeCur()
    
    # Fresh BSP gate (P0-08): signal_age_bars = 从最新BSP生成日到最后一根K线的交易日数
    cur.bsp_event_date = None
    cur.signal_age_bars = None
    cur.is_fresh_bsp = True  # 无BSP或无日期信息时默认 fresh（不误伤）
    if latest_bsp_date is not None:
        cur.bsp_event_date = str(latest_bsp_date.date())
        dates_ts = pd.to_datetime(dates)
        n_after = int((dates_ts >= latest_bsp_date).sum())
        cur.signal_age_bars = max(0, n_after - 1)  # bar 数（交易日），非日历天数
        cur.is_fresh_bsp = cur.signal_age_bars <= 1
    
    # Build stroke list from v5 strokes
    strokes=result.get('strokes',[])
    for s in strokes:
        sp=s.get('start_price',0); ep=s.get('end_price',0)
        d=s.get('direction','up')
        cur.bi_list.append(FakeBI(sp,ep,d,s.get('start_idx',0),s.get('end_idx',0)))
    
    # Build ZS list from v5 pivots
    for pv in pivots:
        zd=pv.get('low',pv.get('dd',0))
        zg=pv.get('high',pv.get('gg',0))
        if zd and zg:
            cur.zs_list.append(FakeZS(zd,zg))
    
    # Build segment list from trend
    if isinstance(trend,dict) and 'segments' in trend:
        for seg in trend['segments']:
            dir_str='up' if '上涨' in seg.get('type','') else 'down'
            cur.seg_list.append(FakeSeg(dir_str))
    
    return cur, bsp_buy, bsp_types, px, zs_str, trend_summary


def get_bsp_label(bsp_buy, bsp_types, position):
    """BSP标签 — 兼容chan_engine, 增强v5"""
    if bsp_buy:
        if position=='内': return 'Buy-中枢内买点'
        types_str=str(bsp_types)
        if '三买' in types_str: return 'Buy-三买'
        if '类二买' in types_str or '二买' in types_str: return 'Buy-二买'
        if '一买' in types_str: return 'Buy-一买'
        return 'Buy'
    # 卖出信号
    if bsp_types:
        types_str=str(bsp_types)
        if 'Sell' in types_str:
            if '三卖' in types_str: return 'Sell-三卖'
            if '类二卖' in types_str or '二卖' in types_str: return 'Sell-二卖'
            if '一卖' in types_str: return 'Sell-一卖'
            return 'Sell'
        # v5新增: 中枢内无BSP → 等信号
        if '中枢内' in types_str and position=='内':
            return '中枢内等信号'
        if '中枢外' in types_str:
            return '中枢外等信号'
    return 'Hold'
