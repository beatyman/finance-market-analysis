#!/usr/bin/env python3
"""聪明钱(SMC)视角分析器 — OpenMobius 知识库"""
import os,json,re
HERE=os.path.dirname(os.path.abspath(__file__))
KB=os.path.join(HERE,'..','references','smc_kb')

def load_index():
    """加载知识点索引"""
    idx_path=os.path.join(KB,'concepts','index.json')  # Or other index file
    concepts_dir=os.path.join(KB,'concepts')
    concepts={}
    if os.path.exists(concepts_dir):
        for f in os.listdir(concepts_dir):
            if f.endswith('.json') and f!='index.json':
                try:
                    with open(os.path.join(concepts_dir,f)) as fh:
                        d=json.load(fh)
                        name=f.replace('.json','')
                        concepts[name]=d
                except:pass
    return concepts

def search_smc(query):
    """搜索SMC知识库"""
    concepts=load_index()
    results=[]
    q=query.lower()
    for name,data in concepts.items():
        text=name+' '+str(data)
        if any(t in text.lower() for t in q.split()):
            results.append((name,data))
        if len(results)>=10:break
    return results

def smc_analysis(code,name,px,bsp_buy,zs_range,position):
    """从聪明钱角度给出辅助分析"""
    concepts=load_index()
    
    # What SMC concepts apply to this stock?
    insights=[]
    
    # 1. Market Structure
    if position=='下':
        insights.append({
            'concept':'Market Structure Shift (CHoCH)',
            'desc':'价格处于关键结构下方，可能发生趋势转变',
            'action':'等待价格回测中枢确认方向'
        })
    elif position=='内':
        insights.append({
            'concept':'Range / Consolidation',
            'desc':'价格在中枢内震荡，聪明钱在此区域积累/派发',
            'action':('中枢下沿买入，上沿卖出' if bsp_buy else '等待方向突破')
        })
    
    # 2. Order Blocks
    if zs_range:
        insights.append({
            'concept':'Order Block',
            'desc':'中枢作为订单块区域——聪明钱在此建仓',
            'action':'中枢下沿(OB下轨)是主要需求区'
        })
    
    # 3. Premium/Discount
    if position=='上':
        insights.append({
            'concept':'Premium Zone',
            'desc':'价格在溢价区，聪明钱倾向于卖出',
            'action':'不宜追高'
        })
    elif position=='下':
        insights.append({
            'concept':'Discount Zone',
            'desc':'价格在折价区，聪明钱在此寻找买入机会',
            'action':'关注反弹信号' if bsp_buy else '继续观察，等待吸筹完成'
        })
    
    # 4. Liquidity
    if zs_range:
        parts=zs_range.split(',')
        if len(parts)>=2:
            insights.append({
                'concept':'Liquidity Pool',
                'desc':'中枢上下沿聚集大量止损/止盈订单(流动性池)',
                'action':'突破中枢时跟随流动性方向'
            })
    
    # 5. FVG — 如果价格远离中枢中心
    if zs_range and '~' in zs_range:
        try:
            first_range=zs_range.split(',')[0]
            lo,hi=map(float,first_range.split('~'))
            center=(lo+hi)/2
            if abs(px-center)>0.05*px:
                insights.append({
                    'concept':'Fair Value Gap',
                    'desc':'价格远离公平价值区(中枢中心)，存在回补缺口动力',
                    'action':'关注价格向中枢回归'
                })
        except:pass
    
    return {
        'symbol':code,'name':name,'price':px,
        'chan_signal':'Buy' if bsp_buy else 'Sell',
        'smc_insights':insights,
        'verdict': 'SMC与缠论共振看多' if bsp_buy and position=='下'
                   else 'SMC与缠论共振看空' if not bsp_buy and position=='上'
                   else 'SMC辅助但需更多确认'
    }
