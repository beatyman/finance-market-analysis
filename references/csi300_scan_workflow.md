# 沪深300全量扫描流程

## 数据准备

1. 读取 `references/hs300_stocks.csv` → 300只成分股(代码+名称)
2. 腾讯 `qt.gtimg.cn` 实时行情(分批100只, ~3秒)
3. 读取 `references/hot_stocks.csv` → AI/科技主题映射

## 扫描步骤

### 1. 缠论分析 (chan_engine.py)
```python
cur, bsp_buy, bsp_types, px, zs_str, pos = chan_analyze(D, o, c, h, l, code)
# cur 是CKLine对象, 必须传给 extract_features 用于XGBoost
# 返回6个值, 不是7个
```

### 2. XGBoost 58维评分 (scorer.py)
```python
from scorer import extract_features, score_from_features
feats = extract_features(c, h, l, o, v, bsp_buy, bsp_types, cur)
# cur必须是CKLine对象, 传dict会导致静默失败(返回全0)
```

### 3. 阿娇过滤
- 年涨>100% + bsp_buy + 非三买 → 假二买, 标记⚠️
- 中枢内 + bsp_buy + 阿娇通过 → 🔥中枢内买(盘背)
- 中枢内 + 无信号 → 🟡等信号
- 中枢内 + Sell → 🔴Sell

### 4. 板块主题标注
- 读取 hot_stocks.csv 映射
- AI关键词: AI/算力/半导体/芯片/机器人/CPO/光模块/液冷/服务器/存储
- 手动补充: 300033→AI金融, 603019→AI服务器, 300124→机器人

### 5. 板块资金共振 (board_hot.py)
```python
from board_hot import get_board_flow
# 返回概念Top10 + 行业Top10 资金流入
```

## 输出格式

Excel: 15+列(代码/名称/现价/年涨/XGBoost/中枢/中枢内/笔方向/BSP/AI主线/板块主题/买入区/止损/TP1/TP2/R:R/标签)

排序: 中枢内买 > 等信号 > 中枢外买 > 等回踩 > Sell

颜色: 绿=中枢内买, 黄=等信号, 红=Sell, 蓝=中枢外买

## 常见错误

1. ❌ 凭记忆判断股票是否在沪深300 → ✅ 读hs300_stocks.csv
2. ❌ cur传dict给extract_features → ✅ 传chan_engine返回的CKLine对象
3. ❌ 忽略阿娇年涨>100%警告 → ✅ 标记⚠️
4. ❌ 扫300只超时 → ✅ 去掉TradeHelper加速(baostock逐只~1.6s)
