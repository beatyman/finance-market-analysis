#!/usr/bin/env python3
"""板块热点 — 通达信 easy-tdx 实时数据"""
import time

def get_board_hot():
    """获取概念+行业板块Top排行"""
    try:
        from easy_tdx import MacClient, BoardType
        with MacClient.from_best_host() as client:
            concept=client.get_board_ranking(BoardType.GN,top_n=8,sort_by="change_pct")
            industry=client.get_board_ranking(BoardType.HY,top_n=8,sort_by="change_pct")
        
        lines=[]
        lines.append('## 🔥 板块热点 (通达信实时)')
        
        cols=['name','change_pct','amount','main_net_amount','up_count','down_count']
        
        lines.append('\n### 概念板块 Top 8')
        lines.append('| 板块 | 涨跌 | 成交(亿) | 主力净流入(亿) | 上涨 |')
        lines.append('|------|------|----------|---------------|------|')
        for _,r in concept.head(8).iterrows():
            amt=float(r['amount'])/1e8;net=float(r['main_net_amount'])/1e8
            up=int(r['up_count']);total=up+int(r['down_count'])
            lines.append('| %s | %+.1f%% | %.0f | %+.1f | %d/%d |'%(r['name'],float(r['change_pct']),amt,net,up,total))
        
        lines.append('\n### 行业板块 Top 8')
        lines.append('| 板块 | 涨跌 | 成交(亿) | 主力净流入(亿) | 上涨 |')
        lines.append('|------|------|----------|---------------|------|')
        for _,r in industry.head(8).iterrows():
            amt=float(r['amount'])/1e8;net=float(r['main_net_amount'])/1e8
            up=int(r['up_count']);total=up+int(r['down_count'])
            lines.append('| %s | %+.1f%% | %.0f | %+.1f | %d/%d |'%(r['name'],float(r['change_pct']),amt,net,up,total))
        
        return '\n'.join(lines)
    except Exception as e:
        return '板块数据获取失败: %s'%str(e)[:80]

if __name__=='__main__':
    print(get_board_hot())
