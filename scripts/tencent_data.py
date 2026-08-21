#!/usr/bin/env python3
"""A股历史K线数据源 — 新浪首选(单次4年) + 腾讯备选 + 本地缓存"""
import requests, json, time, os

_CACHE_DIR = '/tmp/kline_cache'
os.makedirs(_CACHE_DIR, exist_ok=True)

def fetch_kline_sina(code, datalen=1023):
    """新浪日线 — 单次请求最多1023根(约4年), 无分页
    
    Returns: (dates, opens, highs, lows, closes, vols)
    """
    symbol = ('sh' + code) if code.startswith('6') else ('sz' + code)
    url = 'https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData'
    try:
        r = requests.get(url, params={'symbol': symbol, 'scale': 240,
                                      'ma': 'no', 'datalen': datalen}, timeout=15)
        d = r.json()
        if not d:
            return [], [], [], [], [], []
        dates = [x['day'] for x in d]
        opens = [float(x['open']) for x in d]
        highs = [float(x['high']) for x in d]
        lows = [float(x['low']) for x in d]
        closes = [float(x['close']) for x in d]
        vols = [float(x['volume']) for x in d]
        return dates, opens, highs, lows, closes, vols
    except Exception:
        return [], [], [], [], [], []

def _today():
    from datetime import datetime
    return datetime.now().strftime('%Y-%m-%d')

def fetch_kline_tencent(code, start='2023-01-01', end=None):
    """腾讯历史K线(备选) — 本地缓存+自动分页"""
    end = end or _today()
    cache_file = os.path.join(_CACHE_DIR, '{}.json'.format(code))
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                cached = json.load(f)
            if cached.get('end') == end and len(cached.get('dates', [])) >= 200:
                return (cached['dates'], cached['opens'], cached['highs'],
                        cached['lows'], cached['closes'], cached['vols'])
        except:
            pass
    
    symbol = ('sh' + code) if code.startswith('6') else ('sz' + code)
    url = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
    all_rows = []
    cur_end = end
    for _ in range(3):
        params = {'param': '{},day,{},{},640,qfq'.format(symbol, start, cur_end)}
        try:
            r = requests.get(url, params=params, timeout=15)
            time.sleep(0.15)
            d = r.json()
            if d.get('code') != 0:
                break
            data = d.get('data', {}).get(symbol, {})
            klines = data.get('qfqday') or data.get('day') or []
            if not klines:
                break
            all_rows.extend(klines)
            earliest = klines[0][0]
            if earliest <= start or len(klines) < 640:
                break
            cur_end = earliest
        except Exception:
            break
    
    if not all_rows:
        return [], [], [], [], [], []
    seen = set()
    dedup = []
    for row in all_rows:
        if row[0] in seen: continue
        seen.add(row[0]); dedup.append(row)
    dedup.sort(key=lambda x: x[0])
    dedup = [r for r in dedup if start <= r[0] <= end]
    dates = [r[0] for r in dedup]
    opens = [float(r[1]) for r in dedup]
    closes = [float(r[2]) for r in dedup]
    highs = [float(r[3]) for r in dedup]
    lows = [float(r[4]) for r in dedup]
    vols = [float(r[5]) for r in dedup]
    if len(dates) >= 200:
        try:
            with open(cache_file, 'w') as f:
                json.dump({'end': end, 'dates': dates, 'opens': opens,
                           'highs': highs, 'lows': lows, 'closes': closes,
                           'vols': vols}, f)
        except:
            pass
    return dates, opens, highs, lows, closes, vols


def fetch_kline(code, start='2023-01-01', end=None):
    """统一数据源 — 新浪首选(缓存), 腾讯备选
    
    Returns: (dates, opens, highs, lows, closes, vols)
    """
    end = end or _today()
    # 本地缓存优先(仅当数据新鲜: 最新日期==end 或 缓存日期>=上一交易日)
    cache_file = os.path.join(_CACHE_DIR, '{}.json'.format(code))
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                cached = json.load(f)
            cdates = cached.get('dates', [])
            if len(cdates) >= 200 and cdates and cdates[-1] >= end:
                return (cached['dates'], cached['opens'], cached['highs'],
                        cached['lows'], cached['closes'], cached['vols'])
        except:
            pass
    
    # 新浪首选
    dates, opens, highs, lows, closes, vols = fetch_kline_sina(code)
    if len(dates) >= 200:
        # 过滤到[start, end]区间
        filtered = [(d, o, h, l, c, v) for d, o, h, l, c, v in
                    zip(dates, opens, highs, lows, closes, vols)
                    if start <= d <= end]
        if len(filtered) >= 200:
            dates = [x[0] for x in filtered]; opens = [x[1] for x in filtered]
            highs = [x[2] for x in filtered]; lows = [x[3] for x in filtered]
            closes = [x[4] for x in filtered]; vols = [x[5] for x in filtered]
            try:
                with open(cache_file, 'w') as f:
                    json.dump({'dates': dates, 'opens': opens, 'highs': highs,
                               'lows': lows, 'closes': closes, 'vols': vols}, f)
            except:
                pass
            return dates, opens, highs, lows, closes, vols
    
    # 腾讯备选
    return fetch_kline_tencent(code, start, end)


if __name__ == '__main__':
    dates, opens, highs, lows, closes, vols = fetch_kline('600019')
    print('宝钢: {}根K线'.format(len(dates)))
    if dates:
        print('范围: {} ~ {}'.format(dates[0], dates[-1]))
        print('最新: O={} H={} L={} C={} V={}'.format(
            opens[-1], highs[-1], lows[-1], closes[-1], vols[-1]))
        assert all(h >= l for h, l in zip(highs, lows)), 'high<low异常'
        print('OHLC校验通过')
