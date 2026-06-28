# Filecoin 扇区/订单过期查询 — 正确方法

> 2026-06-28 修正 | 数据库: /opt/chain-server/claims.db

## 表结构 (sectors vs claims — 两个独立概念)

### sectors 表 (扇区)
| 关键字段 | 类型 | 说明 |
|---|---|---|
| `sector_end` | TEXT | **扇区到期日期** (YYYY-MM-DD) ← 直接用 |
| `activation` | INTEGER | Filecoin epoch (30秒/epoch) |
| `expiration` | INTEGER | Filecoin epoch |
| `days_until_expiration` | INTEGER | 距到期天数 (预计算) |
| `active` | BOOLEAN | 是否活跃 |

### claims 表 (订单/交易)
| 关键字段 | 类型 | 说明 |
|---|---|---|
| `deal_end` | TEXT | **订单到期日期** (YYYY-MM-DD) ← 直接用 |
| `deal_start` | TEXT | 订单开始日期 |
| `expiration` | INTEGER | ⚠️ 订单持续epoch数, 不是Unix时间! |
| `term_min/max` | INTEGER | 最小/最大期限 (epoch) |

## Filecoin Epoch 转换

```python
GENESIS = datetime(2020, 10, 15, 14, 30, 0)  # Filecoin主网上线
real_date = GENESIS + timedelta(seconds=epoch * 30)
```

⚠️ `datetime(expiration, 'unixepoch')` 是错误的 — expiration是Filecoin epoch,不是Unix timestamp。

## 查询示例

```sql
-- 扇区按天分组
SELECT sector_end, COUNT(*) FROM sectors 
WHERE provider='f02826126' AND deleted_at IS NULL AND active=1
GROUP BY sector_end ORDER BY sector_end;

-- 订单按天分组
SELECT deal_end, COUNT(*) FROM claims 
WHERE provider='f02826126' AND deleted_at IS NULL
GROUP BY deal_end ORDER BY deal_end;
```

## 扇区激活日期分析

用 `activation` epoch 转换后按天分组, 计算中位数:

```python
cur.execute("SELECT activation, COUNT(*) FROM sectors WHERE provider=? AND deleted_at IS NULL AND active=1 GROUP BY 1 ORDER BY 1", (node,))
dates = [(GENESIS + timedelta(seconds=int(e)*30)).strftime('%Y-%m-%d'), c) for e,c in cur.fetchall()]
# 中位数: 展开为单天列表后取中间值
day_list = [d for d, cnt in dates for _ in range(cnt)]
median = sorted(day_list)[len(day_list)//2]
```
