# 指数级别分析工作流 (沪深300/上证50/中证500)

> 当用户要求分析指数本身（非个股）的买卖信号时使用。
> 覆盖：缠论结构 + 期货持仓 + 宏观 + 估值 + 技术指标 五维交叉。

## 数据采集顺序（并行优先）

### 块1: 实时行情 (腾讯 qt.gtimg.cn)
```python
url = 'http://qt.gtimg.cn/q=sh000300,sh000016,sh000905'
# p[2]=代码 p[3]=现价 p[32]=涨跌幅 p[4]=昨收
# p[5]=开盘 p[33]=最高 p[34]=最低 p[37]=成交额(万元)
```

### 块2: K线 + 缠论 (baostock + chan_engine)
```python
import baostock as bs
bs.login()
sym = 'sh.000300'
rs = bs.query_history_k_data_plus(sym, 'date,open,high,low,close,volume',
    start_date='2025-07-01', end_date=today, frequency='d', adjustflag='2')
# 将最后收盘价替换为实时价后跑chan.py
from chan_engine import analyze as chan_analyze
kline_list, has_signal, bsp_list, px, zs_str, pos = chan_analyze(D,O,C,H,L,'000300')
```

### 块3: 股指期货持仓 (CFFEX官方CSV)
```bash
url='http://www.cffex.com.cn/sj/ccpm/{YYYYMM}/{DD}/IF_1.csv'
# GBK编码 | 跳过前3行标题 | 持买单量在列[7], 持卖单量在列[10]
# 详见 references/cffex_direct_data.md
```

### 块4: 估值 (中证官方)
```python
import akshare as ak
df = ak.stock_zh_index_value_csindex(symbol='000300')
pe1 = df['市盈率1'].iloc[-1]    # 静态PE
pe2 = df['市盈率2'].iloc[-1]    # TTM PE
div_yield = df['股息率1'].iloc[-1]  # 股息率(%)
# 注意: 数据约T-3周延迟，需结合现价变化线性外推
```

### 块5: 宏观
```python
# 中美利差 (AKShare)
import akshare as ak
cb = ak.bond_zh_us_rate(start_date='20250601')
cn10 = float(cb['中国国债收益率10年'].iloc[-1])
us10 = float(cb['美国国债收益率10年'].iloc[-1])
spread = us10 - cn10

# DXY/VIX (yfinance, T+2延迟, 仅参考)
import yfinance as yf
dxy = yf.Ticker('DX-Y.NYB').history(period='5d')['Close'].iloc[-1]
vix = yf.Ticker('^VIX').history(period='5d')['Close'].iloc[-1]
```

### 块6: 技术指标（自算）
```python
# RSI(14), MACD(12/26), MA5/10/20/60/120
# 布林带(20,2), 斐波那契(90日范围)
# 成交量比(当日/20日均)
```

## 分析输出结构

```
## 🔬 {指数名} 全面分析

### 一、实时行情 [腾讯 qt.gtimg.cn]
### 二、缠论结构 [chan.py + baostock]
### 三、技术指标 [自算]
### 四、斐波那契 [自算]
### 五、股指期货持仓 [CFFEX官网CSV]
### 六、宏观环境 [AKShare + yfinance]
### 七、估值 [中证指数公司 stock_zh_index_value_csindex]
### 八、综合信号矩阵 [六维加权]
### 九、买卖信号总结 [方向+观察窗口+仓位建议]
```

## 信号权重（指数级别）

| 维度 | 权重 | 数据源 |
|------|------|--------|
| 缠论结构 | 30% | chan.py |
| 技术指标 | 20% | 自算 |
| 期货持仓 | 15% | CFFEX CSV |
| 宏观 | 15% | AKShare+yfinance |
| 估值 | 10% | 中证官方 |
| 位置/斐波那契 | 10% | 自算 |

## 关键判断规则

1. **中枢上方不追买** — 现价 > 中枢上沿 → 无安全边际
2. **期货多空比 < 0.95** → 主力偏空，降低多头仓位
3. **中美利差 > 2.5%** → 资本外流压力，A股权重承压
4. **跌破 Fib 0.618** → 回调升级，下看 0.5 回撤
5. **MA60 是否守住** → 中期趋势分界线
6. **PE + 股息率** → PE < 15 且有 2.5%+ 股息率 = 有底部支撑

## 2026-07-05 沪深300实战案例

| 维度 | 数值 | 信号 |
|------|------|------|
| 缠论 | 中枢4484-4720, 笔向上, 4842在中枢上方 | 🟡 无安全边际 |
| RSI | 38.8 | 🟡 偏弱 |
| 期货 | 净空24375手, 多空比0.89 | 🔴 主力偏空 |
| 中美利差 | 2.73% | 🔴 资本外流 |
| DXY | 100.86 (30日+1.33%) | 🟡 人民币承压 |
| PE | ~14.9静态 | 🟢 合理偏低 |
| 股息率 | ~2.72% | 🟢 有吸引力 |
| 位置 | 触及0.618回撤4808后反弹 | 🟡 支撑确认 |

**结论: ⚪ 观望** — 等4720-4800区间再评估做多。
