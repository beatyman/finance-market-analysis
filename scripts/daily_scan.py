# -*- coding: utf-8 -*-
"""
每日背驰扫描器 — 下跌-盘整-下跌-盘整-再下跌 形态扫描

目标形态：三次下跌笔逐个背驰（力度一次比一次小）
- 盘整可以是中枢形态，也可以是回调形态
- 最后一笔下跌可能未完成（假设成笔连接到已出现的底分型）
- 如果最后一笔下跌没有出现底分型，就暂时不算一笔

四层漏斗：
  第1层：基础过滤（候选池已剔除ST/5元以下/亏损）
  第2层：K线过滤（K线≥60根+近期有新低）
  第3层：缠论结构初筛（至少5根笔+至少3根下跌笔）
  第4层：背驰检测（三次下跌逐个背驰）
"""
import sys
import json
import time
from pathlib import Path

SCRIPTS_PATH = Path("/Users/we-mac/资料库/workbuddy/背驰选股/scripts")
sys.path.insert(0, str(SCRIPTS_PATH))

import chanlun_v2 as v2

CACHE_PATH = Path("/Users/we-mac/资料库/workbuddy/V61 选股器/data/cache")
POOL_PATH = Path("/Users/we-mac/资料库/workbuddy/背驰选股/data/liquidity_top500_pool.json")
OUTPUT_PATH = Path("/Users/we-mac/资料库/workbuddy/背驰选股/outputs")


def load_pool():
    """加载候选池"""
    if not POOL_PATH.exists():
        print(f"候选池文件不存在: {POOL_PATH}")
        print("请先运行: python3 scripts/generate_pool.py")
        sys.exit(1)
    data = json.load(open(POOL_PATH))
    return data.get('pool', [])


def check_kline_filter(bars):
    """第2层：K线过滤"""
    if len(bars) < 60:
        return False, f"K线不足({len(bars)}<60)"

    # 近20根K线中有新低（确保处于下跌趋势）
    recent = bars[-20:]
    lows = [b['low'] for b in recent]
    all_lows = [b['low'] for b in bars]
    if min(lows) >= min(all_lows[:-20]) if len(all_lows) > 20 else True:
        # 近20根的最低点没有创历史新低
        # 放宽条件：近20根中有明显下跌即可
        recent_close = [b['close'] for b in recent]
        if len(recent_close) >= 10:
            first_half = sum(recent_close[:10]) / 10
            second_half = sum(recent_close[-10:]) / 10
            if second_half >= first_half * 0.98:
                return False, "近20根无明显下跌"

    return True, ""


def check_structure_filter(bis):
    """第3层：缠论结构初筛"""
    if len(bis) < 5:
        return False, f"笔不足({len(bis)}<5)"

    # 至少3根下跌笔（top→bottom方向）
    down_count = 0
    for i in range(len(bis) - 1):
        if bis[i][0] == 'top' and bis[i + 1][0] == 'bottom':
            down_count += 1
    if down_count < 3:
        return False, f"下跌笔不足({down_count}<3)"

    return True, ""


