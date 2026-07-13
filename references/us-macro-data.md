# 美股 + 美债宏观数据抓取 (2026-07-13)

## 1. 美债收益率曲线 — 美国财政部官网 (最权威)

```python
import subprocess as sp, re
from datetime import datetime

def fetch_treasury_yields(year='2026'):
    """获取最新美债收益率曲线 (1M~30Y)"""
    url = f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
    
    r = sp.run(['curl', '-x', 'socks5h://127.0.0.1:1080', '-sL', '--max-time', '15', url],
               stdout=sp.PIPE, timeout=20)
    raw = r.stdout.decode('utf-8', errors='ignore')
    
    entries = re.findall(r'<entry>(.*?)</entry>', raw, re.DOTALL)
    if not entries: return None
    
    latest = entries[-1]
    fields = {'1M': 'BC_1MONTH', '3M': 'BC_3MONTH', '6M': 'BC_6MONTH',
              '1Y': 'BC_1YEAR', '2Y': 'BC_2YEAR', '5Y': 'BC_5YEAR',
              '7Y': 'BC_7YEAR', '10Y': 'BC_10YEAR', '20Y': 'BC_20YEAR', '30Y': 'BC_30YEAR'}
    
    date_m = re.search(r'<d:NEW_DATE[^>]*>([^<]+)</d:NEW_DATE>', latest)
    result = {'date': date_m.group(1) if date_m else None}
    for short, full in fields.items():
        m = re.search(f'<d:{full}[^>]*>([^<]+)</d:{full}>', latest)
        if m: result[short] = float(m.group(1))
    
    # Compute 2s10s spread
    if '2Y' in result and '10Y' in result:
        result['2s10s'] = result['10Y'] - result['2Y']
    
    return result

# Example:
# yields = fetch_treasury_yields()
# print(f"10Y: {yields['10Y']}%, 2s10s: {yields['2s10s']:.0f}bp")
```

**数据字段**: 1M/3M/6M/1Y/2Y/5Y/7Y/10Y/20Y/30Y, date, 2s10s利差

## 2. 美股指数 + 半导体 — Yahoo Finance

```python
import subprocess as sp, json

def fetch_us_markets():
    """获取美股主要指数和AI半导体个股"""
    symbols = {
        '^GSPC': '标普500', '^IXIC': '纳斯达克', '^DJI': '道琼斯',
        '^SOX': '费城半导体', '^VIX': 'VIX恐慌',
        'NVDA': '英伟达', 'TSM': '台积电', 'AMD': 'AMD', 'AVGO': '博通',
        'DX-Y.NYB': 'DXY', 'GC=F': '黄金', 'HG=F': '铜', 'CL=F': '原油'
    }
    
    syms = ','.join(symbols.keys())
    r = sp.run(['curl', '-x', 'socks5h://127.0.0.1:1080', '-sL', '--max-time', '15',
                f'https://query1.finance.yahoo.com/v8/finance/chart/{syms}?interval=1d&range=2d'],
               stdout=sp.PIPE, timeout=20)
    
    try:
        d = json.loads(r.stdout)
        results = {}
        for result in d['chart']['result']:
            sym = result['meta']['symbol']
            name = symbols.get(sym, sym)
            quote = result['indicators']['quote'][0]
            closes = [c for c in quote['close'] if c is not None]
            if len(closes) >= 2:
                chg = (closes[-1]/closes[-2]-1)*100
                results[name] = {'close': closes[-1], 'chg%': round(chg, 2)}
        return results
    except: return None
```

## 3. 宏观经济全景 — 一站获取

```python
def macro_snapshot():
    """获取美股+美债+DXY+金属全景数据"""
    print('=== 美债 ===')
    yields = fetch_treasury_yields()
    if yields:
        print(f"  10Y: {yields.get('10Y','?')}%  2Y: {yields.get('2Y','?')}%  2s10s: {yields.get('2s10s','?'):.0f}bp")
    
    print('=== 美股 ===')
    mkts = fetch_us_markets()
    if mkts:
        for name in ['标普500','纳斯达克','道琼斯','费城半导体','VIX恐慌']:
            if name in mkts:
                print(f"  {name}: {mkts[name]['close']:.2f} {mkts[name]['chg%']:+.2f}%")
    
    print('=== AI/半导体 ===')
    if mkts:
        for name in ['英伟达','台积电','AMD','博通']:
            if name in mkts:
                print(f"  {name}: {mkts[name]['close']:.2f} {mkts[name]['chg%']:+.2f}%")
    
    print('=== 宏观 ===')
    if mkts:
        for name in ['DXY','黄金','铜','原油']:
            if name in mkts:
                print(f"  {name}: {mkts[name]['close']:.2f} {mkts[name]['chg%']:+.2f}%")
```

## 4. 前置条件

- SOCKS5代理 `socks5h://127.0.0.1:1080` 必须可用
- `curl` 必须安装
- Python 3.10+

## 5. 前瞻指引模板

```
美股XX收盘:
  半导体±X% → A股科技映射
  道琼斯±X% → 上证50映射
  10Y X.XX% → 压制/利好成长股
  2s10s Xbp → 衰退/正常信号
  VIX X.X → 波动率判断

A股前瞻:
  [方向判断]
  [铜/黄金影响]
  [策略调整]
```
