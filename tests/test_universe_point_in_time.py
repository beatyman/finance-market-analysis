#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CSI300 Point-in-Time 股票池测试"""
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, '..', 'scripts')
sys.path.insert(0, SCRIPTS)

from universe import (get_csi300_members, available_trade_dates,
                      classify_board, coverage_report)


def test_members_300():
    """当前生效成分应为 300 只（含科创板，不再剔除 688）。"""
    members, meta = get_csi300_members(with_meta=True)
    assert members is not None, 'membership 数据为空'
    assert meta['n_members'] == 300, f"期望 300 只, 实际 {meta['n_members']}"


def test_star_board_included():
    """科创板(688) 成分必须保留，不再无条件排除。"""
    members = get_csi300_members()
    star = [c for c, _ in members if c.startswith('688')]
    assert len(star) > 0, '科创板成分股被错误排除'


def test_point_in_time_rollback():
    """asof 日期应回退到 <= asof 的最近生效日。"""
    dates = available_trade_dates()
    assert len(dates) >= 1, '至少有一个生效日'
    # 未来日期 -> 最近生效日
    future = get_csi300_members(datetime(2030, 1, 1))
    latest = get_csi300_members()
    assert [c for c, _ in future] == [c for c, _ in latest], '未来日期应回退到最近生效日'
    # 早于最早记录 -> 最早记录
    early = get_csi300_members(datetime(2000, 1, 1))
    assert len(early) == 300


def test_coverage_report():
    """覆盖率报告：缺数据时 coverage < 1 且标记 degraded。"""
    members = get_csi300_members()
    fetched = {c for c, _ in members[:293]}  # 模拟缺 7 只 (coverage 0.9767 < 0.98)
    rep = coverage_report(members, fetched)
    assert rep['coverage'] < 1.0
    assert rep['degraded'] is True
    # 全覆盖
    rep2 = coverage_report(members, {c for c, _ in members})
    assert rep2['coverage'] == 1.0
    assert rep2['degraded'] is False


def test_classify_board():
    assert classify_board('688008') == 'STAR'
    assert classify_board('000001') == 'SZ'
    assert classify_board('600000') == 'SH_MAIN'


if __name__ == '__main__':
    test_members_300()
    test_star_board_included()
    test_point_in_time_rollback()
    test_coverage_report()
    test_classify_board()
    print('universe point-in-time tests: ALL PASS')
