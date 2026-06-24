#!/usr/bin/env python3
"""量价分析 + 板块热度"""
import numpy as np,subprocess as sp,json,os
HERE=os.path.dirname(os.path.abspath(__file__))

# ── Sector mapping (pre-built) ──
STOCK_SECTOR={
    '002475':'消费电子/连接器','603019':'AI服务器','002594':'新能源车','601899':'黄金/铜','002371':'半导体设备',
    '601138':'AI服务器/代工','600489':'黄金','002837':'AI散热/温控','300476':'PCB/AI','000977':'AI服务器',
    '688041':'CPU/GPU','603986':'存储MCU','603893':'AI芯片','688008':'DDR5/内存','601100':'工程机械',
    '600089':'电力设备/特高压','002281':'光通信/光模块','002463':'PCB','002428':'锗/军工材料',
    '300475':'存储分销','000988':'光通信/激光','600030':'券商','601728':'电信','601985':'核电',
    '000338':'重卡/柴油机','603606':'海缆/风电','000858':'白酒','601318':'保险','600036':'银行',
    '603501':'CIS/图像传感器','300124':'工控/机器人','300750':'新能源电池',
    '00700':'互联网','09988':'电商/云','03690':'本地生活/外卖',
}

SECTOR_HEAT_SOURCE={
    'AI算力':['光通信/光模块','AI服务器','AI服务器/代工','DDR5/内存','AI散热/温控','存储MCU','PCB/AI'],
    '半导体':['半导体设备','CPU/GPU','AI芯片','CIS/图像传感器','晶圆代工'],
    '新能源':['新能源车','新能源电池','海缆/风电'],
    '消费电子':['消费电子/连接器','PCB'],
    '黄金/商品':['黄金','黄金/铜','锗/军工材料'],
    '金融':['券商','银行','保险'],
    '互联网':['互联网','电商/云','本地生活/外卖'],
    '工业':['工程机械','重卡/柴油机','电力设备/特高压','核电','工控/机器人'],
}

def get_stock_sector(code):
    """获取股票所属板块"""
    pure=code.replace('hk','')
    return STOCK_SECTOR.get(pure,STOCK_SECTOR.get(code,'其他'))

def get_sector_heat():
    """板块热度评估"""
    heat={}
    for sector,sub_sectors in SECTOR_HEAT_SOURCE.items():
        heat[sector]={'subs':len(sub_sectors),'score':50}  # Default neutral
    return heat

# ── Volume analysis ──
def volume_analysis(closes,vols):
    """量价分析：背离/放量/缩量"""
    n=len(closes)
    if n<20:return {'signal':'数据不足'}
    
    # 5-day metrics
    vol5=vols[-5:];price5=closes[-5:]
    avg_vol=np.mean(vol5)
    vol_ratio=vols[-1]/avg_vol if avg_vol>0 else 1
    
    # 20-day baseline
    baseline_vol=np.mean(vols[-20:])
    vol_vs_baseline=vols[-1]/baseline_vol if baseline_vol>0 else 1
    
    # Price momentum
    chg_5d=(closes[-1]/closes[-5]-1)*100
    chg_20d=(closes[-1]/closes[-20]-1)*100
    
    # Volume-price divergence
    signals=[]
    if vol_ratio>1.5 and chg_5d<-3:
        signals.append('放量下跌 — 主力出货信号')
    elif vol_ratio>1.5 and chg_5d>3:
        signals.append('放量上涨 — 主力吸筹信号')
    elif vol_ratio<0.5 and chg_5d>3:
        signals.append('缩量上涨 — 惜售信号，趋势延续')
    elif vol_ratio<0.5 and chg_5d<-3:
        signals.append('缩量下跌 — 无人接盘，趋势偏弱')
    
    # Score
    vol_score=50
    if '放量上涨' in str(signals):vol_score+=20
    if '放量下跌' in str(signals):vol_score-=20
    if '缩量上涨' in str(signals):vol_score+=10
    vol_score=min(100,max(0,vol_score))
    
    return {
        'vol_ratio':round(vol_ratio,2),
        'vol_vs_20d':round(vol_vs_baseline,2),
        'chg_5d':round(chg_5d,1),
        'signal':','.join(signals) if signals else '量价正常',
        'score':vol_score
    }

# ── Sector momentum ──
def sector_analysis(code):
    """板块分析"""
    sector=get_stock_sector(code)
    heat=get_sector_heat()
    
    # Find which top-level sector
    top_sector='其他'
    for parent,children in SECTOR_HEAT_SOURCE.items():
        if sector in children:
            top_sector=parent;break
    
    # Try to get real sector data from Tencent
    try:
        url='http://web.ifzq.gtimg.cn/appstock/app/board/index?code=sh000001'
        raw=sp.run(['curl','-sL','--max-time','3',url],stdout=sp.PIPE,stderr=sp.PIPE,timeout=5)
        # This endpoint may not work — use fallback
    except:pass
    
    return {
        'sector':sector,
        'top_sector':top_sector,
        'heat':heat.get(top_sector,{}).get('score',50)
    }
