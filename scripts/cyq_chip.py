#!/usr/bin/env python3
"""
筹码分布(CYQ)算法 — 吸收自 myhhub/stock (InStock股票系统)

A股特有的三角分布筹码模型：每根K线在 [low, high] 区间按三角分布堆叠筹码
(均价 avg=(open+close+high+low)/4 为峰值)，换手率模拟筹码换手衰减。

输出指标：
  - benefit_part  获利盘比例(当前价下方筹码占比)  0~1
  - avg_cost      平均成本(50%筹码成本价)
  - percent_chips 筹码集中度(90%/70%筹码的价格区间 + 集中度系数)
  - 套牢盘/获利盘分界

用法:
  from cyq_chip import calc_cyq
  r = calc_cyq(opens, closes, highs, lows, turnovers, crange=120, cyq_days=210)
  r['benefit_part']  # 获利盘比例
  r['avg_cost']      # 平均成本
  r['concentration'] # 90%筹码集中度(越小越集中)
"""
import numpy as np


def calc_cyq(opens, closes, highs, lows, turnovers=None,
             accuracy_factor=150, crange=120, cyq_days=210):
    """计算筹码分布指标。

    参数:
      opens/closes/highs/lows: 数组(K线)
      turnovers: 换手率数组(0-100), 若为None则用成交量归一化近似
      crange: 计算K线范围
      cyq_days: 筹码计算交易天数

    返回 dict:
      benefit_part, avg_cost, concentration_90, concentration_70,
      price_range_90, price_range_70
    """
    n = len(closes)
    if n < 10:
        return {'benefit_part': None, 'avg_cost': None,
                'concentration_90': None, 'concentration_70': None,
                'price_range_90': None, 'price_range_70': None}

    opens = np.asarray(opens, dtype=float)
    closes = np.asarray(closes, dtype=float)
    highs = np.asarray(highs, dtype=float)
    lows = np.asarray(lows, dtype=float)

    # 换手率: 缺省时用成交量近似(需调用方传入turnovers)
    if turnovers is None:
        turnovers = np.full(n, 1.0)  # 无换手率时默认1%
    else:
        turnovers = np.asarray(turnovers, dtype=float)

    end = n - crange + 1 if n > crange else 0
    start = max(0, end - cyq_days)
    if end == 0:
        start = max(0, n - cyq_days)

    sl = slice(start, n)
    o = opens[sl]; c = closes[sl]; h = highs[sl]; l = lows[sl]; t = turnovers[sl]

    maxprice = float(h.max())
    minprice = float(l.min())
    factor = accuracy_factor
    accuracy = max(0.01, (maxprice - minprice) / (factor - 1))
    currentprice = float(c[-1])

    # 三角分布堆叠筹码
    xdata = np.zeros(factor)
    for open_p, close_p, high_p, low_p, turnover_p in zip(o, c, h, l, t):
        avg = (open_p + close_p + high_p + low_p) / 4
        turnover_rate = min(1.0, turnover_p / 100.0) if turnover_p else 0.0

        H = int((high_p - minprice) / accuracy)
        L = int((low_p - minprice) / accuracy + 0.99)
        L = max(0, min(L, factor - 1))
        H = max(0, min(H, factor - 1))
        # G点坐标: 一字板时 X 为进度因子
        G = (factor - 1) if high_p == low_p else 2.0 / (high_p - low_p)
        G_idx = int((avg - minprice) / accuracy)
        G_idx = max(0, min(G_idx, factor - 1))

        # 换手衰减(旧筹码按换手率减少)
        xdata *= (1.0 - turnover_rate)

        if high_p == low_p:
            # 一字板: 矩形面积是三角形2倍
            xdata[G_idx] += G * turnover_rate / 2
        else:
            for j in range(L, H + 1):
                curprice = minprice + accuracy * j
                if curprice <= avg:
                    if abs(avg - low_p) < 1e-8:
                        xdata[j] += G * turnover_rate
                    else:
                        xdata[j] += (curprice - low_p) / (avg - low_p) * G * turnover_rate
                else:
                    if abs(high_p - avg) < 1e-8:
                        xdata[j] += G * turnover_rate
                    else:
                        xdata[j] += (high_p - curprice) / (high_p - avg) * G * turnover_rate

    total_chips = float(xdata.sum())
    if total_chips <= 0:
        return {'benefit_part': None, 'avg_cost': None,
                'concentration_90': None, 'concentration_70': None,
                'price_range_90': None, 'price_range_70': None}

    # 指定筹码处的成本价
    def get_cost_by_chip(chip):
        sum_chips = 0.0
        for i in range(factor):
            x = xdata[i]
            if sum_chips + x > chip:
                return minprice + i * accuracy
            sum_chips += x
        return minprice + (factor - 1) * accuracy

    # 指定百分比筹码的价格区间 + 集中度
    def percent_chips(percent):
        ps = [(1 - percent) / 2, (1 + percent) / 2]
        pr = [get_cost_by_chip(total_chips * ps[0]),
              get_cost_by_chip(total_chips * ps[1])]
        concentration = 0 if (pr[0] + pr[1]) == 0 else (pr[1] - pr[0]) / (pr[0] + pr[1])
        return pr, concentration

    # 获利盘比例(当前价下方筹码)
    below = float(xdata[:int((currentprice - minprice) / accuracy) + 1].sum()) \
        if currentprice > minprice else 0.0
    benefit_part = below / total_chips if total_chips > 0 else 0.0

    pr90, conc90 = percent_chips(0.9)
    pr70, conc70 = percent_chips(0.7)

    return {
        'benefit_part': round(benefit_part, 4),       # 获利盘比例 0~1
        'avg_cost': round(get_cost_by_chip(total_chips * 0.5), 2),  # 平均成本
        'concentration_90': round(conc90, 4),          # 90%筹码集中度(越小越集中)
        'concentration_70': round(conc70, 4),          # 70%筹码集中度
        'price_range_90': [round(pr90[0], 2), round(pr90[1], 2)],
        'price_range_70': [round(pr70[0], 2), round(pr70[1], 2)],
    }