def detect_triple_decline_divergence(bis, dif, hist, closes, bars):
    """
    第4层：检测"下跌-盘整-下跌-盘整-再下跌"形态的三次逐个背驰

    从最新的下跌笔开始，往前追溯找满足条件的三根下跌笔：
      下跌1 → 盘整 → 下跌2 → 盘整 → 下跌3
      力度：下跌1 > 下跌2 > 下跌3（逐个背驰）

    盘整可以是中枢形态（多笔重叠），也可以是回调形态（单笔反向）。
    最后一笔下跌可能未完成（假设成笔连接到已出现的底分型）。
    """
    n_bi = len(bis) - 1

    if n_bi < 5:
        return None

    # 收集所有下跌笔（top→bottom）的索引
    down_legs = []
    for i in range(n_bi):
        if bis[i][0] == 'top' and bis[i + 1][0] == 'bottom':
            down_legs.append(i)

    if len(down_legs) < 3:
        return None

    # 从最新的下跌笔开始，往前追溯
    # 尝试所有可能的(D1, D2, D3)组合
    # D3是最新的下跌笔（最后一根），D2是前一根，D1是再前一根
    best_result = None
    best_score = 0

    # D3从最新的下跌笔开始
    for d3_pos in range(len(down_legs) - 1, 1, -1):
        d3_idx = down_legs[d3_pos]
        d3_start, d3_end = bis[d3_idx][3], bis[d3_idx + 1][3]
        d3_price_end = bis[d3_idx + 1][2]

        # 检查最后一笔是否未完成
        last_bi_complete = (d3_idx < n_bi - 1)

        # 计算D3力度
        p3, a3, h3 = v2._force(dif, hist, d3_start, d3_end, up=False)
        a3_eff = max(a3, h3)

        # D2：在D3之前找一根下跌笔，力度>D3，且D2和D3之间有盘整
        for d2_pos in range(d3_pos - 1, 0, -1):
            d2_idx = down_legs[d2_pos]
            d2_start, d2_end = bis[d2_idx][3], bis[d2_idx + 1][3]
            d2_price_end = bis[d2_idx + 1][2]

            # D2和D3之间至少有1根反向笔（盘整）
            if d3_idx - d2_idx < 2:
                continue

            # D3必须创新低
            if d3_price_end >= d2_price_end:
                continue

            # 计算D2力度
            p2, a2, h2 = v2._force(dif, hist, d2_start, d2_end, up=False)
            a2_eff = max(a2, h2)

            if a2_eff <= 0:
                continue

            # 背驰条件：D2 vs D3，D3力度 < D2力度
            area_ratio_23 = a3_eff / a2_eff
            dif_ratio_23 = abs(p3 / p2) if p2 != 0 else 0

            if area_ratio_23 >= 1.0 or dif_ratio_23 >= 1.0:
                continue

            # D1：在D2之前找一根下跌笔，力度>D2，且D1和D2之间有盘整
            for d1_pos in range(d2_pos - 1, -1, -1):
                d1_idx = down_legs[d1_pos]
                d1_start, d1_end = bis[d1_idx][3], bis[d1_idx + 1][3]
                d1_price_end = bis[d1_idx + 1][2]

                # D1和D2之间至少有1根反向笔（盘整）
                if d2_idx - d1_idx < 2:
                    continue

                # D2必须创新低
                if d2_price_end >= d1_price_end:
                    continue

                # 计算D1力度
                p1, a1, h1 = v2._force(dif, hist, d1_start, d1_end, up=False)
                a1_eff = max(a1, h1)

                if a1_eff <= 0:
                    continue

                # 背驰条件：D1 vs D2，D2力度 < D1力度
                area_ratio_12 = a2_eff / a1_eff
                dif_ratio_12 = abs(p2 / p1) if p1 != 0 else 0

                if area_ratio_12 >= 1.0 or dif_ratio_12 >= 1.0:
                    continue

                # 找到满足条件的三根下跌笔！
                # 计算综合评分
                score = 60
                score += (1 - min(area_ratio_12, 1.0)) * 20
                score += (1 - min(area_ratio_23, 1.0)) * 20
                score += (1 - min(dif_ratio_12, 1.0)) * 10
                score += (1 - min(dif_ratio_23, 1.0)) * 10

                # 越近的D3加分越多（时效性）
                recency = len(closes) - 1 - d3_end
                if recency <= 5:
                    score += 10
                elif recency <= 10:
                    score += 5

                if score > best_score:
                    max_area_ratio = max(area_ratio_12, area_ratio_23)
                    max_dif_ratio = max(dif_ratio_12, dif_ratio_23)
                    if max_area_ratio < 0.01 and max_dif_ratio < 0.1:
                        label = '极强背驰'
                    elif max_area_ratio < 0.3:
                        label = '强背驰'
                    else:
                        label = '背驰'

                    best_score = score
                    best_result = {
                        'status': 'confirmed' if last_bi_complete else 'forming',
                        'mode': '三次逐个背驰',
                        'kind': 'bottom',
                        'score': round(score, 1),
                        'label': label,
                        'd1': {'start': d1_start, 'end': d1_end,
                               'price_start': bis[d1_idx][2], 'price_end': d1_price_end,
                               'dif': p1, 'area': a1_eff,
                               'date_start': bars[d1_start]['date'], 'date_end': bars[d1_end]['date']},
                        'd2': {'start': d2_start, 'end': d2_end,
                               'price_start': bis[d2_idx][2], 'price_end': d2_price_end,
                               'dif': p2, 'area': a2_eff,
                               'date_start': bars[d2_start]['date'], 'date_end': bars[d2_end]['date']},
                        'd3': {'start': d3_start, 'end': d3_end,
                               'price_start': bis[d3_idx][2], 'price_end': d3_price_end,
                               'dif': p3, 'area': a3_eff,
                               'date_start': bars[d3_start]['date'], 'date_end': bars[d3_end]['date']},
                        'area_ratio_12': round(area_ratio_12, 4),
                        'dif_ratio_12': round(dif_ratio_12, 4),
                        'area_ratio_23': round(area_ratio_23, 4),
                        'dif_ratio_23': round(dif_ratio_23, 4),
                        'oidx': d3_end,
                        'recency': recency,
                        'current_price': closes[-1],
                        'd3_price': d3_price_end,
                        'price_change': round((closes[-1] - d3_price_end) / d3_price_end * 100, 2) if d3_price_end > 0 else 0,
                    }

    return best_result


def scan_stock(code, bars, name):
    """扫描单只股票"""
    # 第2层：K线过滤
    ok, reason = check_kline_filter(bars)
    if not ok:
        return None, reason

    highs = [b['high'] for b in bars]
    lows = [b['low'] for b in bars]
    closes = [b['close'] for b in bars]
    volumes = [b.get('volume', 0) for b in bars]

    try:
        bis, centers, dif, dea, hist, _ = v2.analyze(highs, lows, closes, volumes)
    except Exception as e:
        return None, f"分析失败: {e}"

    # 第3层：缠论结构初筛
    ok, reason = check_structure_filter(bis)
    if not ok:
        return None, reason

    # 第4层：背驰检测
    result = detect_triple_decline_divergence(bis, dif, hist, closes, bars)
    if result is None:
        return None, "无三次逐个背驰"

    result['code'] = code
    result['name'] = name
    result['n_bars'] = len(bars)
    result['last_close'] = closes[-1]
    result['last_date'] = bars[-1]['date']

    return result, ""


