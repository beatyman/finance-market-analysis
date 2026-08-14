# Qlib Alpha360 因子库

> **来源**: Microsoft Qlib — `qlib.contrib.data.handler.Alpha360`
> **因子总数**: 360个（6个字段组 × 60个时间步）
> **数据字段**: `$close`, `$open`, `$high`, `$low`, `$vwap`, `$volume`
> **表达式语法**: Qlib Expression Engine DSL
> **设计理念**: 用过去60个交易日的原始价量数据构造归一化时序特征，直接输入机器学习模型

---

## 概述

Alpha360 不同于 Alpha158 的"人工设计指标"思路，它采用**原始特征工程**方法：将过去60个交易日（d=59到d=0）的6个价量字段直接作为特征，通过归一化消除量纲差异，让机器学习模型自行发现模式。

### 核心设计

| 维度 | 说明 |
|------|------|
| **字段数** | 6个（CLOSE, OPEN, HIGH, LOW, VWAP, VOLUME） |
| **时间窗口** | 60天（Ref=59 到 Ref=0，即今天到59天前） |
| **归一化** | 价格类除以当日收盘价，成交量类除以当日成交量 |
| **总特征数** | 6 × 60 = 360 |
| **命名规则** | `{FIELD}_{d}`，如 `CLOSE_0` 表示当日收盘价归一化值 |

### 归一化规则

| 字段类型 | 归一化公式 | 目的 |
|----------|-----------|------|
| 价格类（CLOSE/OPEN/HIGH/LOW/VWAP） | `Ref($field, d) / $close` | 消除股价绝对值差异，转化为相对比率 |
| 成交量类（VOLUME） | `Ref($volume, d) / ($volume + 1e-12)` | 消除成交量绝对值差异，`1e-12`防除零 |

---

## 一、CLOSE 组（60个） — 收盘价相对序列

捕捉过去60天收盘价相对于当日收盘价的变化轨迹，本质是**多尺度收益率序列**。

### 生成规则

```
CLOSE_d = Ref($close, d) / $close    （d = 0, 1, 2, ..., 59）
```

### 因子列表

| 因子名 | 表达式 | 语义 |
|--------|--------|------|
| CLOSE_0 | `$close / $close` | 恒为1，作为基准锚点 |
| CLOSE_1 | `Ref($close, 1) / $close` | 1日前收盘价/今日收盘价，≈ 1/(1+日收益率) |
| CLOSE_2 | `Ref($close, 2) / $close` | 2日前收盘价相对比 |
| CLOSE_3 | `Ref($close, 3) / $close` | 3日收盘价相对比 |
| CLOSE_5 | `Ref($close, 5) / $close` | 周级别价格变化 |
| CLOSE_10 | `Ref($close, 10) / $close` | 双周级别价格变化 |
| CLOSE_20 | `Ref($close, 20) / $close` | 月级别价格变化 |
| CLOSE_40 | `Ref($close, 40) / $close` | 双月级别价格变化 |
| CLOSE_59 | `Ref($close, 59) / $close` | 季度级别价格变化 |

> **完整列表**: CLOSE_0 至 CLOSE_59，共60个因子，d从0到59逐一生成。

### 分类与使用建议

- **分类**: 动量 / 均值回复
- **语义**: CLOSE_d > 1 表示d天前价格高于今天（价格下跌），< 1 表示上涨
- **使用建议**: 
  - 短期（d=1~5）：捕捉日内动量和短期反转
  - 中期（d=5~20）：捕捉周级别趋势
  - 长期（d=20~59）：捕捉月度/季度趋势
  - 整体序列可被LSTM/Transformer等时序模型有效利用

---

## 二、OPEN 组（60个） — 开盘价相对序列

捕捉过去60天开盘价相对于当日收盘价的变化，反映**隔夜跳空和开盘情绪**。

### 生成规则

```
OPEN_d = Ref($open, d) / $close    （d = 0, 1, 2, ..., 59）
```

### 因子列表

| 因子名 | 表达式 | 语义 |
|--------|--------|------|
| OPEN_0 | `$open / $close` | 今日开盘价/收盘价，反映日内涨跌 |
| OPEN_1 | `Ref($open, 1) / $close` | 昨日开盘价相对比 |
| OPEN_5 | `Ref($open, 5) / $close` | 周前开盘价相对比 |
| OPEN_20 | `Ref($open, 20) / $close` | 月前开盘价相对比 |
| OPEN_59 | `Ref($open, 59) / $close` | 季度前开盘价相对比 |

> **完整列表**: OPEN_0 至 OPEN_59，共60个因子。

