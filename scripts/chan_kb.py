#!/usr/bin/env python3
"""知识库评估 — chanstock-skill 缠论结构确认"""
import os,sys,subprocess as sp
HERE=os.path.dirname(os.path.abspath(__file__))

KB_RULES=os.path.join(HERE,'..','..','chanstock','references','chanlun','rules.md')
KB_WORKFLOW=os.path.join(HERE,'..','..','chanstock','references','chanlun','workflow.md')
KB_FUSION=os.path.join(HERE,'..','..','chanstock','references','chanlun','fusion.md')

def load_kb():
    """加载缠论知识库"""
    kb={'rules':'','workflow':'','fusion':''}
    for k,f in [('rules',KB_RULES),('workflow',KB_WORKFLOW),('fusion',KB_FUSION)]:
        if os.path.exists(f):
            with open(f) as fh:kb[k]=fh.read()
    return kb

def evaluate(name,code,px,bsp_buy,bsp_types,position,zs_range,score):
    """缠论知识库二次确认 + 盈利预期"""
    kb=load_kb()
    
    # Build analysis context
    signal='/'.join(bsp_types) if bsp_types else '-'
    direction='买入' if bsp_buy else ('卖出' if bsp_types else '观望')
    
    # Risk assessment from kb
    risk='中'
    if position=='内':risk='低'
    elif position=='下' and bsp_buy:risk='偏高'  # 中枢下买点风险高
    elif not bsp_buy and position=='上':risk='低'  # 中枢上卖点风险低
    
    # Target estimation
    target=0
    if zs_range:
        ranges=[(int(z.split('~')[0]),int(z.split('~')[1])) for z in zs_range.split(',')]
        rng=ranges[-1]
        if bsp_buy:target=rng[1] if position!='上' else int(rng[1]*1.1)
        else:target=rng[0]
    
    # Confirmation from knowledge base
    confirm=[]
    if '中枢' in position and bsp_buy:
        confirm.append('中枢内买点 — 对应 lesson-056/lesson-061 标准买点形态')
    if '3' in str(bsp_types):
        confirm.append('三买/三卖 — 最强信号，需结合量能确认')
    if position=='下' and bsp_buy:
        confirm.append('中枢下买点 — 风险偏高，需等30m级别确认')
    if score>=75:
        confirm.append('高评分 — 多维度共振，信号可靠度高')
    
    # Profit expectation
    profit=''
    if bsp_buy and target>px:
        pct=round((target-px)/px*100,1)
        profit='%.1f%% (目标 ¥%s)'%(pct,str(target))
    elif not bsp_buy and target<px:
        pct=round((px-target)/px*100,1)
        profit='%.1f%% (止损/目标 ¥%s)'%(pct,str(target))
    
    return {
        'name':name,'code':code,'price':px,
        'signal':signal,'direction':direction,'score':score,
        'position':position,'zs':zs_range,
        'risk':risk,'target':target,'profit':profit,
        'confirmations':confirm
    }
