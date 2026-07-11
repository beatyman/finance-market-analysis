# 仓库吸收模式 + XGBoost训练 & 3D校准 — 2026-07-10 最终版

本次会话吸收 4 个 GitHub 仓库 + 7 个本地仓库 → 产出 6 个新模块 + 1个新XGBoost模型。

## 吸收流程

```
1. GitHub API 读 README (curl + base64 decode) → 判断价值
2. 有价值 → git clone --depth 1 (带 socks5 代理)
3. 扫描核心模块 (grep "^def " | wc -l)
4. 提取自包含函数 → 重写为 numpy 零依赖 → 放入 enhanced_tools.py
5. 测试验证 → commit + push
```

## 吸收原则

- **自包含优先**: 提取的函数不能有外部依赖（pandas/akshare等）
- **零依赖重写**: 源用pandas → 改用numpy；源用akshare → 改用东财直连curl
- **不重复**: 已有功能不吸收同类实现
- **轻量级**: 每个模块 < 70 行

## 本轮吸收汇总 (11仓库 → 6模块)

| 仓库 | 吸收 | enhanced_tools模块 |
|------|------|------|
| chanlunStockAnalysis | 北向资金+K线回退 | 12-13 |
| chanlun-quant | 三维评分+风控过滤 | 14-15 |
| yanwuyou/chanlun-stock-analyzer | MACD背驰6条件 | 16 |
| chanlun-trade-signal | 风控计划(止损/仓位) | 17 |
| chanlun-kline | (前端可视化) | — |
| 其余5个本地项目 | (GUI/框架耦合/重复实现) | — |

## XGBoost训练流水线

```python
# 训练参数
stocks: 300只沪深300 | 时段: 1年日线 | 时间点: t=100..N-5
标签: 前向5日收益>2% → 1 | 总样本: 41,459条 | 正样本: 28.8%
模型: 300棵树, max_depth=6, lr=0.05 | AUC: 0.717

# 断点续传
CHECKPOINT = '/tmp/xgb_train_samples.json'
每50只股票保存一次 → {X: [...], y: [...], last_idx: N}

# 输出
models/chan_xgb_300s.pkl (1.2MB)
models/chan_xgb_latest.pkl → chan_xgb_300s.pkl
```

## 三维评分校准

```
阈值: TECH_BUY=40 (原60) | FUND_HEAVY=55 (原70) | COMP_A=65 (原75)
fund_score = max(V4.5×2.5, GZK×1.5)
新旧模型对比: 新>25 ≈ 旧>50
→ 天赐材料3D=A但BSP=Sell → BSP优先级 > 3D评分
```

## 不吸收的典型原因

- **前端可视化** (chanlun-kline): Canvas渲染, 非Python
- **GUI应用** (chanlun_quantify): Qt界面，非策略库
- **框架耦合** (structure_analyzer): pandas+多TF，太重
- **重复实现** (TRAE-User): 已有chan_engine.py

## Excel输出规范 (用户纠正 2026-07-10)

```
三个Sheet必须全部存在:
1. 信号 — 原16列 + 新增5列(新XGB/3D分/等级/仓位%/风控)
2. 宏观 — 股指期货+美债+黄金+港股沽空+综合判断
3. 综合推荐 — Top15 + 逻辑
禁止删除宏观Sheet、减少列数、省略任何原有列
```
