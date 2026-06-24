#!/usr/bin/env python3
"""板块实时涨幅+资金流 — easy-tdx 通达信 (9秒)"""
from easy_tdx import MacClient, BoardType

def get_board_flow():
    """概念+行业 Top10 资金流"""
    try:
        c=MacClient.from_best_host()
        gn=c.get_board_ranking(BoardType.GN,top_n=10,sort_by="change_pct")
        hy=c.get_board_ranking(BoardType.HY,top_n=10,sort_by="change_pct")
        c.close()
        
        lines=['## 🔥 板块实时资金流 (通达信)']
        lines.append('\n### 概念 Top 10')
        lines.append('| 板块 | 涨跌 | 成交(亿) | 主力净流入(亿) | 上涨 |')
        lines.append('|------|------|----------|---------------|------|')
        for _,r in gn.iterrows():
            amt=float(r['amount'])/1e8;net=float(r['main_net_amount'])/1e8
            up=int(r['up_count']);total=up+int(r['down_count'])
            lines.append('| %s | %+.1f%% | %.0f | %+.1f | %d/%d |'%(
                r['name'],float(r['change_pct']),amt,net,up,total))
        
        lines.append('\n### 行业 Top 10')
        lines.append('| 板块 | 涨跌 | 成交(亿) | 主力净流入(亿) | 上涨 |')
        lines.append('|------|------|----------|---------------|------|')
        for _,r in hy.iterrows():
            amt=float(r['amount'])/1e8;net=float(r['main_net_amount'])/1e8
            up=int(r['up_count']);total=up+int(r['down_count'])
            lines.append('| %s | %+.1f%% | %.0f | %+.1f | %d/%d |'%(
                r['name'],float(r['change_pct']),amt,net,up,total))
        
        return '\n'.join(lines)
    except:
        return '(板块数据获取失败)'

if __name__=='__main__':
    print(get_board_flow())
