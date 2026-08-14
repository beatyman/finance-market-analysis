#!/usr/bin/env python3
"""沪深300四框架增强评分 — 江恩八分位 + MACD多级别共振 + Ari动量
吸收 futures-four-framework, 适配A股日线(单级别输入, 内部降采样周线)

输出: enhance_score(0-100) + 三框架明细, 并入综合推荐排序
"""
import numpy as np


def _sma(v, p):
    out = np.full(len(v), np.nan)
    if len(v) >= p:
        c = np.convolve(v, np.ones(p) / p, mode='valid')
        out[p - 1:] = c
    return out


def _ema(v, p):
    out = np.full(len(v), np.nan)
    k = 2 / (p + 1)
    prev = np.nan
    for i in range(len(v)):
        prev = v[i] if np.isnan(prev) else v[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def _macd(closes):
    e12 = _ema(closes, 12); e26 = _ema(closes, 26)
    dif = e12 - e26
    dea = _ema(dif, 9)
    hist = 2 * (dif - dea)
    return dif, dea, hist


def _rsi(closes, p=14):
    delta = np.diff(closes)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    out = np.full(len(closes), np.nan)
    if len(closes) <= p:
        return out
    avg_g = gain[:p].mean(); avg_l = loss[:p].mean()
    out[p] = 100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    for i in range(p + 1, len(closes)):
        avg_g = (avg_g * (p - 1) + gain[i - 1]) / p
        avg_l = (avg_l * (p - 1) + loss[i - 1]) / p
        out[i] = 100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    return out


def _round_tick(v, tick):
    return round(v / tick) * tick


def compute_gann_enhance(closes, highs, lows, tick=None):
    """四框架增强评分 — 单只股票日线
    
    Args:
        closes/highs/lows: np.array 日线
        tick: 价格最小变动(默认自动=价格*0.002)
    
    Returns:
        dict: enhance_score(0-100), gann, macd, ari 明细
    """
    closes = np.asarray(closes, float)
    highs = np.asarray(highs, float)
    lows = np.asarray(lows, float)
    n = len(closes)
    if n < 60:
        return {'enhance_score': 50.0, 'gann': None, 'macd': None, 'ari': None,
                'note': '数据不足60根'}
    tick = tick or max(closes[-1] * 0.002, 0.01)
    price = closes[-1]

    # ── 江恩八分位 (近120根摆动) ──
    lb = 120 if n >= 120 else n
    seg_h = highs[-lb:]; seg_l = lows[-lb:]
    li = int(np.argmin(seg_l)); hi = int(np.argmax(seg_h))
    low, high = seg_l[li], seg_h[hi]
    direction = 1 if li < hi else -1  # 1上升摆动 -1下降摆动
    span = max(high - low, tick * 8)
    pos8 = (price - low) / span  # 0~1
    # 江恩分: 位置偏下=偏多(低吸), 偏上=偏空; 上升摆动+0.5
    gann_pos_score = (0.5 - pos8) * 4  # pos8=0 → +2, pos8=1 → -2
    gann_dir_score = 0.5 * direction
    gann_score = gann_pos_score + gann_dir_score
    support = low + span * int(pos8 * 8) / 8
    resistance = support + span / 8
    # 1×1速度线
    elapsed = max(abs(hi - li), 1)
    slope = span / elapsed
    bars_after = lb - 1 - (li if direction == 1 else hi)
    line_1x1 = (low + slope * bars_after) if direction == 1 else (high - slope * bars_after)
    gann_line_rel = 1 if price >= line_1x1 else -1

    # ── MACD 多级别共振 (日线 + 周线降采样) ──
    dif_d, dea_d, hist_d = _macd(closes)
    hist_d_last = hist_d[-1]; hist_d_prev = hist_d[-2]
    # 周线降采样(每5根)
    if n >= 250:
        wk = closes[-(n // 5 * 5):].reshape(-1, 5)
        wk_close = wk[:, -1]
        _, _, hist_w = _macd(wk_close)
        hist_w_last = hist_w[-1]
    else:
        hist_w_last = hist_d_last
    # 共振分: 日线+周线同向
    macd_d_part = 1.5 if hist_d_last >= 0 else -1.5
    macd_d_part += 0.5 if hist_d_last >= hist_d_prev else -0.5
    macd_w_part = 1.0 if hist_w_last >= 0 else -1.0
    macd_score = macd_d_part + macd_w_part  # 范围约 -3~+3

    # ── Ari 动量 (MA20多空线 + RSI) ──
    ma20 = _sma(closes, 20)
    above_ma20 = 1 if price >= ma20[-1] else -1
    rsi = _rsi(closes)
    rsi_last = rsi[-1]
    if rsi_last >= 75:
        ari_rsi_score = -0.5  # 过热
    elif rsi_last <= 25:
        ari_rsi_score = 0.0  # 过冷(不追空, 但也不追多)
    else:
        ari_rsi_score = 0.5 if rsi_last >= 55 else (-0.5 if rsi_last <= 45 else 0)
    ma20_slope = ma20[-1] - ma20[-6] if not np.isnan(ma20[-6]) else 0
    ari_score = 1.5 * above_ma20 + (0.75 if ma20_slope > 0 else -0.75) + ari_rsi_score

    # ── 综合增强分 (0-100) ──
    # 各框架归一化到 ~[-4,+4], 加权后映射到 0-100
    gann_n = np.clip(gann_score, -3, 3) * 0.33      # ~[-1,1]
    macd_n = np.clip(macd_score, -3, 3) * 0.33      # ~[-1,1]
    ari_n = np.clip(ari_score, -3, 3) * 0.33        # ~[-1,1]
    composite = (gann_n + macd_n + ari_n) / 3        # ~[-1,1]
    enhance_score = 50 + composite * 50               # 0-100

    return {
        'enhance_score': round(float(enhance_score), 1),
        'gann': {
            'direction': '上升摆动' if direction == 1 else '下降摆动',
            'pos8': round(float(pos8 * 8), 2),
            'support': round(support, 3), 'resistance': round(resistance, 3),
            'line_1x1': round(line_1x1, 3),
            'line_above': gann_line_rel == 1,
            'score': round(float(gann_score), 2),
        },
        'macd': {
            'hist': round(float(hist_d_last), 4),
            'hist_w': round(float(hist_w_last), 4),
            'score': round(float(macd_score), 2),
            'resonance': '日周共振偏多' if (hist_d_last >= 0 and hist_w_last >= 0)
                         else ('日周共振偏空' if (hist_d_last < 0 and hist_w_last < 0)
                               else '日周分歧'),
        },
        'ari': {
            'above_ma20': above_ma20 == 1,
            'rsi': round(float(rsi_last), 1) if not np.isnan(rsi_last) else None,
            'score': round(float(ari_score), 2),
            'env': '多头主场' if (above_ma20 == 1 and ari_score > 0)
                   else ('空头主场' if (above_ma20 == -1 and ari_score < 0) else '过渡区'),
        },
    }


if __name__ == '__main__':
    # 测试: 用随机合成数据
    np.random.seed(1)
    n = 250
    px = 100 + np.cumsum(np.random.randn(n) * 1.0)
    h = px + np.abs(np.random.randn(n) * 0.5)
    l = px - np.abs(np.random.randn(n) * 0.5)
    r = compute_gann_enhance(px, h, l)
    print('增强分:', r['enhance_score'])
    print('江恩:', r['gann'])
    print('MACD:', r['macd'])
    print('Ari:', r['ari'])
