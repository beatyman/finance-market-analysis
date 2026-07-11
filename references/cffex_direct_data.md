# 中金所股指期货持仓 — 直接CSV数据源

## 官方URL格式

```
http://www.cffex.com.cn/sj/ccpm/{YYYYMM}/{DD}/IF_1.csv   # 沪深300
http://www.cffex.com.cn/sj/ccpm/{YYYYMM}/{DD}/IM_1.csv   # 中证1000
```

> 数据当日盘后发布（T日数据T日晚间可用）。可用实时数据替代AKShare的T-1延迟。

## CSV结构

```
交易日,合约,排名,成交量排名,,,持买单量排名,,,持卖单量排名,,
(sub-header) 会员简称,成交量,增减,会员简称,持买单量,增减,会员简称,持卖单量,增减
```

**解析注意:**
- 文件编码: GBK
- 实际数据从第4行开始（跳过标题行+表头行+子表头行）
- `持买单量`在列索引[7]，`持卖单量`在列索引[10]
- Top20席位默认排序

## 示例代码

```python
import csv,io,urllib.request

url = f'http://www.cffex.com.cn/sj/ccpm/202607/02/IF_1.csv'
raw = urllib.request.urlopen(url).read()
txt = raw.decode('gbk')
rows = list(csv.reader(io.StringIO(txt)))

buy = sell = 0
for r in rows[3:23]:  # skip headers, top20
    try:
        buy += int(r[7].replace(',',''))
        sell += int(r[10].replace(',',''))
    except: pass

print(f'IF Top20 多:{buy:,} 空:{sell:,} 净:{buy-sell:,}')
```

## vs AKShare

| 源 | 延迟 | 范围 | 可靠性 |
|---|---|---|---|
| CFFEX直接 | T日盘后 | Top20 | ✅ 官方 |
| AKShare | T-1(常有bug) | 全市场 | ⚠️ 不稳定 |

**建议**: daily_report.py优先用CFFEX直接CSV(当日盘后)，AKShare作回退。