### 分类与使用建议

- **分类**: 微观结构 / 动量
- **语义**: OPEN_0 < 1 表示今日收阳（开盘低于收盘），> 1 表示收阴
- **使用建议**:
  - OPEN_0 是日内多空强度的直接度量
  - OPEN_d - CLOSE_d 隐含了第d天的日内涨跌幅
  - 配合CLOSE组使用可解耦"隔夜跳空"与"日内波动"两个维度

---

## 三、HIGH 组（60个） — 最高价相对序列

捕捉过去60天最高价相对于当日收盘价的变化，反映**上方压力和突破潜力**。

### 生成规则

```
HIGH_d = Ref($high, d) / $close    （d = 0, 1, 2, ..., 59）
```

### 因子列表

| 因子名 | 表达式 | 语义 |
|--------|--------|------|
| HIGH_0 | `$high / $close` | 今日最高价/收盘价，反映上影线长度 |
| HIGH_1 | `Ref($high, 1) / $close` | 昨日最高价相对比 |
| HIGH_5 | `Ref($high, 5) / $close` | 周前最高价相对比 |
| HIGH_20 | `Ref($high, 20) / $close` | 月前最高价相对比 |
| HIGH_59 | `Ref($high, 59) / $close` | 季度前最高价相对比 |

> **完整列表**: HIGH_0 至 HIGH_59，共60个因子。

### 分类与使用建议

- **分类**: 波动率 / 形态
- **语义**: HIGH_0 - CLOSE_0 = 上影线比例，HIGH_0 - LOW_0 = 当日振幅
- **使用建议**:
  - HIGH_0 接近1表示收在最高价附近（强势）
  - 序列中的局部最大值可能代表历史阻力位
  - 配合LOW组计算各日振幅变化趋势

---

## 四、LOW 组（60个） — 最低价相对序列

捕捉过去60天最低价相对于当日收盘价的变化，反映**下方支撑和风险暴露**。

### 生成规则

```
LOW_d = Ref($low, d) / $close    （d = 0, 1, 2, ..., 59）
```

### 因子列表

| 因子名 | 表达式 | 语义 |
|--------|--------|------|
| LOW_0 | `$low / $close` | 今日最低价/收盘价，反映下影线长度 |
| LOW_1 | `Ref($low, 1) / $close` | 昨日最低价相对比 |
| LOW_5 | `Ref($low, 5) / $close` | 周前最低价相对比 |
| LOW_20 | `Ref($low, 20) / $close` | 月前最低价相对比 |
| LOW_59 | `Ref($low, 59) / $close` | 季度前最低价相对比 |

> **完整列表**: LOW_0 至 LOW_59，共60个因子。

### 分类与使用建议

- **分类**: 波动率 / 形态
- **语义**: CLOSE_0 - LOW_0 = 下影线比例（收盘价距最低价的距离）
- **使用建议**:
  - LOW_0 接近1表示收在最低价附近（弱势）
  - 序列中的局部最小值可能代表历史支撑位
  - HIGH_d - LOW_d 序列直接给出各日振幅的时序变化

---

## 五、VWAP 组（60个） — 成交量加权均价相对序列

捕捉过去60天VWAP相对于当日收盘价的变化，反映**机构资金成本和市场公允价格**。

### 生成规则

```
VWAP_d = Ref($vwap, d) / $close    （d = 0, 1, 2, ..., 59）
```

### 因子列表

| 因子名 | 表达式 | 语义 |
|--------|--------|------|
| VWAP_0 | `$vwap / $close` | 今日VWAP/收盘价，反映日内成交重心 |
| VWAP_1 | `Ref($vwap, 1) / $close` | 昨日VWAP相对比 |
| VWAP_5 | `Ref($vwap, 5) / $close` | 周前VWAP相对比 |
| VWAP_20 | `Ref($vwap, 20) / $close` | 月前VWAP相对比 |
| VWAP_59 | `Ref($vwap, 59) / $close` | 季度前VWAP相对比 |

> **完整列表**: VWAP_0 至 VWAP_59，共60个因子。

### 分类与使用建议

- **分类**: 量价关系 / 流动性
- **语义**: VWAP_0 > 1 表示今日均价高于收盘价（尾盘弱势抛压），< 1 表示尾盘拉升
- **使用建议**:
  - VWAP是机构交易的基准价格，偏离VWAP的程度反映机构持仓方向
  - VWAP_d 与 CLOSE_d 的差值反映第d天的成交重心偏移
  - 适合构建"机构资金流向"类衍生特征

---

## 六、VOLUME 组（60个） — 成交量相对序列

