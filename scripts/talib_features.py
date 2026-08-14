#!/usr/bin/env python3
"""TA-Lib因子增强模块 — 为XGBoost训练添加技术指标因子"""
import numpy as np
import talib

def add_talib_features(closes, highs, lows, vols):
    """从OHLCV序列提取TA-Lib技术因子
    
    Args:
        closes/highs/lows/vols: list[float] 或 np.array
    
    Returns:
        dict: 因子名 -> float (最后一个bar的值)
    """
    c = np.asarray(closes, dtype=float)
    h = np.asarray(highs, dtype=float)
    l = np.asarray(lows, dtype=float)
    v = np.asarray(vols, dtype=float)
    f = {}
    n = len(c)
    
    def safe(fn, *args):
        try:
            r = fn(*args)
            r = np.asarray(r)
            return float(r[-1]) if len(r) > 0 and not np.isnan(r[-1]) else 0.0
        except:
            return 0.0
    
    # === 趋势类 ===
    f['adx_14'] = safe(talib.ADX, h, l, c, 14)
    f['adxr_14'] = safe(talib.ADXR, h, l, c, 14)
    f['plus_di_14'] = safe(talib.PLUS_DI, h, l, c, 14)
    f['minus_di_14'] = safe(talib.MINUS_DI, h, l, c, 14)
    f['aroon_up_25'] = safe(talib.AROONOSC, h, l, 25)
    f['cci_14'] = safe(talib.CCI, h, l, c, 14)
    f['dx_14'] = safe(talib.DX, h, l, c, 14)
    f['mom_10'] = safe(talib.MOM, c, 10)
    f['roc_10'] = safe(talib.ROC, c, 10)
    
    # === 动量类 ===
    f['stoch_k'], _ = talib.STOCH(h, l, c) if len(talib.STOCH(h,l,c))==2 else (0.0,0.0)
    f['stoch_k'] = float(np.asarray(f['stoch_k'])[-1]) if isinstance(f['stoch_k'],np.ndarray) else (float(f['stoch_k'][-1]) if hasattr(f['stoch_k'],'__len__') else 0.0)
    f['willr_14'] = safe(talib.WILLR, h, l, c, 14)
    f['mfi_14'] = safe(talib.MFI, h, l, c, v, 14)
    f['trix_30'] = safe(talib.TRIX, c, 30)
    f['ultosc'] = safe(talib.ULTOSC, h, l, c, 7, 14, 28)
    f['ppo'] = safe(talib.PPO, c, 12, 26, 0)
    
    # === 波动率类 ===
    f['natr_14'] = safe(talib.NATR, h, l, c, 14)
    f['trange'] = safe(talib.TRANGE, h, l, c)
    f['atr_14'] = safe(talib.ATR, h, l, c, 14)
    
    # === 成交量类 ===
    f['ad'] = safe(talib.AD, h, l, c, v)
    f['adosc'] = safe(talib.ADOSC, h, l, c, v, 3, 10)
    f['obv'] = safe(talib.OBV, c, v)
    f['obv_roc'] = 0.0
    obv_full = talib.OBV(c, v)
    if len(obv_full) > 5:
        f['obv_roc'] = float(obv_full[-1] - obv_full[-6]) / (abs(obv_full[-6]) + 1e-9)
    
    # === 均线类 ===
    f['sma_5'] = safe(talib.SMA, c, 5)
    f['sma_10'] = safe(talib.SMA, c, 10)
    f['sma_20'] = safe(talib.SMA, c, 20)
    f['sma_60'] = safe(talib.SMA, c, 60)
    f['ema_12'] = safe(talib.EMA, c, 12)
    f['ema_26'] = safe(talib.EMA, c, 26)
    f['wma_10'] = safe(talib.WMA, c, 10)
    f['kama_30'] = safe(talib.KAMA, c, 30)
    f['sar'] = safe(talib.SAR, h, l, 0.02, 0.2)
    
    # === 布林带 ===
    bb_upper, bb_mid, bb_lower = talib.BBANDS(c, 20, 2, 2, 0)
    f['bb_upper'] = safe(lambda: bb_upper)
    f['bb_mid'] = safe(lambda: bb_mid)
    f['bb_lower'] = safe(lambda: bb_lower)
    
    # === MACD ===
    macd, macd_signal, macd_hist = talib.MACD(c, 12, 26, 9)
    f['macd_ta'] = safe(lambda: macd)
    f['macd_signal_ta'] = safe(lambda: macd_signal)
    f['macd_hist_ta'] = safe(lambda: macd_hist)
    
    # === 价格位置 ===
    if n >= 20:
        hi20 = np.max(h[-20:]); lo20 = np.min(l[-20:])
        f['pos_20d'] = (c[-1] - lo20) / (hi20 - lo20 + 1e-9)
    if n >= 60:
        hi60 = np.max(h[-60:]); lo60 = np.min(l[-60:])
        f['pos_60d'] = (c[-1] - lo60) / (hi60 - lo60 + 1e-9)
    if n >= 250:
        hi250 = np.max(h[-250:]); lo250 = np.min(l[-250:])
        f['pos_250d'] = (c[-1] - lo250) / (hi250 - lo250 + 1e-9)
    
    # === 统计类 ===
    f['stddev_20'] = safe(talib.STDDEV, c, 20, 1.0)
    f['linearreg_slope'] = safe(talib.LINEARREG_SLOPE, c, 20)
    f['tsf_14'] = safe(talib.TSF, c, 14)
    
    return f


def get_talib_feature_names():
    """返回所有TA-Lib因子名(用于排序保持一致)"""
    c = np.random.rand(300) * 100 + 50
    h = c * 1.02; l = c * 0.98; v = np.random.rand(300) * 1e6
    return sorted(add_talib_features(c, h, l, v).keys())


if __name__ == '__main__':
    # 测试
    import numpy as np
    np.random.seed(42)
    c = np.cumsum(np.random.randn(300)) + 100
    h = c + abs(np.random.randn(300)); l = c - abs(np.random.randn(300))
    v = np.random.rand(300) * 1e6
    f = add_talib_features(c, h, l, v)
    print('TA-Lib因子数: {}'.format(len(f)))
    for k, val in list(f.items())[:10]:
        print('  {} = {:.4f}'.format(k, val))
