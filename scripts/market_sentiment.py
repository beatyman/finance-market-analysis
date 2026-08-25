#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股市场情绪温度计 (吸收 a-stock-daily-review)

抓涨停/炸板/跌停/昨涨停池(东财 push2ex), 计算情绪指标, 输出温度计分级。
情绪退潮期好股也难涨——选股 = 个股信号 × 市场情绪。

用法:
    python3 market_sentiment.py               # 今天(需收盘后)
    python3 market_sentiment.py --date 20260825
"""
import argparse
import json
import random
import time
from collections import Counter

import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
ZTB_UT = "7eea3edcaed734bea9cbfc24409ed989"
SESSION = requests.Session()
SESSION.trust_env = False
SESSION.headers.update({"User-Agent": UA})


def em_get(url, params, timeout=12):
    """东财串行限流(1s+)"""
    time.sleep(random.uniform(1.0, 1.4))
    try:
        return SESSION.get(url, params=params, timeout=timeout)
    except Exception:
        return None


def zt_api(endpoint, date_str, sort):
    url = f"https://push2ex.eastmoney.com/{endpoint}"
    params = {"ut": ZTB_UT, "dpt": "wz.ztzt", "Pageindex": 0,
              "pagesize": 10000, "sort": sort, "date": date_str}
    r = em_get(url, params)
    if r is None:
        return []
    try:
        return (r.json().get("data") or {}).get("pool") or []
    except Exception:
        return []


def fetch_pools(date_str):
    zt = zt_api("getTopicZTPool", date_str, "fbt:asc")       # 涨停
    zb = zt_api("getTopicZBPool", date_str, "fbt:asc")       # 炸板
    dt = zt_api("getTopicDTPool", date_str, "fund:asc")      # 跌停
    yzt = zt_api("getYesterdayZTPool", date_str, "zs:desc")  # 昨涨停
    return zt, zb, dt, yzt


def market_sentiment(date_str):
    zt, zb, dt, yzt = fetch_pools(date_str)
    if not zt:
        return {'error': f'{date_str} 涨停池为空(非交易日或数据未更新)', 'date': date_str}

    # 1. 涨停/炸板/跌停 + 炸板率
    zt_n, zb_n, dt_n = len(zt), len(zb), len(dt)
    break_rate = round(zb_n / (zt_n + zb_n) * 100, 1) if (zt_n + zb_n) else 0

    # 2. 连板梯队
    limit_days = [p.get('lbc', 1) for p in zt]
    max_board = max(limit_days) if limit_days else 0
    ladder = Counter(limit_days)
    ladder_sorted = sorted(ladder.items(), reverse=True)

    # 3. 昨涨停溢价 + 晋级率 + 大面
    yzt_n = len(yzt)
    prem = 0.0
    advance_n = 0
    big_loss = 0
    if yzt:
        pcts = [p.get('zdp', 0) for p in yzt]
        prem = round(sum(pcts) / len(pcts), 2)
        advance_n = sum(1 for x in pcts if x >= 9.8)  # 今日仍涨停≈晋级
        big_loss = sum(1 for x in pcts if x <= -7)     # 大面
    advance_rate = round(advance_n / yzt_n * 100, 1) if yzt_n else 0

    # 4. 情绪温度计分级
    def temp_level():
        if zt_n >= 100 and advance_rate >= 40 and max_board >= 6:
            return '🔥 过热', '高潮警惕退潮, 减仓止盈'
        if zt_n >= 60 and advance_rate >= 30:
            return '🟢 热', '容错率高, 可积极做多'
        if zt_n >= 30 and advance_rate >= 20:
            return '🟡 中性', '精选个股, 控制仓位'
        if zt_n >= 15:
            return '⚪ 冷', '减仓防守, 等情绪修复'
        return '🧊 冰点', '冰点转机, 关注逆势龙头'

    level, advice = temp_level()

    return {
        'date': date_str,
        'zt_n': zt_n, 'zb_n': zb_n, 'dt_n': dt_n, 'break_rate': break_rate,
        'max_board': max_board, 'ladder': ladder_sorted,
        'yzt_n': yzt_n, 'premium': prem, 'advance_rate': advance_rate, 'big_loss': big_loss,
        'level': level, 'advice': advice,
    }


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--date', default=None, help='YYYYMMDD, 默认今天')
    args = p.parse_args()
    date_str = args.date or time.strftime('%Y%m%d')
    r = market_sentiment(date_str)
    if 'error' in r:
        print(r['error'])
    else:
        print(f"=== A股市场情绪温度计 {r['date']} ===")
        print(f"涨停 {r['zt_n']} | 炸板 {r['zb_n']} | 跌停 {r['dt_n']} | 炸板率 {r['break_rate']}%")
        print(f"连板梯队: {dict(r['ladder'])}  (最高 {r['max_board']} 板)")
        print(f"昨涨停 {r['yzt_n']} 只 | 溢价 {r['premium']:+.2f}% | 晋级率 {r['advance_rate']}% | 大面 {r['big_loss']} 只")
        print(f"情绪: {r['level']}")
        print(f"操作: {r['advice']}")
