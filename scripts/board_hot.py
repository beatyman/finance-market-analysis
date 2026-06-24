#!/usr/bin/env python3
"""板块实时涨幅+资金流 — easy-tdx 通达信"""
from easy_tdx import MacClient, BoardType

BOARDS=['BK0877','BK0891','BK1650','BK1680','BK1128','BK1408',
        'BK1036','BK1138','BK1624','BK1331','BK1101','BK0478']

BOARD_NAMES={
    'BK0877':'PCB概念','BK0891':'半导体概念','BK1650':'AI概念',
    'BK1680':'存储芯片','BK1128':'光刻胶','BK1408':'先进封装',
    'BK1036':'CPO概念','BK1138':'EDA概念','BK1624':'铜缆高速',
    'BK1331':'液冷散热','BK1101':'机器人概念','BK0478':'汽车电子',
}

def get_board_flow():
    results={}
    try:
        c=MacClient.from_best_host()
        concept=c.get_board_ranking(BoardType.GN,top_n=100,sort_by="change_pct")
        c.close()
        
        for bk in BOARDS:
            match=concept[concept['code']==bk] if 'code' in concept.columns else None
            if match is not None and len(match)>0:
                r=match.iloc[0]
                results[bk]={
                    'name':BOARD_NAMES.get(bk,bk),
                    'chg':float(r.get('change_pct',0)),
                    'amount':float(r.get('amount',0))/1e8,
                    'net_inflow':float(r.get('main_net_amount',0))/1e8,
                    'up':int(r.get('up_count',0)),
                    'total':int(r.get('up_count',0))+int(r.get('down_count',0)),
                }
    except:pass
    return results

def format_board_flow():
    flow=get_board_flow()
    if not flow:return '(板块数据获取失败)'
    
    lines=['## 🔥 12板块实时数据 (通达信)']
    lines.append('| 板块 | 涨跌 | 成交(亿) | 主力净流入(亿) | 上涨 |')
    lines.append('|------|------|----------|---------------|------|')
    
    for bk,data in sorted(flow.items(),key=lambda x:-x[1]['chg']):
        up_pct=int(data['up']/max(data['total'],1)*100)
        bar='🔥' if data['chg']>3 else('🟢' if data['chg']>1 else('🔴' if data['chg']<-1 else '🟡'))
        lines.append(f'| {bar} {data["name"]} | {data["chg"]:+.1f}% | {data["amount"]:.0f} | {data["net_inflow"]:+.1f} | {data["up"]}/{data["total"]}({up_pct}%) |')
    
    return '\n'.join(lines)

if __name__=='__main__':
    print(format_board_flow())
