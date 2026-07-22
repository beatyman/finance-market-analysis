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

## 9. 两日对比框架 (2026-07-14)

日报优先做两日对比，暴露趋势变化:

```
指数涨跌 + 期指持仓变化(增仓/减仓=多空方向) + 期权Gamma到期效应
+ 港股沽空 + CSI300中枢内买增减 + 核心持仓变动 + ETF动量排名
```

**期指对比**: IF/IC/IM/IH四大合约持仓变化。减仓+上涨=空头回补(short squeeze)，增仓+上涨=多头进场。

## 10. ETF动量输出规范 (2026-07-14)

**必须包含代码列**，标准格式:
```
代码        ETF        收盘    20日%   60日%  120日%   得分 趋势
sh.588200   科创芯片   4.400  +18.7  +66.2   +66.7   59.3  ✅
```

数据源: baostock (日常) 或 东方财富ulist (备用)
公式: score = r20d×0.15 + r60d×0.35 + r120d×0.50
门控: close>MA120 and r120d>0

## 6. 港股沽空数据 — HKEX官网 + 东方财富备用

**HKEX (主力)**: `https://www.hkex.com.hk/eng/stat/smstat/ssturnover/{YYYYMM}/ss_{YYYYMMDD}.htm`
注：7月数据URL路径可能变更，fallback到东方财富

**东方财富 (备用)**: `https://push2.eastmoney.com/api/qt/stock/get?secid=116.{code}&fields=f43,f170`

覆盖标的: 腾讯(00700)/美团(03690)/阿里(09988)/小米(01810)/快手(01024)

**脚本**: `scripts/hk_short.py`

```bash
python3 scripts/hk_short.py
```

数据源: `https://www.hkex.com.hk/eng/stat/smstat/ssturnover/{YYYYMM}/ss_{YYYYMMDD}.htm`

覆盖标的: 美团(3690)/腾讯(0700)/阿里(9988)/小米(1810)/快手(1024)

**脚本**: `scripts/hk_short.py` — curl+SOCKS5抓取HKEX每日沽空成交

## 7. 前瞻指引模板

## 11. X/Twitter 信息提取 (2026-07-16)

**必须用 curl + SOCKS5:**

```bash
curl -x socks5h://127.0.0.1:1080 -sL --max-time 10 \
  -H 'User-Agent: Mozilla/5.0' \
  'https://x.com/<user>/status/<tweet_id>' \
  2>/dev/null | grep -oP 'property="og:description"\s+content="\K[^"]+'
```

**原因**: Python urllib 不支持 SOCKS5 → 浏览器导航不支持代理 → 只用 curl + og:description 元数据提取。
图片无法通过 curl 提取，需手动描述或浏览器打开。

批量: `execute_code` + `subprocess.run(['curl','-x','socks5h://127.0.0.1:1080',...])`

## 12. 期指换月分析 (2026-07-16)

7月合约到期日(每月第三个周五)是换月关键节点。分析框架:

```
主力合约(07): 减仓/增仓 = 多空方向
次月合约(08): 增仓量 = 新资金进场强度
远月合约(09): 增仓 = 中长期趋势确认

净增仓 = 08增仓 + 09增仓 + 12增仓 - 07减仓
净增仓 > 0 → 多头进场
净增仓 < 0 → 资金离场

配合国债期货: 债市减仓+股市增仓 = 资金从债→股轮动
```

### 沪金/沪银 (东方财富 futures)
```python
# secids: 113.aum(沪金), 113.agm(沪银)
url = "https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=113.aum,113.agm&fields=f2,f3,f14"
```

### 有色金属 (东方财富 futures)
```python
# 沪铜/沪铝/沪锌/沪镍主连
url = "https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=113.cum,113.alm,113.znm,113.nim&fields=f2,f3,f14"
```

### 美股指数 (东方财富)
```python
# secids: 100.SPX(标普), 100.NDX(纳斯达克), 100.DJIA(道琼斯)
url = "https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=100.SPX,100.NDX,100.DJIA&fields=f2,f3,f14"
```

### 加密货币 (CoinGecko, 免费无需API Key)
```python
url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids=bitcoin,ethereum&price_change_percentage=24h"
```

**脚本**: `scripts/us_macro.py` 已整合上述数据源

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
