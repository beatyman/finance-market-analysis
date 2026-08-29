#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建 CSI300 Point-in-Time membership 数据

数据源优先级：
    1. akshare index_stock_cons_csindex (中证指数官网，当前成分)
    2. 本地 references/hs300_stocks.csv (历史快照)

产出：references/csi300_membership.csv
      trade_date, code, name, source, source_date

幂等：同一 trade_date 已存在则覆盖该日记录，不影响其它生效日。
"""
import os
import csv
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, '..', 'references')
MEMBERSHIP_FILE = os.path.join(REF, 'csi300_membership.csv')
LEGACY_SNAPSHOT = os.path.join(REF, 'hs300_stocks.csv')


def fetch_current_from_akshare():
    """从 akshare 拉当前沪深300成分。返回 (trade_date_str, [(code,name),...]) 或 None。"""
    try:
        import warnings
        warnings.filterwarnings('ignore')
        import akshare as ak
        df = ak.index_stock_cons_csindex(symbol='000300')
        date_str = str(df['日期'].iloc[0])[:10]
        members = [(str(r['成分券代码']).strip(), str(r['成分券名称']).strip())
                   for _, r in df.iterrows()]
        return date_str, members
    except Exception as e:
        print(f'[warn] akshare 拉取失败: {e}')
        return None


def load_legacy_snapshot():
    """读本地 hs300_stocks.csv 历史快照。返回 (trade_date_str, [(code,name),...]) 或 None。"""
    if not os.path.exists(LEGACY_SNAPSHOT):
        return None
    date_str = None
    members = []
    with open(LEGACY_SNAPSHOT, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            d = (r.get('日期') or '').strip()
            c = (r.get('成分券代码') or '').strip()
            n = (r.get('成分券名称') or '').strip().strip('"')
            if not d or not c:
                continue
            date_str = date_str or d
            members.append((c, n))
    return (date_str, members) if members else None


def load_existing():
    """读已有 membership，返回 {trade_date: {code: name}}。"""
    existing = {}
    if os.path.exists(MEMBERSHIP_FILE):
        with open(MEMBERSHIP_FILE, encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                d = (r['trade_date'] or '').strip()
                c = (r['code'] or '').strip()
                n = (r['name'] or '').strip().strip('"')
                if d and c:
                    existing.setdefault(d, {})[c] = n
    return existing


def main():
    existing = load_existing()

    # 1) akshare 当前成分
    cur = fetch_current_from_akshare()
    if cur:
        d, members = cur
        existing[d] = {c: n for c, n in members}
        print(f'[akshare] {d} 成分 {len(members)} 只')

    # 2) 本地历史快照
    legacy = load_legacy_snapshot()
    if legacy:
        d, members = legacy
        if d not in existing:
            existing[d] = {c: n for c, n in members}
            print(f'[legacy]  {d} 成分 {len(members)} 只（导入历史快照）')
        else:
            print(f'[legacy]  {d} 已存在，跳过')

    # 写回（按 trade_date 排序，code 排序）
    today = datetime.now().strftime('%Y-%m-%d')
    with open(MEMBERSHIP_FILE, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['trade_date', 'code', 'name', 'source', 'source_date'])
        for d in sorted(existing.keys()):
            for c in sorted(existing[d].keys()):
                src = 'akshare' if d != '2026-06-23' else 'csindex'
                w.writerow([d, c, existing[d][c], src, today])

    n_dates = len(existing)
    print(f'\n写入 {MEMBERSHIP_FILE}')
    for d in sorted(existing.keys()):
        print(f'  {d}: {len(existing[d])} 只')


if __name__ == '__main__':
    main()
