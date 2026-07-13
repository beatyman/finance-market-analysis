# 全功能扫描 Excel 输出模板 v1.0

## 脚本: csi300_full_scan.py (baostock批处理, ~180s/280只)

### 输出文件: /root/chan_hs300_full_YYYYMMDD.xlsx

### 三Sheet格式

**Sheet 1: 信号** (按基础型号+超频列)
- 21列: 代码/名称/现价/PE/YTD%/旧XGB/新XGB/3D分/等级/仓位%/R:R/中枢/中枢内/BSP/V4.5/GZK/买入/止损/TP1/风控/标签
- 排序: 中枢内买(绿) > 中枢内等信号(黄) > 中枢内Sell(红) > 其他
- 冻结A2, 自选筛选

**Sheet 2: 宏观**
- 市场指数/期指持仓/美债黄金/港股沽空/综合判断
- 单列文本, 分段标题用━

**Sheet 3: 综合推荐** (Top15)
- 17列: #/代码/名称/现价/旧XGB/新XGB/3D分/等级/仓位%/R:R/V4.5/GZK/中枢/买入/止损/TP1/逻辑
- 排序: _rank = 3D×0.5 + (XGB×0.3 if 中枢内) + (10 if V4.5≥8)
- 非买卖信号entry/stop/tp1显示"—"
- 前5行绿底

### 颜色规范
- 绿(E2EFDA): 中枢内买 / A级
- 黄(FFF2CC): 等信号
- 红(FCE4D6): Sell
- 蓝(2F5496): 表头

### 双XGBoost模型
- 旧: chan_xgb_56d.pkl (200树, 56维)
- 新: chan_xgb_300s.pkl (300树, 58维, 41K样本, AUC 0.717)
- 阈值: 新模型>25≈旧模型>50
