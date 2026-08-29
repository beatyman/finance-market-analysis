#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSI300 Point-in-Time 股票池

解决：静态 hs300_stocks.csv 快照 + 无条件排除 688 导致的
      (1) 非严格完整沪深300  (2) 历史回放幸存者偏差。

核心接口：
    get_csi300_members(asof_date=None) -> List[Tuple[code, name]]

规则：
    - 任何历史日期只能使用 <= asof_date 的最近一个生效日(trade_date)的成分。
    - 不再按代码前缀无条件排除科创板(688)。
    - 数据不支持的板块 -> 标记 eligibility_reason，由上层报告覆盖率，
      而不是一边剔除一边声称"300 只全量"。
"""
import os
import csv
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, '..', 'references')
MEMBERSHIP_FILE = os.path.join(REF, 'csi300_membership.csv')

# 数据源不支持的板块（用 eligibility 标记，而非静默剔除）
UNSUPPORTED_PREFIXES = ()  # V2: 不再无条件排除任何前缀

_membership_cache = None  # {trade_date_str: [(code, name), ...]}


def _load_membership(force=False):
    """读 membership 数据，按 trade_date 分组。"""
    global _membership_cache
    if _membership_cache is not None and not force:
        return _membership_cache
    grouped = {}
    if os.path.exists(MEMBERSHIP_FILE):
        with open(MEMBERSHIP_FILE, encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                d = (r['trade_date'] or '').strip()
                c = (r['code'] or '').strip()
                n = (r['name'] or '').strip().strip('"')
                if not d or not c:
                    continue
                grouped.setdefault(d, []).append((c, n))
    _membership_cache = grouped
    return grouped


def available_trade_dates():
    """所有已记录的生效日（升序）。"""
    return sorted(_load_membership().keys())


def get_csi300_members(asof_date=None, with_meta=False):
    """
    返回 asof_date 生效的沪深300成分股列表 [(code, name), ...]。
    asof_date 为 None 或未来日期 -> 使用最近生效日。
    返回 None 若 membership 数据为空。
    """
    grouped = _load_membership()
    if not grouped:
        return None
    dates = sorted(grouped.keys())
    if asof_date is None:
        picked = dates[-1]
    else:
        asof = asof_date.strftime('%Y-%m-%d') if hasattr(asof_date, 'strftime') else str(asof_date)
        picked = None
        for d in dates:  # 升序取最后一个 <= asof
            if d <= asof:
                picked = d
        if picked is None:
            picked = dates[0]  # 早于最早记录 -> 用最早记录（并可由上层报告降级）
    members = grouped[picked]
    if with_meta:
        asof_str = asof_date.strftime('%Y-%m-%d') if (asof_date is not None and hasattr(asof_date, 'strftime')) else None
        is_exact = True if asof_str is None else (picked == asof_str)
        return members, {'trade_date': picked,
                         'asof': asof_str,
                         'n_members': len(members),
                         'is_exact': is_exact}
    return members


def classify_board(code):
    """返回板块标识，供上层做 eligibility 标记。"""
    if code.startswith('688'):
        return 'STAR'          # 科创板
    if code.startswith(('8', '4', '83', '87', '92')):
        return 'BSE'           # 北交所
    if code.startswith('6'):
        return 'SH_MAIN'
    if code.startswith(('0', '3')):
        return 'SZ'
    return 'OTHER'


def coverage_report(members, fetched_codes):
    """
    覆盖率报告。fetched_codes = 实际成功取到数据的 code 集合。
    返回 dict。
    """
    n_total = len(members)
    fetched = {c for c, _ in members if c in fetched_codes}
    missing = [(c, n) for c, n in members if c not in fetched_codes]
    n_fetched = len(fetched)
    return {
        'n_total': n_total,
        'n_fetched': n_fetched,
        'coverage': round(n_fetched / n_total, 4) if n_total else 0.0,
        'missing': missing,
        'degraded': (n_fetched / n_total) < 0.98 if n_total else True,
    }


if __name__ == '__main__':
    members, meta = get_csi300_members(with_meta=True)
    print(f'生效日: {meta["trade_date"]}  成分股: {meta["n_members"]} 只')
    if members:
        star = [c for c, _ in members if c.startswith('688')]
        print(f'其中科创板(688): {len(star)} 只')
        print('前5只:', members[:5])
