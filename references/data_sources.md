# 数据源可用性 & 限制

## 服务器可用数据源 (已验证)

| 源 | 行情 | K线 | 板块 | 资金流向 |
|---|---|---|---|---|
| 腾讯 qt.gtimg.cn | ✅ 个股实时 | ✅ | ✅(个股涨跌推断) | ❌ |
| 腾讯 ifzq.gtimg.cn | — | ✅(需-L重定向) | ❌ | ❌ |
| yfinance | — | ✅(A/港/美/期货/宏观) | — | — |
| baostock | — | ✅(全量历史) | — | — |
| AKShare | ❌(部分) | ❌ | ❌ | ✅(仅CFFEX期货) |

## 不可用原因

服务器IP被 `push2.eastmoney.com` 封锁:
- TCP连接可达(0.0s延时)
- HTTP层拒绝: "Remote end closed connection without response"
- 影响范围: AKShare东财板块、tushare、同花顺、通达信全部被封
- 例外: 腾讯通过CDN, baostock独立服务器, yfinance走Yahoo

## 板块资金流向替代方案

1. **当前方案**: sector_heat.py 用腾讯个股行情推断板块平均涨跌
2. **完整方案**: Windows机器定时跑AKShare, CSV同步到服务器
3. **腾讯board/index接口**: 返回板块INDEX资金流(体量小, 仅盘中参考)

## K线数据源优先级

Tencent → yfinance → AKShare(K线) → baostock
- Tencent: 最快, 偶尔需要-L重定向
- yfinance: 对A股用.SS/.SZ后缀, 对港股用%04d.HK格式
- baostock: 最稳定但返回datetime.date对象(需str()转换)
- 自动截取最近250根K线(防止chan分析过深)

## yfinance多列索引坑

yfinance下载单只股票时DataFrame是多列索引:
```python
df['Close'].values  # 2D array → 需.ravel()
np.array(df['Close']).ravel()  # 正确
```

## AKShare CFFEX期货

可用的AKShare接口:
- `ak.get_cffex_rank_table()` — 股指期货持仓排名
- `ak.get_rank_sum_daily()` — 持仓变化趋势
- `ak.futures_foreign_commodity_realtime()` — COMEX实时行情
