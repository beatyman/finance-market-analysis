# CSI300 量价分析

## 方法

20日涨跌幅 × 20日均量/60日均量比 → 五分类：

| 分类 | 条件 | 含义 |
|------|------|------|
| 放量上涨 | p20>0, v20r>1.3 | 主力资金介入 |
| 缩量下跌 | p20<0, v20r<0.8 | 筑底/洗盘 |
| 量价均衡 | 0.8≤v20r≤1.3 | 方向不明 |
| 缩量上涨 | p20>0, v20r<0.8 | 动能衰减 |
| 放量下跌 | p20<0, v20r>1.3 | 出货信号 |

## 代码

```python
import baostock as bs, numpy as np
bs.login()
rs = bs.query_history_k_data_plus(code, 'date,close,volume', 
    start_date='2026-03-01', end_date='2026-07-13', frequency='d', adjustflag='2')
rows = [rs.get_row_data() for _ in iter(lambda: rs.next(), None) if rs.error_code=='0']
c, v = np.array([float(r[1]) for r in rows]), np.array([float(r[2]) for r in rows])
p20 = (c[-1] - c[-21]) / c[-21] * 100
v20r = v[-20:].mean() / v[-60:-20].mean()
# → classify
bs.logout()
```

## 2026-07-13 CSSI300 结论

- 297只标的，系统性回调，放量上涨罕见(市场无主力入场)
- 中枢内买(18只)中仅中信证券1只放量上涨
- 持仓: 江铜放量下跌(-7.1% 1.3x), 铜陵缩量阴跌(-17.5%), 安克缩量下跌(-6.3%)
