# 沪深300全量扫描 Excel 标准输出格式

## 文件命名

`/root/chan_hs300_full_YYYYMMDD.xlsx`

## Sheet结构

### Sheet1: 交易计划（17列）

| 列 | 字段 | 类型 | 说明 |
|----|------|------|------|
| A | 代码 | str | 6位数字 |
| B | 名称 | str | 来源 hs300_stocks.csv |
| C | 现价 | float | 腾讯实时价 |
| D | 年涨% | str | +XX.X% |
| E | XGBoost 58维 | int | 0-100 |
| F | 中枢 | str | "42~46,49~55" 逗号分隔 |
| G | 中枢内 | str | ✓ 或 ✗ |
| H | 笔方向 | str | 上/下/内/"" |
| I | BSP信号 | str | Buy/Sell/Hold |
| J | AI主线 | str | 🔥 或空 |
| K | 板块/主题 | str | 来源 hot_stocks.csv |
| L | 买入区 | float | 或 — |
| M | 止损 | float | 或 — |
| N | TP1 | float | 或 — |
| O | TP2 | float | 或 — |
| P | R:R | str | X.X 或 — |
| Q | 标签 | str | 分级标签 |

### Sheet2: AI主线（12列）

仅含 AI/机器人/光模块/算力/服务器/存储 等主线标的。

### Sheet3: 统计

含分类计数、XGBoost分布、阿娇标准、数据源、三花智控验证状态。

## 颜色编码

- 🟢 绿底(E2EFDA) = 🔥中枢内买(盘背)
- 🟡 黄底(FFF2CC) = 🟡中枢内等信号
- 🔴 红底(FCE4D6) = 🔴中枢内Sell
- 🔵 蓝底(D9E1F2) = 🟡中枢外买
- ⚪ 白底 = 其他

## 排序

优先级: 中枢内买 > 中枢内等信号 > 中枢外买 > 中枢上等回踩 > 中枢下等突破 > Sell
同级按XGBoost降序。

## 格式

- 表头: 蓝底(2F5496)白字宋体10pt
- 数据: 宋体9pt全细线边框
- 冻结A2 + 自动筛选
