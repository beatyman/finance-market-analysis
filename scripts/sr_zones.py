#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
S&R 支撑阻力带聚类算法 — 吸收 SPX-Price-Action-Compass (Al Brooks/Bob Volman)

纯函数、零外部依赖。把 Swing 极点聚类成 support/resistance/flip 三类支撑阻力带，
输出触碰强度 + Top N，可配合缠论中枢 + 筹码峰做三重共振验证。

用法:
    from sr_zones import sr_zones
    zones = sr_zones(highs, lows, tolerance=0.0015, top=8)
    # zones: [{'price', 'type'(support/resistance/flip), 'strength', 'min_price', 'max_price'}]
"""


def find_swing_points(highs, lows, left=5, right=5):
    """前后向滑动窗口找局部高低点。返回 (swing_highs, swing_lows)，元素为 (index, price)。"""
    n = len(highs)
    swing_highs = []
    swing_lows = []
    for i in range(left, n - right):
        ch, cl = highs[i], lows[i]
        is_high = True
        is_low = True
        for j in range(1, left + 1):
            if highs[i - j] >= ch:
                is_high = False
            if lows[i - j] <= cl:
                is_low = False
        for j in range(1, right + 1):
            if highs[i + j] > ch:
                is_high = False
            if lows[i + j] < cl:
                is_low = False
        if is_high:
            swing_highs.append((i, ch))
        if is_low:
            swing_lows.append((i, cl))
    return swing_highs, swing_lows


def cluster_sr_zones(swing_highs, swing_lows, tolerance=0.0015, top=8):
    """
    一维凝聚聚类: 把所有 Swing 价格映射到数轴, 按 tolerance 公差聚类。
    返回按 strength 降序的 Top N 支撑阻力带。
    """
    points = [(idx, price, 'high') for idx, price in swing_highs] + \
             [(idx, price, 'low') for idx, price in swing_lows]
    if not points:
        return []

    points.sort(key=lambda p: p[1])  # 按价格排序

    clusters = []
    cur = []
    for p in points:
        if not cur:
            cur.append(p)
        else:
            avg = sum(x[1] for x in cur) / len(cur)
            if abs(p[1] - avg) / avg <= tolerance:
                cur.append(p)
            else:
                clusters.append(cur)
                cur = [p]
    if cur:
        clusters.append(cur)

    zones = []
    for cl in clusters:
        prices = [x[1] for x in cl]
        avg = sum(prices) / len(prices)
        high_touches = sum(1 for x in cl if x[2] == 'high')
        low_touches = sum(1 for x in cl if x[2] == 'low')
        if high_touches > 0 and low_touches == 0:
            ztype = 'resistance'
        elif low_touches > 0 and high_touches == 0:
            ztype = 'support'
        else:
            ztype = 'flip'
        strength = len(cl)
        if strength >= 2:  # 过滤噪声(触碰<2次)
            zones.append({
                'price': round(avg, 2),
                'type': ztype,
                'strength': strength,
                'min_price': round(min(prices) * 0.9995, 2),
                'max_price': round(max(prices) * 1.0005, 2),
            })

    zones.sort(key=lambda z: -z['strength'])
    return zones[:top]


def sr_zones(highs, lows, tolerance=0.0015, top=8, left=5, right=5):
    """一站式: 输入 K线高低序列, 输出支撑阻力带。"""
    sh, sl = find_swing_points(highs, lows, left, right)
    return cluster_sr_zones(sh, sl, tolerance, top)


def split_sr(zones, price):
    """把 zones 分成现价上方的阻力(升序,最近在前)和下方的支撑(降序,最近在前)。"""
    resistances = sorted([z for z in zones if z['price'] > price], key=lambda z: z['price'])
    supports = sorted([z for z in zones if z['price'] < price], key=lambda z: -z['price'])
    return resistances, supports


if __name__ == '__main__':
    # 自测: 用 data.py 拉一只股票验证
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    try:
        from data import fetch_kline_a
        dates, opens, closes, highs, lows, vols = fetch_kline_a('600519')  # 贵州茅台
        zones = sr_zones(highs, lows)
        res, sup = split_sr(zones, closes[-1])
        print(f'贵州茅台现价 {closes[-1]:.2f}')
        print(f'阻力带(近→远):', [(z["price"], z["type"], z["strength"]) for z in res[:3]])
        print(f'支撑带(近→远):', [(z["price"], z["type"], z["strength"]) for z in sup[:3]])
    except Exception as e:
        print(f'自测失败(可能无网络): {e}')
        # 用合成数据自测
        import math
        highs = [10 + 2*math.sin(i/5) + i*0.01 for i in range(100)]
        lows = [h - 0.5 for h in highs]
        zones = sr_zones(highs, lows)
        print('合成数据 S&R 带:', [(z['price'], z['type'], z['strength']) for z in zones])
