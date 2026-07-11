# 沪深300 综合分析工作流

> 一次性完成缠论/期货/估值/宏观/技术五维分析，输出统一买卖信号矩阵。

## 数据采集顺序（建议并行4路）

```
第1路: 腾讯实时行情 → qt.gtimg.cn/q=sh000300,sh000016,sh000905
第2路: baostock K线 → query_history_k_data_plus('sh.000300', 1年日线)
第3路: CFFEX IF期货 → http://www.cffex.com.cn/sj/ccpm/{YYYYMM}/{DD}/IF_1.csv
第4路: 宏观+估值并行
  - 中证估值: ak.stock_zh_index_value_csindex(symbol='000300')
  - 中美利差: ak.bond_zh_us_rate(start_date='20250701')
  - DXY/VIX/US10Y: yfinance (T+2延迟，仅做背景)
  - 北向资金: push2.eastmoney.com (kamt.kline)
```

## 六维分析矩阵

| 维度 | 数据源 | 权重 | 关键判断 |
|------|--------|------|---------|
| 📈 缠论 | chan.py (baostock K线+腾讯现价) | 30% | 中枢位置/笔方向/BSP信号 |
| 📊 技术 | 自算(MA/RSI/MACD/布林/量比/Fib) | 20% | 死叉/金叉/超买超卖 |
| 🐋 期货 | CFFEX IF_1.csv | 15% | 多空比/席位变动方向 |
| 🌍 宏观 | AKShare+yfinance | 15% | 中美利差阈值2.5%/DXY方向 |
| 💰 估值 | 中证官方PE/股息率 | 10% | PE分位/股债性价比 |
| 🔍 位置 | Fib回撤+均线 | 10% | 0.618支撑/MA60防守 |

## 买卖信号逻辑

```
做多条件(≥3项满足):
  □ 中枢内/中枢上三买 + 笔向上
  □ 期货多空比>1.0
  □ 中美利差<2.5%
  □ PE分位<50%
  □ MA60支撑有效

做空条件(≥3项满足):
  □ 中枢上方一卖 + 笔向下
  □ 期货多空比<0.9
  □ 中美利差>2.5%
  □ 跌破Fib 0.618
  □ MA5/10死叉

否则: ⚪ 观望
```

## 输出模板

见主 SKILL.md 的日报模板。分析报告需包含:
1. 实时行情快照（含涨跌/成交额/日内高低）
2. K线统计（YTD/5日/20日/60日/90日高低）
3. 缠论结构（中枢/笔方向/BSP/位置）
4. 技术指标表（均线/RSI/MACD/布林/量比）
5. 斐波那契表（90日范围，标注关键位突破/触及）
6. CFFEX期货持仓（多空合计/净持仓/多空比/Top5变动）
7. 宏观数据表（中美利差/DXY/VIX）
8. 估值表（PE静态/TTM/股息率/分位）
9. 综合信号矩阵（六维加权方向）
10. 买卖信号总结（不买/不卖理由 + 观察窗口 + 仓位建议）

## 数据源清单（报告末尾必附）

```markdown
**数据源清单**:
- 实时行情: 腾讯 qt.gtimg.cn（0延迟）
- K线: baostock（日终复权）
- 缠论: chan.py BSP分析
- 期货: CFFEX官网 cffex.com.cn/sj/ccpm CSV
- 估值: 中证指数公司 stock_zh_index_value_csindex
- 宏观: AKShare（中美利差）+ Yahoo Finance（DXY/VIX/US10Y, T+2延迟）
```
