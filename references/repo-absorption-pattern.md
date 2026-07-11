# 仓库吸收模式 — 2026-07-10 最佳实践

本次会话吸收 4 个 GitHub 仓库 + 7 个本地仓库 → 产出 6 个新模块。

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
- **不重复**: 已有功能（如chan_engine.py的背驰）不再吸收同类实现
- **轻量级**: 每个模块 < 70 行，放入 enhanced_tools.py 的 Module 12-17

## 本轮吸收汇总

| 仓库 | 吸收 | 行数 |
|------|------|------|
| chanlunStockAnalysis (JeffreyCaicai) | 北向资金 (东财push2) | 60 |
| chanlunStockAnalysis | K线多源回退 (mootdx→腾讯) | 65 |
| chanlun-quant (kouweizhu) | 三维综合评分 | 55 |
| chanlun-quant | 风控过滤器 (ST检测) | 22 |
| yanwuyou/chanlun-stock-analyzer | MACD背驰6条件 | 68 |
| chanlun-trade-signal | 风控计划 (止损/仓位) | 63 |

## 不吸收的典型原因

- **前端可视化** (chanlun-kline): Canvas渲染, 非Python
- **GUI应用** (chanlun_quantify): 2023行Qt界面，非策略库
- **框架耦合** (structure_analyzer.py): pandas+多TF数据加载，太重
- **重复实现** (TRAE-User engine.py): 已有chan_engine.py

## 关键决策

1. **所有模块放入 enhanced_tools.py** — 单文件零依赖，非多文件包
2. **enhanced_tools.py 从1400行→1730行**: 已足够，后续考虑模块化
3. **三维评分权重硬编码**: 技术40%+基本30%+消息30%，不依赖config.yaml
4. **新模型阈值待校准**: 新XGB 300s 分数25-62 vs 旧模型50-85
