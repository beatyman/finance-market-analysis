#!/usr/bin/env python3
"""板块热度引擎 — 基于板块内个股的涨跌/成交量/缠论信号密度"""
import subprocess as sp,json,os
HERE=os.path.dirname(os.path.abspath(__file__))

# ── 板块成员映射 ──
SECTOR_MEMBERS={
    'AI算力':['002475','603019','601138','000977','002837','603019','688008','603986'],
    '半导体':['002371','688041','603893','603501','688981'],
    '新能源':['002594','300750','603606'],
    '消费电子':['002475','002463','002384','603501'],
    '光通信':['002281','000988','300308'],
    '黄金/商品':['600489','601899','002428'],
    '金融':['600030','600036','601318'],
    '互联网(HK)':['00700','09988','03690','01024'],
    '医药':['600276','06618','603259'],
    '工业':['601100','600089','000338','601985','300124'],
    'PCB':['002463','002384','300476'],
    '消费':['000858','601888'],
}

def get_sector_heat_tencent():
    """从腾讯行情推断板块热度"""
    all_codes=[]
    for members in SECTOR_MEMBERS.values():
        all_codes.extend(members)
    all_codes=list(set(all_codes))
    
    # Batch quotes
    quotes={}
    for i in range(0,len(all_codes),80):
        batch=all_codes[i:i+80]
        a_batch=[c for c in batch if not c.startswith('0')]
        hk_batch=['hk'+c for c in batch if c.startswith('0')]
        qt=','.join([('sh'+c if c.startswith('6') else 'sz'+c) for c in a_batch]+hk_batch)
        try:
            r=sp.run(['curl','-s','--max-time','4','http://qt.gtimg.cn/q='+qt],stdout=sp.PIPE,stderr=sp.PIPE,timeout=6)
            for line in r.stdout.decode('gbk','ignore').strip().split('\n'):
                parts=line.split('~')
                if len(parts)<40:continue
                px=0;chg=0
                try:px=float(parts[3]);chg=float(parts[32])
                except:continue
                if px>0:
                    cr=line.split('=')[0].replace('v_','').replace('_','')
                    code=cr.replace('hk','') if cr.startswith('hk') else cr[2:]
                    quotes[code]=chg
        except:pass
    
    # Calculate sector heat
    heat={}
    for sector,members in SECTOR_MEMBERS.items():
        changes=[quotes[c] for c in members if c in quotes]
        if changes:
            avg_chg=sum(changes)/len(changes)
            pos=sum(1 for c in changes if c>0)
            heat[sector]={
                'avg_chg':round(avg_chg,2),
                'up_ratio':round(pos/len(changes)*100,1),
                'score':min(100,max(0,int(50+avg_chg*10+pos/len(changes)*30))),
                'active':len(changes)
            }
    return heat

def sector_signal(code_or_name,heat=None):
    """返回股票所属板块的热度信号"""
    if heat is None:
        try:heat=get_sector_heat_tencent()
        except:heat={}
    
    # Find sector
    pure=code_or_name.replace('hk','')
    sector='其他'
    for sec,members in SECTOR_MEMBERS.items():
        if pure in members:sector=sec;break
    
    h=heat.get(sector,{})
    if not h:return {'sector':sector,'signal':'无数据','score':50}
    
    score=h.get('score',50);avg=h.get('avg_chg',0);up=h.get('up_ratio',50)
    if avg>2 and up>60:signal='🔥 板块领涨'
    elif avg>0:signal='🟢 板块偏强'
    elif avg>-2:signal='🟡 板块中性'
    else:signal='🔴 板块偏弱'
    
    return {'sector':sector,'signal':signal,'score':score,'avg_chg':avg,'up_ratio':up}

if __name__=='__main__':
    heat=get_sector_heat_tencent()
    print('板块热度:')
    for sec in sorted(heat.keys(),key=lambda s:heat[s]['score'],reverse=True):
        h=heat[sec];bar='🔥' if h['score']>70 else('🟢' if h['score']>55 else('🟡' if h['score']>45 else '🔴'))
        print('  %s %-12s %+5.1f%% %5.1f%%↑ %d分 %d股'%(bar,sec,h['avg_chg'],h['up_ratio'],h['score'],h['active']))
