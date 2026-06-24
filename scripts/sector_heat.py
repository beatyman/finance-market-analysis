#!/usr/bin/env python3
"""板块热度引擎 — 腾讯实时行情 + 本地 AKShare CSV 回退"""
import subprocess as sp,json,os,csv
HERE=os.path.dirname(os.path.abspath(__file__))
REF=os.path.join(HERE,'..','references')

# ── 板块成员映射 ──
SECTOR_MEMBERS={
    'AI算力':['002475','603019','601138','000977','002837'],
    '半导体':['002371','688041','603893','603501','688981'],
    '新能源':['002594','300750','603606'],
    '消费电子':['002475','002463','002384','603501'],
    '光通信':['002281','000988'],
    '黄金/商品':['600489','601899','002428'],
    '金融':['600030','600036','601318'],
    '互联网(HK)':['00700','09988','03690','01024'],
    '医药':['600276','06618'],
    '工业':['601100','600089','000338','601985','300124'],
    'PCB':['002463','002384','300476'],
    '消费':['000858','601888'],
}


def _ak_with_retry(fn, max_retries=3):
    """AKShare 带重试的调用"""
    import time
    for i in range(max_retries):
        try:return fn()
        except:
            if i<max_retries-1:time.sleep(5*(i+1))
    return None

def get_sector_from_akshare():
    """直接从 AKShare 获取板块数据（需东财网络）"""
    try:
        import akshare as ak
        industry=_ak_with_retry(ak.stock_board_industry_name_em)
        concept=_ak_with_retry(ak.stock_board_concept_name_em)
        if industry is None and concept is None:return {}
        import pandas as pd
        dfs=[]
        if industry is not None:dfs.append(industry)
        if concept is not None:dfs.append(concept)
        df=pd.concat(dfs,ignore_index=True) if dfs else None
        if df is None:return {}
        data={}
        for _,r in df.iterrows():
            try:
                data[r['板块名称']]={
                    'chg':float(r.get('涨跌幅',0) or 0),
                    'up':int(r.get('上涨家数',0) or 0),
                    'dn':int(r.get('下跌家数',0) or 0),
                    'volume':float(r.get('总市值',0) or 0)
                }
            except:pass
        return data
    except:return {}
def load_local_sector_csv():
    """加载Windows同步的AKShare板块CSV"""
    csv_path=os.path.join(REF,'sector_data.csv')
    if not os.path.exists(csv_path):return {}
    data={}
    with open(csv_path,'r',encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            name=row.get('板块名称','')
            chg=float(row.get('涨跌幅',0) or 0)
            try:
                vol=float(row.get('总市值','0') or 0)
                up=int(row.get('上涨家数',0) or 0)
                dn=int(row.get('下跌家数',0) or 0)
            except:vol=0;up=0;dn=0
            data[name]={'chg':chg,'up':up,'dn':dn,'volume':vol}
    return data

def get_sector_fund_flow_tencent():
    """腾讯板块指数资金流"""
    try:
        r=sp.run(['curl','-sL','--max-time','5','http://web.ifzq.gtimg.cn/appstock/app/board/index?code=sh000001'],
                 stdout=sp.PIPE,stderr=sp.PIPE,timeout=7)
        d=json.loads(r.stdout);ff=d['data']['fundflow']
        flows={}
        for ptype in ['plate','concept']:
            for item in ff.get(ptype,{}).get('top',[]):
                flows[item['name']]={
                    'zdf':float(item['zdf']),
                    'net_flow':float(item['zljlr'])/10000,  # 元 → 万元
                    'money':float(item['cje'])/100000000     # 元 → 亿元
                }
        return flows
    except:return {}

def get_sector_heat():
    """综合板块热度 — AKShare直接 > CSV > 腾讯回退"""
    # 1. Try AKShare directly (server-side, with retry)
    local=get_sector_from_akshare()
    if not local:local=load_local_sector_csv()
    if len(local)>10:return local
    
    # 2. Fallback: Tencent member stock heat
    quotes=_fetch_quotes()
    heat={}
    for sec,members in SECTOR_MEMBERS.items():
        changes=[quotes[c] for c in members if c in quotes]
        if not changes:continue
        avg=sum(changes)/len(changes)
        up=sum(1 for c in changes if c>0)
        score=min(100,max(0,int(50+avg*10+up/len(changes)*30)))
        heat[sec]={'chg':round(avg,2),'up':up,'dn':len(changes)-up,'score':score}
    return heat

def _fetch_quotes():
    """批量获取个股涨跌"""
    all_codes=list(set(c for m in SECTOR_MEMBERS.values() for c in m))
    quotes={}
    for i in range(0,len(all_codes),80):
        batch=all_codes[i:i+80]
        qt=','.join([('sh'+c if c.startswith('6') else 'sz'+c) for c in batch if not c.startswith('0')]+
                    ['hk'+c for c in batch if c.startswith('0')])
        try:
            r=sp.run(['curl','-s','--max-time','4','http://qt.gtimg.cn/q='+qt],
                     stdout=sp.PIPE,stderr=sp.PIPE,timeout=6)
            for line in r.stdout.decode('gbk','ignore').strip().split('\n'):
                p=line.split('~')
                if len(p)<40:continue
                try:chg=float(p[32]);px=float(p[3])
                except:continue
                if px>0:
                    cr=line.split('=')[0].replace('v_','').replace('_','')
                    code=cr.replace('hk','') if cr.startswith('hk') else cr[2:]
                    quotes[code]=chg
        except:pass
    return quotes

def sector_signal(code_or_name,heat=None):
    """板块信号"""
    if heat is None:heat=get_sector_heat()
    pure=code_or_name.replace('hk','')
    sec='其他'
    for s,members in SECTOR_MEMBERS.items():
        if pure in members:sec=s;break
    
    h=heat.get(sec,{})
    if not h:return {'sector':sec,'signal':'无数据','avg_chg':0,'up_ratio':0,'score':50}
    
    chg=h.get('chg',0)
    total=max(h.get('up',0)+h.get('dn',0),1)
    up_r=h.get('up',0)/total*100
    score=h.get('score',50)
    
    if chg>2 and up_r>60:signal='🔥 板块领涨'
    elif chg>0:signal='🟢 板块偏强'
    elif chg>-2:signal='🟡 板块中性'
    else:signal='🔴 板块偏弱'
    
    return {'sector':sec,'signal':signal,'score':score,'avg_chg':chg,'up_ratio':up_r}

if __name__=='__main__':
    heat=get_sector_heat()
    flows=get_sector_fund_flow_tencent()
    
    src='本地 AKShare CSV' if len(heat)>10 else '腾讯个股推断'
    print(f'板块热度 ({src}):')
    for sec in sorted(heat.keys(),key=lambda s:heat[s].get('score',0),reverse=True):
        h=heat[sec];chg=h.get('chg',0)
        bar='🔥' if chg>2 else('🟢' if chg>0 else('🟡' if chg>-2 else '🔴'))
        flow_str=''
        if sec in flows:flow_str=' 资金:%+.0f万'%flows[sec]['net_flow']
        print(f'  {bar} {sec:12s} {chg:+5.1f}%  ↑{h.get("up",0)}/↓{h.get("dn",0)}{flow_str}')
    
    if len(heat)<=10:
        print('\n💡 放置 AKShare 导出的 sector_data.csv 到 references/ 获取全量板块数据')
