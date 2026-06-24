#!/usr/bin/env python3
"""缠论知识库语义确认 — 封装 chanstock-skill 的搜索引擎"""
import subprocess as sp,os,sys,json
HERE=os.path.dirname(os.path.abspath(__file__))

KB_SEARCH=os.path.join(HERE,'chanlun_kb_search.py')
KB_ROOT=os.path.join(HERE,'..','references','chan_kb')

def kb_confirm(bsp_type,position,price):
    """用知识库确认买卖点"""
    query=''
    if '1' in bsp_type:query+='一类买点 背驰 '
    if '2' in bsp_type:query+='二类买点 中枢下沿 '
    if '3' in bsp_type:query+='三类买点 中枢上破 '
    if '1p' in bsp_type:query+='盘整背驰买点 '
    if position=='内':query+='中枢震荡 区间套'
    if position=='下':query+='中枢下方 支撑'
    if position=='上':query+='中枢上方 压力'
    if not query:query='买卖点 确认 操作'
    
    try:
        env=os.environ.copy()
        env['PYTHONPATH']=os.path.join(HERE,'..','references')
        r=sp.run(['python3',KB_SEARCH,'search',query,'--top-k','3'],
                 capture_output=True,text=True,timeout=10,cwd=HERE,env=env)
        return r.stdout[:500] if r.stdout else None
    except:
        return None

def evaluate_bsp(code,name,px,bsp_buy,bsp_types,position,zs_range,score):
    """综合评估：知识库搜索 + 规则确认"""
    bsp_label='/'.join(bsp_types) if bsp_types else '-'
    
    confirm=[]
    # Rule-based checks (fast)
    if position=='内' and bsp_buy:
        confirm.append('中枢内买点 — 标准二买/三买形态')
    if '3' in bsp_label:
        confirm.append('三买/三卖 — 最强信号，需量能配合')
    if position=='下' and bsp_buy:
        confirm.append('中枢下买点 — 风险偏高，等次级别确认')
    if not bsp_buy and bsp_types:
        confirm.append('卖出信号 — 中枢上方减仓或中枢下破止损')
    
    # Semantic search (slow — only for high-score stocks)
    semantic=None
    if score>=65:
        sem=kb_confirm(bsp_label,position,px)
        if sem:
            lines=[l for l in sem.split('\n') if l.strip() and not l.startswith('error')]
            if lines:semantic=lines[:3]
    
    # Risk
    risk='中'
    if position=='内':risk='低'
    elif position=='下' and bsp_buy:risk='偏高'
    elif not bsp_buy and position=='上':risk='低'  # selling at high = low risk
    
    # Target
    target=0;profit=''
    if zs_range and '~' in zs_range:
        try:
            parts=zs_range.split(',')[-1:]  # Use last (most recent) ZS range
            lo,hi=map(float,parts[0].split('~'))
            if bsp_buy:target=hi;profit='%.1f%% (目标 ¥%s)'%((target-px)/px*100,str(int(target)))
            elif not bsp_buy:target=lo;profit='%.1f%% (止损 ¥%s)'%((px-target)/px*100,str(int(target)))
        except:pass
    
    return {
        'name':name,'code':code,'price':px,
        'signal':bsp_label,'direction':'Buy' if bsp_buy else('Sell' if bsp_types else 'Hold'),
        'score':score,'position':position,'zs':zs_range,
        'risk':risk,'target':target,'profit':profit,
        'confirmations':confirm,'semantic':semantic
    }
evaluate = evaluate_bsp
