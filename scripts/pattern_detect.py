# 15策略形态吸收 → enhanced_tools.py 扩展模块
# 来源: https://github.com/wei1104/bigApush

import numpy as np

def detect_w_bottom(close, volume, pattern_days=40, low_window=5, min_gap=10):
    """
    W底形态检测
    返回: (is_w, neckline, confidence) 或 (False, None, 0)
    """
    n = len(close)
    if n < pattern_days: return False, None, 0
    
    recent = close[-pattern_days:]
    vol = volume[-pattern_days:] if len(volume) >= pattern_days else volume
    
    # 找局部低点
    lows = []
    for i in range(low_window, len(recent) - low_window):
        if recent[i] == min(recent[i-low_window:i+low_window+1]):
            lows.append((i, recent[i]))
    
    if len(lows) < 2: return False, None, 0
    
    # 找相邻两低点满足双底条件
    for i in range(len(lows)-1):
        for j in range(i+1, min(i+5, len(lows))):
            l1_time, l1_price = lows[i]
            l2_time, l2_price = lows[j]
            
            if l2_time - l1_time < min_gap: continue
            if abs(l1_price/l2_price - 1) > 0.03: continue  # 价格差<3%
            
            # 颈线: L1和L2之间的最高点
            neck = max(recent[l1_time:l2_time+1])
            
            # 突破确认: 当前价 > 颈线
            if recent[-1] > neck:
                # 量价: 突破日放量
                vol_ratio = vol[-1] / vol[-5:].mean() if len(vol) >= 5 else 1
                confidence = min(100, 60 + 20 * (vol_ratio - 1) if vol_ratio > 1 else 40)
                return True, neck, int(confidence)
    
    return False, None, 0


def detect_multi_party_cannon(open_p, close, high, low, volume):
    """
    多方炮: 两阳夹一阴 K线组合
    返回: (is_cannon, strength_score)
    """
    n = len(close)
    if n < 3: return False, 0
    
    # Day-2, Day-1, Day-0
    o1, c1, l1 = open_p[-3], close[-3], low[-3]
    o2, c2, l2 = open_p[-2], close[-2], low[-2]
    o0, c0, l0 = open_p[-1], close[-1], low[-1]
    v1, v2, v0 = volume[-3], volume[-2], volume[-1]
    
    # 第一根: 阳线, 涨幅>=3%
    body1 = c1 - o1
    if body1 <= 0: return False, 0
    rise1 = body1 / o1
    if rise1 < 0.03: return False, 0
    
    # 第二根: 阴线, 实体小, 回调有限
    body2 = o2 - c2
    if body2 <= 0: return False, 0
    if body2 > body1 * 0.5: return False, 0
    if o1 and c1 and (o2 < c1 * 0.97): return False, 0  # 回调不超过3%
    
    # 第三根: 阳线, 涨幅>=3%, 突破第一根高点
    body0 = c0 - o0
    if body0 <= 0: return False, 0
    rise0 = body0 / o0
    if rise0 < 0.03: return False, 0
    if c0 <= c1: return False, 0  # 未突破前高
    
    # 量: 第二根缩量, 第三根放量
    score = 50
    if v1 > 0:
        if v2 <= v1 * 0.8: score += 15
        if v0 >= v1 * 1.2: score += 15
    score += min(20, int(rise0 * 200))
    
    return True, min(100, score)


def detect_strong_wash(close, volume, high, low,
                       short_ma=10, long_ma=30, volume_ma=20):
    """
    强势洗盘弱转强检测
    返回: (is_wash, score)
    """
    n = len(close)
    if n < long_ma + 10: return False, 0
    
    ma_s = np.mean(close[-short_ma:])
    ma_l = np.mean(close[-long_ma:])
    
    # 上升趋势: MA短 > MA长
    if ma_s <= ma_l: return False, 0
    
    # 找最近的高点回撤
    recent = close[-20:]
    peak = recent.max()
    current = close[-1]
    drawdown = (peak - current) / peak
    
    # 回撤5-15%
    if drawdown < 0.05 or drawdown > 0.15: return False, 0
    
    # 缩量: 洗盘时缩量
    v_recent = volume[-20:] if len(volume) >= 20 else volume
    v_ma = np.mean(v_recent)
    v_last = volume[-5:].mean()
    vol_shrink = v_last < v_ma * 0.8
    
    # 开始放量反弹
    v_today = volume[-1]
    v_5avg = volume[-5:].mean() if len(volume) >= 5 else v_today
    vol_expand = v_today > v_5avg * 1.3
    
    score = 40
    if vol_shrink: score += 20
    if vol_expand: score += 20
    score += min(20, int(10 - drawdown * 100))
    
    return True if score >= 50 else False, min(100, score)