捕捉过去60天成交量相对于当日成交量的变化，反映**市场活跃度和资金参与度**。

### 生成规则

```
VOLUME_d = Ref($volume, d) / ($volume + 1e-12)    （d = 0, 1, 2, ..., 59）
```

> 注意：分母加 `1e-12` 防止除零错误（停牌日成交量为0）。

### 因子列表

| 因子名 | 表达式 | 语义 |
|--------|--------|------|
| VOLUME_0 | `$volume / ($volume + 1e-12)` | 恒接近1，作为基准锚点 |
| VOLUME_1 | `Ref($volume, 1) / ($volume + 1e-12)` | 昨日成交量/今日成交量 |
| VOLUME_5 | `Ref($volume, 5) / ($volume + 1e-12)` | 周前成交量相对比 |
| VOLUME_10 | `Ref($volume, 10) / ($volume + 1e-12)` | 双周成交量相对比 |
| VOLUME_20 | `Ref($volume, 20) / ($volume + 1e-12)` | 月前成交量相对比 |
| VOLUME_59 | `Ref($volume, 59) / ($volume + 1e-12)` | 季度前成交量相对比 |

> **完整列表**: VOLUME_0 至 VOLUME_59，共60个因子。

### 分类与使用建议

- **分类**: 流动性 / 量价关系
- **语义**: VOLUME_d > 1 表示第d天成交量大于今天（今日缩量），< 1 表示今日放量
- **使用建议**:
  - 成交量序列是捕捉"量价背离"的关键输入
  - 放量/缩量的模式由模型从序列中自动学习
  - VOLUME序列的方差反映成交量稳定性（高方差=间歇性放量）

---

## Qlib 配置模板

### DataHandlerLP 配置

```python
import qlib
from qlib.contrib.data.handler import Alpha360

# 初始化 Qlib
qlib.init(provider_uri="~/.qlib/qlib_data/cn_data")

# 使用 Alpha360 数据处理器
handler = Alpha360(
    instruments="csi300",
    start_time="2015-01-01",
    end_time="2023-12-31",
    fit_start_time="2015-01-01",
    fit_end_time="2020-12-31",
    infer_processors=[],     # 推理时的数据处理
    learn_processors=[],     # 训练时的数据处理
)

# 获取特征数据
data = handler.fetch()
```

### 自定义表达式生成（手动构建）

```python
# 价格类因子生成
fields = []
names = []
for field in ["$close", "$open", "$high", "$low", "$vwap"]:
    field_name = field[1:].upper()
    for d in range(60):
        if d == 0:
            expr = f"{field} / $close"
        else:
            expr = f"Ref({field}, {d}) / $close"
        fields.append(expr)
        names.append(f"{field_name}_{d}")

# 成交量因子生成
for d in range(60):
    if d == 0:
        expr = "$volume / ($volume + 1e-12)"
    else:
        expr = f"Ref($volume, {d}) / ($volume + 1e-12)"
    fields.append(expr)
    names.append(f"VOLUME_{d}")
```

---

## 汇总

| 字段组 | 因子数量 | 归一化基准 | 核心语义 | 适用模型 |
|--------|---------|-----------|---------|---------|
| CLOSE | 60 | 当日$close | 多尺度收益率序列 | LSTM, GRU, Transformer |
| OPEN | 60 | 当日$close | 隔夜跳空+日内方向 | LSTM, GRU, Transformer |
| HIGH | 60 | 当日$close | 上方压力+波动上界 | LSTM, GRU, Transformer |
| LOW | 60 | 当日$close | 下方支撑+波动下界 | LSTM, GRU, Transformer |
| VWAP | 60 | 当日$close | 机构成本+公允价格 | LSTM, GRU, Transformer |
| VOLUME | 60 | 当日$volume | 市场活跃度+资金参与 | LSTM, GRU, Transformer |
| **合计** | **360** | — | — | — |

### Alpha360 vs Alpha158 对比

| 维度 | Alpha158 | Alpha360 |
|------|----------|----------|
| 设计哲学 | 人工设计技术指标 | 原始特征+模型学习 |
| 因子解释性 | 高（每个因子有明确含义） | 低（依赖模型发现模式） |
| 适用模型 | 树模型（LightGBM/XGBoost） | 深度学习（LSTM/Transformer） |
| 特征数量 | 158 | 360 |
| 时间信息 | 通过窗口参数隐含 | 显式60天时序结构 |
| 扩展性 | 需手动设计新指标 | 增加字段或延长窗口即可扩展 |
| 最佳搭配 | 树模型 + 因子挖掘 | 时序深度学习模型 |
