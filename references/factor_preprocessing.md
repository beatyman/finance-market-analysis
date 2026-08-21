# 因子预处理方法手册（吸收 AlphaPurify）

量化因子标准三段式管线：**winsorize(去极值) → neutralize(去风险暴露) → standardize(标准化)**

原版 AlphaPurify 提供 42 种方法（polars 实现）。本 skill 已吸收核心 13 种为纯函数 `scripts/factor_preprocess.py`（pandas/numpy/sklearn/scipy，零 polars 依赖）。完整方法清单见下，未吸收的可按需补全。

## 一、缩尾去极值 (winsorize) — 12 种

| 方法 | 算法 | 适用场景 | 已吸收 |
|---|---|---|---|
| mean_std | 均值 ± n×σ 裁剪 | 正态分布因子 | ✅ |
| mad | 中位数 ± n×MAD 裁剪 | 抗离群值（首选鲁棒方法） | ✅ |
| iqr | Q1−k×IQR ~ Q3+k×IQR | 偏态分布 | ✅ |
| quantile | 分位数裁剪（1%~99%） | 通用（当前训练管线用此） | ✅ |
| rolling_quantile | 滚动分位数裁剪（时序） | 时序因子 | — |
| boxcox_compress | Box-Cox 压缩 | 强偏态 | — |
| zscore | z 分数裁剪 | 正态 | — |
| rankgauss | RankGauss 分位数正态化 | 抗离群+正态化 | — |
| tanh | tanh 压缩 | 软压缩 | — |
| huber | Huber 回归裁剪 | 鲁棒回归 | — |
| ransac | RANSAC 回归清洗 | 大量离群值 | — |

## 二、中性化 (neutralize) — 15 种（去除市值/行业等风险暴露）

| 方法 | 算法 | 适用场景 | 已吸收 |
|---|---|---|---|
| multiOLS | 横截面 OLS 回归取残差 | **最常用**（去市值/行业） | ✅ |
| ridge | 岭回归 | 中性化变量共线性强 | ✅ |
| pca | 主成分回归 | 去系统性暴露（多风险因子） | ✅ |
| lasso | Lasso（L1稀疏） | 变量选择 | — |
| elasticnet | 弹性网 | 稀疏+共线兼顾 | — |
| polynomial | 多项式回归 | 非线性暴露 | — |
| kernelridge | 核岭回归 | 非线性 | — |
| huber | Huber 鲁棒回归 | 抗离群 | — |
| rank | Rank 回归 | 非参数 | — |
| theilsen | Theil-Sen 鲁棒回归 | 强鲁棒 | — |
| randomforest | 随机森林 | 非线性暴露 | — |
| GBDT | 梯度提升树 | 非线性暴露 | — |
| ICA | 独立成分分析 | 独立源分离 | — |
| bayesianridge | 贝叶斯岭回归 | 先验正则 | — |
| partialcorrelation | 偏相关 | 控制变量后相关性 | — |

## 三、标准化 (standardize) — 15 种

| 方法 | 算法 | 适用场景 | 已吸收 |
|---|---|---|---|
| zscore | (x−mean)/std | **最常用** | ✅ |
| robust_zscore | (x−median)/(1.4826×MAD) | 抗离群 | ✅ |
| rank | 排名百分位 0~1 | 非正态/抗离群 | ✅ |
| rank_gauss | 排名→逆正态CDF | 近似正态+保留秩 | ✅ |
| minmax | 0~1 归一化 | 有界特征 | ✅ |
| rolling | 滚动 z-score（时序） | 时序稳定 | — |
| rolling_robust | 滚动鲁棒 z-score | 时序+抗离群 | — |
| rolling_minmax | 滚动 min-max | 时序有界 | — |
| volatility_scaling | 波动率缩放（shift防前视） | 量价因子 | — |
| EWMA | 指数加权波动率缩放 | 时变波动 | — |
| normal_scores | 正态分数 | 秩→正态 | — |
| quantile_binning | 分位数分箱 | 离散化 | — |
| log_zscore | log变换→zscore | 对数正态 | — |
| boxcox | Box-Cox→zscore | 强偏态 | — |
| yeo_johnson | Yeo-Johnson→zscore | 含负值偏态 | — |

## 四、与现有训练管线的集成

现有 `train_production.py` 用 `Winsorization(1-99%)` + `Spearman冗余`。可升级为：

```python
from factor_preprocess import purify
# 训练特征净化（去市值/行业暴露 + 抗离群 + 正态化）
df = purify(df, 'factor', date_col='date',
            neutralizer_cols=['log_mktcap', 'log_turnover'],
            dummy_cols=['industry'],
            winsorize='mad', neutralize='ols', standardize='rank_gauss')
```

**推荐组合**：
- 横截面因子：`mad` 缩尾 + `ols` 中性化（去市值/行业）+ `rank_gauss` 标准化
- 量价因子：`quantile` 缩尾 + `rank` 标准化（量价非正态，rank 更稳）
- 趋势因子（缠论结构）：`quantile` 缩尾 + `zscore`（结构因子近正态）

**关键 Pitfall**：中性化必须在横截面（按交易日 groupby）做，不能在时间序列整体做（会引入前视偏差）。所有方法已按 `date_col` 横截面分组实现。

## 五、原版依赖说明

- AlphaPurify 依赖 polars（高性能），本 skill 吸收版用 pandas 重写（零 polars 依赖）
- 原版 FactorAnalyzer（IC/Rank IC + 多空分位数回测）、Exposures（收益归因）、Database（数据聚合）未吸收——用户已有 `train_production.py` 的 Rank IC 评估管线，功能重叠

## 六、实验结论（2026-08-21 — 横截面预处理对树模型有害）

在 `train_production.py`（CSI300 XGBoost 55维）上实测对比：

| 预处理方法 | AUC | Rank IC |
|---|---|---|
| 按列整体 1%-99% 缩尾（legacy） | **0.667** ✅ | — |
| 横截面 MAD 缩尾 | 0.5165 | 0.0261 |
| 横截面 quantile(1-99%) 缩尾 | 0.5108 | 0.0171 |
| 横截面 MAD + zscore 标准化 | 0.5074 | 0.0116 |

**结论**：横截面预处理（缩尾/标准化）对 XGBoost 树模型**有害**（AUC 从 0.667 降到 ~0.51）。

**原因**：树模型对单调变换不敏感；横截面分组统计（按交易日）破坏了特征的**绝对水平**与**时序一致性**——每个特征被重定义为"当天横截面相对值"，丢失了跨时间可比性。

**正确用法**：
- **树模型（XGBoost/LGBM）** → 用按列整体缩尾（legacy），**不要**横截面标准化/中性化
- **线性模型 / IC 计算 / 因子中性化** → 横截面预处理是标准步骤（去市值/行业暴露 + zscore 是线性回归和 Rank IC 的前提）

`train_production.py` 已集成开关：`PURIFY_WINSORIZE=None` 默认走 legacy（最优），配置 `'mad'/'quantile'` 切换横截面（供线性模型实验）。
