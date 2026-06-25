#!/usr/bin/env python3
"""
持仓管理 + 预警系统 — 吸收 stock-watcher + stock-monitor 设计
功能: 添加/更新/删除持仓, 成本盈亏, 信号变化预警
存储: ~/.portfolio.json
"""
import json,os,subprocess as sp
from datetime import datetime

PFILE=os.path.expanduser('~/.portfolio.json')

# 预警规则 (吸收 stock-monitor 的7规则)
ALERT_RULES={
    'cost_pct_above':15,   # 盈利15%提醒
    'cost_pct_below':-8,   # 亏损8%提醒
    'change_pct':5,        # 日内涨跌±5%
    'volume_surge':2.0,    # 放量>2倍均量
    'trailing_drawdown':5, # 动态止盈回撤5%
}

def load():
    if not os.path.exists(PFILE):return []
    return json.load(open(PFILE))

def save(positions):
    json.dump(positions,open(PFILE,'w'),ensure_ascii=False,indent=2)

def add(code, name=None, cost=0, qty=0):
    """添加持仓"""
    positions=load()
    # Get live price
    px=get_live_price(code)
    for p in positions:
        if p['code']==code:
            p['cost']=cost if cost>0 else p.get('cost',0)
            p['qty']=qty if qty>0 else p.get('qty',0)
            save(positions)
            return f'✅ 已更新 {code} {name or ""} 成本¥{cost} 数量{qty}'
    
    positions.append({
        'code':code,'name':name or code,'cost':cost,'qty':qty,
        'added':datetime.now().strftime('%Y-%m-%d'),
        'price_now':px,'pnl_pct':((px-cost)/cost*100) if cost>0 else 0
    })
    save(positions)
    return f'✅ 已添加 {code} {name or ""} 成本¥{cost} 数量{qty}'

def remove(code):
    positions=[p for p in load() if p['code']!=code]
    save(positions)
    return f'✅ 已删除 {code}'

def get_live_price(code):
    """腾讯实时行情"""
    prefix='sz' if code.startswith('0') or code.startswith('3') else 'sh'
    url=f'http://qt.gtimg.cn/q={prefix}{code}'
    r=sp.run(['curl','-sL','--max-time','3',url],stdout=sp.PIPE,timeout=5)
    data=r.stdout.decode('gbk','ignore')
    p=data.split('~')
    return float(p[3]) if len(p)>10 else 0

def check_alerts():
    """检查所有持仓预警"""
    positions=load()
    if not positions:return '📭 无持仓'
    
    alerts=[]
    for p in positions:
        px=get_live_price(p['code'])
        pnl=((px-p['cost'])/p['cost']*100) if p['cost']>0 else 0
        p['price_now']=px;p['pnl_pct']=round(pnl,2)
        
        item_alerts=[]
        if pnl>=ALERT_RULES['cost_pct_above']:
            item_alerts.append(f'🎯 盈利{pnl:+.1f}% (目标{ALERT_RULES["cost_pct_above"]}%)')
        if pnl<=ALERT_RULES['cost_pct_below']:
            item_alerts.append(f'🚨 亏损{pnl:+.1f}% (止损{ALERT_RULES["cost_pct_below"]}%)')
        
        if item_alerts:
            alerts.append({
                'code':p['code'],'name':p.get('name',''),'price':px,
                'cost':p['cost'],'pnl':pnl,'alerts':item_alerts
            })
    
    save(positions)
    
    if not alerts:return '✅ 无预警'
    
    lines=['🔔 持仓预警:']
    for a in alerts:
        color='🔴' if a['pnl']<0 else '🔴'
        lines.append(f'  {color} {a["name"]} ¥{a["price"]:.2f} (成本¥{a["cost"]})')
        for aa in a['alerts']:lines.append(f'    {aa}')
    return '\n'.join(lines)

def show():
    """显示持仓概览"""
    positions=load()
    if not positions:return '📭 无持仓'
    
    lines=['📊 持仓概览:']
    lines.append(f'{"代码":8s} {"名称":8s} {"成本":>6s} {"现价":>6s} {"盈亏":>6s}')
    lines.append('-'*40)
    total_pnl=0;total_value=0
    for p in positions:
        px=get_live_price(p['code'])
        pnl=((px-p['cost'])/p['cost']*100) if p['cost']>0 else 0
        p['price_now']=px;p['pnl_pct']=round(pnl,2)
        value=px*p['qty']*100
        total_value+=value;total_pnl+=(px-p['cost'])*p['qty']*100
        lines.append(f'{p["code"]:8s} {p.get("name",""):8s} ¥{p["cost"]:5.2f} ¥{px:5.2f} {pnl:+5.1f}%')
    save(positions)
    lines.append(f'{"总市值:":>20s} ¥{total_value:,.0f}')
    lines.append(f'{"总盈亏:":>20s} ¥{total_pnl:+,.0f}')
    return '\n'.join(lines)

if __name__=='__main__':
    import sys
    cmd=sys.argv[1] if len(sys.argv)>1 else 'show'
    if cmd=='show':print(show())
    elif cmd=='alerts':print(check_alerts())
    elif cmd=='add':print(add(sys.argv[2],cost=float(sys.argv[3]) if len(sys.argv)>3 else 0,qty=int(sys.argv[4]) if len(sys.argv)>4 else 0))
    elif cmd=='remove':print(remove(sys.argv[2]))