def detect_golden_cross_resonance(close, high, low, volume):
    """
    多金叉共振: MA+MACD+KDJ
    返回: dict with ma_cross, macd_cross, kdj_cross, resonance_score
    """
    n = len(close)
    if n < 60: return {'resonance': 0}
    
    # MA金叉: 5日上穿20日
    ma5 = np.convolve(close, np.ones(5)/5, mode='valid')
    ma20 = np.convolve(close, np.ones(20)/20, mode='valid')
    ma_cross = ma5[-2] < ma20[-2] and ma5[-1] > ma20[-1]
    
    # MACD金叉
    ema12 = np.zeros(n)
    ema26 = np.zeros(n)
    ema12[0] = close[0]; ema26[0] = close[0]
    for i in range(1, n):
        ema12[i] = close[i] * 0.15 + ema12[i-1] * 0.85
        ema26[i] = close[i] * 0.075 + ema26[i-1] * 0.925
    dif = ema12 - ema26
    dea = np.convolve(dif, np.ones(9)/9, mode='same')
    macd_cross = dif[-2] < dea[-2] and dif[-1] > dea[-1]
    
    # KDJ金叉 (简化)
    hh = np.max(high[-9:]); ll = np.min(low[-9:])
    rsv = (close[-1] - ll) / (hh - ll) * 100 if hh > ll else 50
    k = rsv * 1/3 + 50 * 2/3  # simplified
    d = k * 1/3 + 50 * 2/3
    kdj_cross = rsv > 50 and close[-1] > close[-2]
    
    score = 0
    if ma_cross: score += 35
    if macd_cross: score += 35
    if kdj_cross: score += 30
    
    return {
        'ma_cross': ma_cross,
        'macd_cross': macd_cross,
        'kdj_cross': kdj_cross,
        'resonance': score,
        'resonance_strong': score >= 65
    }


def detect_fanbao(open_p, close, high, low, volume, turnover=None):
    """
    反包策略 (来源: quantjuzi/fanbao_strategy)
    条件:
      1. 昨天下跌 (close[-2] < close[-3])
      2. 今天阳线反包 (close[-1] > high[-2])
      3. 成交额 >= 10亿 (可选)
      4. 今天未涨停 (close[-1] < pre_close * 1.095)
      5. 涨幅 >= 3%
    返回: (is_fanbao, strength, detail_dict)
    """
    n = len(close)
    if n < 3: return False, 0, {}
    
    c_yesterday, c_today = close[-2], close[-1]
    c_daybefore = close[-3]
    h_yesterday = high[-2]
    
    # 1. 昨天下跌
    if c_yesterday >= c_daybefore: return False, 0, {}
    
    # 2. 今天阳线反包
    if open_p[-1] >= c_today: return False, 0, {}  # 非阳线
    if c_today <= h_yesterday: return False, 0, {}  # 未反包
    
    # 3. 成交额 (如果提供了turnover)
    if turnover is not None and turnover < 10e8: return False, 0, {}
    
    # 4. 未涨停
    rise = (c_today - c_daybefore) / c_daybefore
    if c_today >= c_daybefore * 1.095: return False, 0, {}
    
    # 5. 涨幅 >= 3%
    if rise < 0.03: return False, 0, {}
    
    # 量: 今日放量
    v_ratio = volume[-1] / volume[-5:].mean() if len(volume) >= 5 else 1
    strength = 50 + min(30, int(rise * 500)) + min(20, int((v_ratio - 1) * 50))
    strength = min(100, strength)
    
    return True, strength, {
        'type': '反包',
        'yesterday_pct': round((c_yesterday - c_daybefore) / c_daybefore * 100, 1),
        'today_rise': round(rise * 100, 1),
        'volume_ratio': round(v_ratio, 1),
        'hold_days': 1,  # 次日买入, 隔日9:40卖出
        'score': strength
    }
