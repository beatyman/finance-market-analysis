#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股经典形态选股策略（吸收 InStock / myhhub-stock core/strategy/）

10 个纯函数选股形态，零外部依赖（仅 pandas/numpy），可直接接入
csi300_full_scan.py / analyze.py 作为形态共振信号。

统一输入: df 为 pandas.DataFrame，必须含列:
    date, open, high, low, close, volume, p_change(涨跌幅%)

原版依赖 talib.MA → 已用 pandas rolling().mean() 替代（零 talib 依赖）。
"""

import numpy as np
import pandas as pd


def _ma(s: pd.Series, n: int) -> pd.Series:
    """简单移动平均（替代 talib.MA）"""
    return s.rolling(n).mean()


# ═══════════════ 1. 放量上涨 (enter.py check_volume) ═══════════════
def check_volume_breakout(df: pd.DataFrame, threshold: int = 60) -> bool:
    """放量上涨
    1. 当日涨幅 >= 2% 且 收盘 >= 开盘（收阳）
    2. 成交额 = 收盘价 × 成交量 >= 2 亿
    3. 量比 = 当日量 / 5日均量 >= 2
    """
    if len(df) < threshold:
        return False
    last = df.iloc[-1]
    if last['p_change'] < 2 or last['close'] < last['open']:
        return False
    vol_ma5 = _ma(df['volume'], 5).fillna(0.0)
    amount = last['close'] * last['volume']
    if amount < 200_000_000:  # 2亿
        return False
    mean_vol = vol_ma5.iloc[-2] if len(vol_ma5) >= 2 else 0
    if mean_vol <= 0:
        return False
    return (last['volume'] / mean_vol) >= 2


# ═══════════════ 2. 高紧旗形 (high_tight_flag.py) ═══════════════
def check_high_tight_flag(df: pd.DataFrame, istop: bool = False, threshold: int = 60) -> bool:
    """高而窄的旗形（欧奈尔 High Tight Flag）
    1. 必须在龙虎榜上有机构 (istop=True)
    2. 近24日高点 / 前24~10日最低价 >= 1.9
    3. 前24~10日必须连续两天涨幅 >= 9.5%
    """
    if not istop:
        return False
    if len(df) < threshold:
        return False
    data = df.tail(threshold).tail(24).head(14)
    if len(data) < 14:
        return False
    low = data['low'].min()
    if low <= 0:
        return False
    ratio = data['high'].max() / low
    if ratio < 1.9:
        return False
    prev = 0.0
    for p in data['p_change'].values:
        if p >= 9.5:
            if prev >= 9.5:
                return True
            prev = p
        else:
            prev = 0.0
    return False


# ═══════════════ 3. 停机坪 (parking_apron.py) ═══════════════
def check_parking_apron(df: pd.DataFrame, threshold: int = 15) -> bool:
    """停机坪（涨停后高位横盘整理）
    1. 最近15日有涨停(>9.5%)且放量上涨
    2. 涨停后连续3日: 高开 + 收盘上涨 + 收盘/开盘在 0.97~1.03
       且第2-3日涨跌幅在 -5%~5%，收盘价持续高于涨停价
    """
    if len(df) < threshold + 3:
        return False
    data = df.tail(threshold + 3).reset_index(drop=True)
    # 找涨停日
    for i in range(len(data) - 3):
        row = data.iloc[i]
        if row['p_change'] > 9.5:
            limit_price = row['close']
            # 涨停日必须放量上涨（用截至该日的数据检查）
            sub = data.iloc[:i + 1]
            if len(sub) < 5:
                continue
            # 简化放量确认：涨停日量 > 前5日均量 × 2
            if sub['volume'].iloc[-1] < sub['volume'].iloc[:-1].tail(5).mean() * 2:
                continue
            # 后续3日
            d1 = data.iloc[i + 1]
            d23 = data.iloc[i + 2:i + 4]
            if len(d23) < 2:
                continue
            if not (d1['close'] > limit_price and d1['open'] > limit_price
                    and 0.97 < d1['close'] / d1['open'] < 1.03):
                continue
            ok = True
            for _, d in d23.iterrows():
                if not (0.97 < d['close'] / d['open'] < 1.03 and -5 < d['p_change'] < 5
                        and d['close'] > limit_price and d['open'] > limit_price):
                    ok = False
                    break
            if ok:
                return True
    return False


# ═══════════════ 4. 海龟突破 (turtle_trade.py) ═══════════════
def check_turtle_breakout(df: pd.DataFrame, threshold: int = 60) -> bool:
    """海龟交易法则入场：当日收盘价 >= 最近60日最高收盘价"""
    if len(df) < threshold:
        return False
    data = df.tail(threshold)
    return data['close'].iloc[-1] >= data['close'].max()


# ═══════════════ 5. 平台突破 (breakthrough_platform.py) ═══════════════
def check_breakthrough_platform(df: pd.DataFrame, threshold: int = 60) -> bool:
    """平台突破
    1. 60日内某日 开盘 < MA60 <= 收盘（突破60日线）且放量上涨
    2. 突破前所有交易日收盘价与MA60偏离在 -5% ~ +20% 之间
    """
    if len(df) < threshold + 60:
        return False
    data = df.tail(threshold + 60).reset_index(drop=True)
    data['ma60'] = _ma(data['close'], 60).fillna(0.0)
    breakthrough_idx = None
    for i in range(len(data)):
        row = data.iloc[i]
        if row['open'] < row['ma60'] <= row['close']:
            # 放量上涨确认（截至该日）
            sub = data.iloc[:i + 1]
            if len(sub) >= 5:
                vol_ratio = sub['volume'].iloc[-1] / max(sub['volume'].iloc[:-1].tail(5).mean(), 1e-9)
                if vol_ratio >= 2:
                    breakthrough_idx = i
                    break
    if breakthrough_idx is None:
        return False
    front = data.iloc[:breakthrough_idx]
    front = front[front['ma60'] > 0]
    if front.empty:
        return False
    for _, row in front.iterrows():
        if not (-0.05 < (row['ma60'] - row['close']) / row['ma60'] < 0.2):
            return False
    return True


# ═══════════════ 6. 放量跌停 (climax_limitdown.py) ═══════════════
def check_climax_limitdown(df: pd.DataFrame, threshold: int = 60) -> bool:
    """放量跌停（恐慌底部 / 派发确认）
    1. 跌幅 <= -9.5%
    2. 成交额 >= 2 亿
    3. 量比 >= 4（放量恐慌）
    """
    if len(df) < threshold:
        return False
    last = df.iloc[-1]
    if last['p_change'] > -9.5:
        return False
    vol_ma5 = _ma(df['volume'], 5).fillna(0.0)
    amount = last['close'] * last['volume']
    if amount < 200_000_000:
        return False
    mean_vol = vol_ma5.iloc[-2] if len(vol_ma5) >= 2 else 0
    if mean_vol <= 0:
        return False
    return (last['volume'] / mean_vol) >= 4


# ═══════════════ 7. 持续上涨 (keep_increasing.py) ═══════════════
def check_keep_increasing(df: pd.DataFrame, threshold: int = 30) -> bool:
    """持续上涨（MA30 多头且加速）
    MA30[0] < MA30[10] < MA30[20] < MA30[29] 且 MA30[29] > 1.2 × MA30[0]
    """
    if len(df) < threshold:
        return False
    data = df.tail(threshold).reset_index(drop=True)
    ma30 = _ma(data['close'], 30).fillna(0.0).values
    if ma30[0] <= 0:
        return False
    step1 = round(threshold / 3)
    step2 = round(threshold * 2 / 3)
    return (ma30[0] < ma30[step1] < ma30[step2] < ma30[-1]
            and ma30[-1] > 1.2 * ma30[0])


# ═══════════════ 8. 低ATR成长 (low_atr.py) ═══════════════
def check_low_atr(df: pd.DataFrame, ma_long: int = 250, threshold: int = 10) -> bool:
    """低波动稳步上涨（低ATR）
    1. 至少250日数据
    2. 近10日平均|涨跌幅|(ATR代理) < 10%
    3. 近10日高低价差 / 最低价 > 1.1（有一定涨幅）
    """
    if len(df) < ma_long:
        return False
    data = df.tail(threshold)
    if len(data) < threshold:
        return False
    atr = data['p_change'].abs().mean()
    if atr > 10:
        return False
    high = data['close'].max()
    low = data['close'].min()
    if low <= 0:
        return False
    return (high - low) / low > 1.1


# ═══════════════ 9. 无大幅回撤 (low_backtrace_increase.py) ═══════════════
def check_low_backtrace_increase(df: pd.DataFrame, threshold: int = 60) -> bool:
    """稳步上涨无大幅回撤
    1. 60日涨幅 >= 60%
    2. 期间无: 单日跌7% / 高开低走7% / 两日累计跌10% / 两日高开低走跌10%
    """
    if len(df) < threshold:
        return False
    data = df.tail(threshold).reset_index(drop=True)
    ratio = (data['close'].iloc[-1] - data['close'].iloc[0]) / data['close'].iloc[0]
    if ratio < 0.6:
        return False
    prev_p = 100.0
    prev_open = -1e6
    for _, row in data.iterrows():
        p = row['p_change']
        o = row['open']
        c = row['close']
        if p < -7 or (c - o) / o * 100 < -7 \
                or prev_p + p < -10 \
                or (c - prev_open) / prev_open * 100 < -10:
            return False
        prev_p = p
        prev_open = o
    return True


# ═══════════════ 10. 回踩年线 (backtrace_ma250.py) ═══════════════
def check_backtrace_ma250(df: pd.DataFrame, threshold: int = 60) -> bool:
    """回踩年线（250日线）缩量企稳
    1. 前段: 从年线下方突破到年线上方
    2. 后段: 年线上运行，最低价日距最高价日 10~50 日
    3. 回踩缩量: 最高量/最低量 > 2 且 最低价/最高价 < 0.8
    """
    if len(df) < 250:
        return False
    data = df.tail(threshold + 250).reset_index(drop=True)
    data['ma250'] = _ma(data['close'], 250).fillna(0.0)
    data = data.tail(threshold).reset_index(drop=True)

    high_idx = data['close'].idxmax()
    highest = data.loc[high_idx]
    front = data.loc[:high_idx]
    back = data.loc[high_idx:]

    if front.empty or back.empty:
        return False
    if not (front['close'].iloc[0] < front['ma250'].iloc[0]
            and front['close'].iloc[-1] > front['ma250'].iloc[-1]):
        return False

    recent_low_idx = back['close'].idxmin()
    recent_lowest = back.loc[recent_low_idx]
    if back['close'].min() < back['ma250'].min():
        return False

    day_diff = (recent_lowest['date'] - highest['date']).days
    if not (10 <= day_diff <= 50):
        return False

    vol_ratio = highest['volume'] / recent_lowest['volume']
    back_ratio = recent_lowest['close'] / highest['close']
    return vol_ratio > 2 and back_ratio < 0.8


# ═══════════════ 组合扫描 ═══════════════
STRATEGIES = {
    '放量上涨': check_volume_breakout,
    '高紧旗形': check_high_tight_flag,
    '停机坪': check_parking_apron,
    '海龟突破': check_turtle_breakout,
    '平台突破': check_breakthrough_platform,
    '放量跌停': check_climax_limitdown,
    '持续上涨': check_keep_increasing,
    '低ATR成长': check_low_atr,
    '无大幅回撤': check_low_backtrace_increase,
    '回踩年线': check_backtrace_ma250,
}


def scan_all(df: pd.DataFrame) -> dict:
    """扫描全部10个形态，返回 {策略名: bool}"""
    result = {}
    for name, fn in STRATEGIES.items():
        try:
            result[name] = bool(fn(df))
        except Exception:
            result[name] = False
    return result


if __name__ == '__main__':
    # 自测：构造模拟数据
    n = 300
    rng = np.random.default_rng(42)
    close = 10 + np.cumsum(rng.normal(0.05, 0.3, n))
    close = np.clip(close, 1, None)
    open_ = close + rng.normal(0, 0.2, n)
    high = np.maximum(open_, close) + abs(rng.normal(0, 0.3, n))
    low = np.minimum(open_, close) - abs(rng.normal(0, 0.3, n))
    vol = rng.integers(1000000, 5000000, n)
    p_change = np.diff(close, prepend=close[0]) / np.maximum(close, 1e-9) * 100
    dates = pd.date_range('2025-01-01', periods=n, freq='B')
    df = pd.DataFrame({'date': dates, 'open': open_, 'high': high, 'low': low,
                       'close': close, 'volume': vol, 'p_change': p_change})
    print('自测 scan_all 结果:')
    for k, v in scan_all(df).items():
        print(f'  {k:<12} {v}')