def main():
    print("=" * 100)
    print("每日背驰扫描器 — 下跌-盘整-下跌-盘整-再下跌 形态")
    print("=" * 100)

    # 加载候选池
    pool = load_pool()
    print(f"\n候选池: {len(pool)}只（流动性前500+过滤）")

    # 统计
    results = []
    stats = {'total': 0, 'layer2_pass': 0, 'layer3_pass': 0, 'layer4_pass': 0}

    t0 = time.time()

    for i, item in enumerate(pool):
        code = item['code']
        name = item['name']
        stats['total'] += 1

        # 加载K线数据
        cache_file = CACHE_PATH / f"{code}.json"
        if not cache_file.exists():
            continue

        try:
            data = json.load(open(cache_file))
            bars = data.get('bars', [])
            if not bars:
                continue

            result, reason = scan_stock(code, bars, name)
            if result is not None:
                stats['layer4_pass'] += 1
                results.append(result)
            elif "K线不足" in reason or "无明显下跌" in reason:
                pass  # 第2层过滤
            elif "笔不足" in reason or "下跌笔不足" in reason:
                stats['layer2_pass'] += 1
            else:
                stats['layer3_pass'] += 1

        except Exception as e:
            pass

        if (i + 1) % 100 == 0:
            print(f"  进度: {i+1}/{len(pool)} ...")

    elapsed = time.time() - t0
    print(f"\n扫描完成! 耗时 {elapsed:.1f}秒")

    # 统计
    forming = [r for r in results if r['status'] == 'forming']
    confirmed = [r for r in results if r['status'] == 'confirmed']

    print(f"\n结果统计:")
    print(f"  扫描总数: {stats['total']}")
    print(f"  通过K线过滤: ~{stats['layer2_pass'] + stats['layer3_pass'] + stats['layer4_pass']}")
    print(f"  通过结构初筛: ~{stats['layer3_pass'] + stats['layer4_pass']}")
    print(f"  检测到三次逐个背驰: {stats['layer4_pass']}")
    print(f"    ├ forming(最后一笔未完成): {len(forming)}")
    print(f"    └ confirmed(已完成): {len(confirmed)}")

    # 按评分排序
    results.sort(key=lambda x: x['score'], reverse=True)

    # 显示结果
    if forming:
        print(f"\n{'='*120}")
        print(f"正在形成中的三次逐个背驰 (forming) — 共{len(forming)}只")
        print(f"{'='*120}")
        print(f"{'排名':>4} {'代码':<12} {'名称':<10} {'评分':>6} {'标签':<8} {'面积比12':>8} {'DIF比12':>8} {'面积比23':>8} {'DIF比23':>8} {'D3日期':>12} {'已跌':>7}")
        print(f"{'-'*4} {'-'*12} {'-'*10} {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*12} {'-'*7}")
        for i, r in enumerate(forming[:30]):
            print(f"{i+1:>4} {r['code']:<12} {r['name'][:8]:<10} {r['score']:>6.1f} "
                  f"{r['label']:<8} {r['area_ratio_12']:>8.3f} {r['dif_ratio_12']:>8.3f} "
                  f"{r['area_ratio_23']:>8.3f} {r['dif_ratio_23']:>8.3f} {r['d3']['date_end']:>12} {r['price_change']:>+6.1f}%")

    if confirmed:
        print(f"\n{'='*120}")
        print(f"已确认的三次逐个背驰 (confirmed) — 共{len(confirmed)}只")
        print(f"{'='*120}")
        print(f"{'排名':>4} {'代码':<12} {'名称':<10} {'评分':>6} {'标签':<8} {'面积比12':>8} {'DIF比12':>8} {'面积比23':>8} {'DIF比23':>8} {'D3日期':>12} {'涨跌':>7}")
        print(f"{'-'*4} {'-'*12} {'-'*10} {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*12} {'-'*7}")
        for i, r in enumerate(confirmed[:30]):
            print(f"{i+1:>4} {r['code']:<12} {r['name'][:8]:<10} {r['score']:>6.1f} "
                  f"{r['label']:<8} {r['area_ratio_12']:>8.3f} {r['dif_ratio_12']:>8.3f} "
                  f"{r['area_ratio_23']:>8.3f} {r['dif_ratio_23']:>8.3f} {r['d3']['date_end']:>12} {r['price_change']:>+6.1f}%")

    if not results:
        print("\n未检测到任何三次逐个背驰形态")

    # 保存结果
    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    output = {
        'scan_time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'pool_size': len(pool),
        'total_scanned': stats['total'],
        'forming_count': len(forming),
        'confirmed_count': len(confirmed),
        'results': results,
    }

    out_file = OUTPUT_PATH / "daily_scan_result.json"
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n结果已保存: {out_file}")


if __name__ == '__main__':
    main()