def calc_chip_score(benefit_part, concentration_90, price, avg_cost):
    """筹码评分(0-100) — 基于获利盘/集中度/主力成本 三维度。

    基准 50 分，三因子调整：
      获利盘比例: 深度套牢(<0.1)-20 | 健康(0.25~0.8)+10 | 几乎全获利(>0.9)-15
      筹码集中度: 高度集中(<0.08)+20 | 较集中(<0.15)+10 | 分散(>0.25)-10
      距主力成本: 接近成本上方(-5%~15%)+15 | 远高于(>50%)-15 | 跌破(<-10%)-10

    返回 (score, veto, detail):
      score  0-100 筹码评分
      veto   True 时 = 筹码深度套牢且现价远高于主力成本(追高接盘风险, 建议否决)
      detail 各维度调整说明
    """
    score = 50.0
    veto = False
    detail = []

    # 1. 获利盘比例
    if benefit_part is not None:
        if benefit_part < 0.1:
            score -= 20
            detail.append('深度套牢')
        elif benefit_part < 0.25:
            detail.append('获利盘偏低')
        elif benefit_part <= 0.8:
            score += 10
            detail.append('筹码健康')
        elif benefit_part <= 0.9:
            detail.append('获利盘偏高')
        else:
            score -= 15
            detail.append('几乎全获利')

    # 2. 筹码集中度(越小越集中)
    if concentration_90 is not None:
        if concentration_90 < 0.08:
            score += 20
            detail.append('高度控盘')
        elif concentration_90 < 0.15:
            score += 10
            detail.append('较集中')
        elif concentration_90 > 0.25:
            score -= 10
            detail.append('筹码分散')

    # 3. 现价 vs 平均成本(主力成本锚)
    dist = None
    if avg_cost is not None and price is not None and avg_cost > 0:
        dist = (price - avg_cost) / avg_cost
        if -0.05 <= dist <= 0.15:
            score += 15
            detail.append('接近主力成本')
        elif dist < -0.10:
            score -= 10
            detail.append('跌破主力成本')
        elif dist > 0.50:
            score -= 15
            detail.append('远高于成本')
        elif dist > 0.30:
            score -= 5
            detail.append('偏高主力成本')

    # 否决: 深度套牢 + 现价远高于主力成本(主力获利巨大, 追高接盘)
    if benefit_part is not None and benefit_part < 0.1 and dist is not None and dist > 0.5:
        veto = True

    return round(max(0.0, min(100.0, score)), 1), veto, '|'.join(detail)


def fetch_turnover_batch(codes, sleep=0.15):
    """东财批量取换手率(%) — 免费直连, 返回 {code: turnover_float}

    codes: 6位代码列表(如 '600547')
    接口: push2.eastmoney.com/api/qt/stock/get?secid={market}.{code}&fields=f168
      market: 6开头=1(沪), 0/3开头=0(深)
      f168 换手率需 ÷100
    节流: 默认 sleep 0.15s 防限流(东财连续快速请求会返回空)
    """
    import subprocess, time, json
    headers = ['-H', 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
               '-H', 'Referer: https://quote.eastmoney.com/']
    turnovers = {}
    for code in codes:
        code = str(code).zfill(6)
        market = '1' if code.startswith('6') else '0'
        url = 'https://push2.eastmoney.com/api/qt/stock/get?secid={}.{}&fields=f168'.format(market, code)
        f168 = None
        for attempt in range(2):  # 失败重试1次
            try:
                r = subprocess.run(['curl', '-s', '--max-time', '8'] + headers + [url],
                                   stdout=subprocess.PIPE, timeout=10)
                d = json.loads(r.stdout)
                f168 = d.get('data', {}).get('f168')
                if f168 not in (None, '-', ''):
                    break
                time.sleep(0.3)  # 限流重试前等待
            except Exception:
                f168 = None
        if f168 not in (None, '-', ''):
            turnovers[code] = float(f168) / 100.0
        if sleep:
            time.sleep(sleep)
    return turnovers


if __name__ == '__main__':
    # 快速自测: 生成一段模拟K线
    np.random.seed(42)
    n = 250
    px = 30 + np.cumsum(np.random.randn(n) * 0.5)
    opens = px + np.random.randn(n) * 0.2
    closes = px + np.random.randn(n) * 0.2
    highs = np.maximum(opens, closes) + abs(np.random.randn(n) * 0.3)
    lows = np.minimum(opens, closes) - abs(np.random.randn(n) * 0.3)
    turnovers = np.random.uniform(1, 8, n)
    r = calc_cyq(opens, closes, highs, lows, turnovers)
    print('筹码分布自测:')
    for k, v in r.items():
        print('  {} = {}'.format(k, v))
