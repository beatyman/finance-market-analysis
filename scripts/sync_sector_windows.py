#!/usr/bin/env python3
"""
Windows 板块数据同步脚本 — 每天跑一次，导出 AKShare 板块数据到 CSV
scp 到服务器: references/sector_data.csv
"""
import akshare as ak,pandas as pd,os
from datetime import datetime

OUTPUT=os.path.join(os.path.dirname(__file__) if '__file__' in dir() else '.','sector_data.csv')

print(f'[{datetime.now():%Y-%m-%d %H:%M}] 开始获取板块数据...')

try:
    # 1. 行业板块
    industry=ak.stock_board_industry_name_em()
    print(f'  行业板块: {len(industry)} 个')
    
    # 2. 概念板块
    concept=ak.stock_board_concept_name_em()
    print(f'  概念板块: {len(concept)} 个')
    
    # Merge
    df=pd.concat([industry,concept],ignore_index=True)
    df.to_csv(OUTPUT,index=False,encoding='utf-8-sig')
    
    print(f'✅ 保存: {OUTPUT} ({len(df)} 个板块)')
    print(f'   scp {OUTPUT} root@server:~/.hermes/skills/a-share-market-analysis/references/')
    
    # Show top flows
    if '主力净流入' in df.columns:
        top=df.nlargest(5,'主力净流入')
        print('\n主力净流入 Top 5:')
        for _,r in top.iterrows():
            print(f'  {r["板块名称"]:10s} {r["主力净流入"]:+.0f}万')

except Exception as e:
    print(f'❌ 失败: {e}')
