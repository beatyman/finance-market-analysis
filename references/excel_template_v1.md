# 全功能扫描 Excel 生成模板 (v1.0 — 2026-07-10)

## 数据源
- 扫描结果: `/tmp/hs300_YYYYMMDD_full.json`（chan_engine + 双XGBoost + 三维评分）
- 宏观数据: 股指期货(IF/IC/IM/IH) + 美债(T/TF/TS) + COMEX黄金 + 港股沽空

## Excel 格式（强制三Sheet，不可删减）

### Sheet 1: 信号（信号Sheet名用当日日期如"7月10日信号"）

| 列 | 字段 | 说明 |
|----|------|------|
| 1 | 代码 | 6位数字 |
| 2 | 名称 | 股票中文名 |
| 3 | 现价 | 腾讯实时价 |
| 4 | PE | 市盈率 |
| 5 | YTD% | 年涨幅 |
| 6 | 旧XGB | 旧模型(56维) |
| 7 | 新XGB | 新模型(300s 58维 AUC 0.717) |
| 8 | 3D分 | 三维综合评分 |
| 9 | 等级 | A/B/C/D |
| 10 | 仓位% | 建议仓位 |
| 11 | R:R | 盈亏比 |
| 12 | 中枢 | 中枢区间字符串 |
| 13 | 中枢内 | Y/N |
| 14 | BSP | 缠论买卖点标签 |
| 15 | V4.5 | V4.5经验评分 |
| 16 | GZK | GZK评分 |
| 17 | 买入 | 建议买入价 |
| 18 | 止损 | 止损价 |
| 19 | TP1 | 第一目标 |
| 20 | 风控 | ST/OK |
| 21 | 标签 | 中枢内买/中枢内等信号/中枢内Sell等 |

排序: 中枢内买(绿色) -> 中枢内等信号(黄色) -> 中枢内Sell(红色) -> 其他, 同级按旧XGB降序
冻结: A2

### Sheet 2: 宏观

单列文本，包含:
- 市场指数 (上证/沪深300子指数)
- 股指期货 (多空持仓/净变化)
- 美债/美元/黄金 (收益率/DXY/COMEX)
- 港股沽空 (5只核心标的)
- 综合判断 (方向+持仓建议)
- 今日扫描统计

### Sheet 3: 综合推荐

| 列 | 字段 |
|----|------|
| 1 | # |
| 2 | 代码 |
| 3 | 名称 |
| 4 | 现价 |
| 5 | 旧XGB |
| 6 | 新XGB |
| 7 | 3D分 |
| 8 | 等级 |
| 9 | 仓位% |
| 10 | R:R |
| 11 | V4.5 |
| 12 | GZK |
| 13 | 中枢 |
| 14 | 买入 |
| 15 | 止损 |
| 16 | TP1 |
| 17 | 逻辑 |

排序: _rank = 3D分×0.5 + (旧XGB×0.3 if 中枢内 else 0) + (10 if V4.5≥8 else 0)
取Top15，前5行绿底

### 阿娇二次筛选（Critical — 2026-07-11）

综合推荐的Top15并非全部可操作。生成报告后**必须**按阿娇标准二次筛选：
1. 中枢内 + Buy信号 → ✅ 可操作
2. 中枢内 + Sell → 🔴 排除（天赐材料3D=A但BSP=Sell，矛盾）
3. 中枢内 + Hold/等信号 → 🟡 观察
4. 中枢外(无论BSP) → ❌ 排除
5. YTD>100%+非三买 → ⚠️ R4否决

**教训**: 天齐锂业(3D=75 A级)中枢外、赣锋锂业无中枢 — 高评分≠可操作。BSP优先级 > 3D评分。

## 生成命令

```bash
cd /root/.hermes/skills/a-share-market-analysis/scripts

# 日常扫描（推荐 — baostock共享连接，2-3分钟）
python3 csi300_full_scan.py
# 输出: /root/chan_hs300_full_YYYYMMDD.xlsx（三Sheet: 信号/宏观/综合推荐）

# 旧版手动生成
python3 << 'XEOF'
import json, openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
import sys; sys.path.insert(0,'.')
from enhanced_tools import compute_3d_score

with open('/tmp/hs300_YYYYMMDD_full.json') as f: results = json.load(f)

# 3D评分 (fund_score = max(V4.5×2.5, GZK×1.5))
for r in results:
    fund = max(r.get('v45s',0)*2.5, r.get('gzk',0)*1.5)
    s3d = compute_3d_score(r.get('old_xgb',0), fund_score=fund)
    r['s3d'] = s3d['composite']; r['grade'] = s3d['grade']; r['position'] = s3d['position']

# 排序: 中枢内买 > 等信号 > Sell > 其他
def skey(r):
    lab=r.get('label','')
    if '中枢内买' in lab and '否决' not in lab: return 0
    if '中枢内等信号' in lab: return 1
    if 'Sell' in lab: return 2
    return 3
results.sort(key=lambda r:(skey(r),-r.get('old_xgb',0)))

wb=openpyxl.Workbook()
hfont=Font(name='宋体',size=10,bold=True,color='FFFFFF')
hfill=PatternFill(start_color='2F5496',end_color='2F5496',fill_type='solid')
gfill=PatternFill(start_color='E2EFDA',end_color='E2EFDA',fill_type='solid')
yfill=PatternFill(start_color='FFF2CC',end_color='FFF2CC',fill_type='solid')
rfill=PatternFill(start_color='FCE4D6',end_color='FCE4D6',fill_type='solid')
border=Border(left=Side('thin'),right=Side('thin'),top=Side('thin'),bottom=Side('thin'))

# Sheet 1: 信号
ws=wb.active; ws.title='7月XX日信号'
headers=['代码','名称','现价','PE','YTD%','旧XGB','新XGB','3D分','等级','仓位%','R:R','中枢','中枢内','BSP','V4.5','GZK','买入','止损','TP1','风控','标签']
for col,h in enumerate(headers,1):
    c=ws.cell(row=1,column=col,value=h); c.font=hfont; c.fill=hfill; c.alignment=Alignment(horizontal='center',wrap_text=True); c.border=border

counts={}; row=2
for r in results:
    lab=r.get('label','')
    if '中枢内买' in lab and '否决' not in lab: fill=gfill; k='best'
    elif '中枢内等信号' in lab: fill=yfill; k='wait'
    elif 'Sell' in lab: fill=rfill; k='sell'
    else: fill=None; k='other'
    counts[k]=counts.get(k,0)+1
    rr_s=str(r['rr']) if r.get('rr') and r['rr']>0 else '—'
    pos_pct=str(int(r.get('position',0)*100))+'%'
    vals=[r['code'],r.get('name','?'),r['price'],r.get('pe','?'),str(round(r['ytd'],1))+'%',
          r.get('old_xgb',0),r.get('new_xgb',0),r.get('s3d',0),r.get('grade','?'),pos_pct,
          rr_s,str(r.get('zs_str',''))[:20],'Y' if r.get('in_zs') else 'N',str(r.get('bl','')),
          str(r.get('v45s',0)),str(r.get('gzk',0)),
          str(r['entry']) if r.get('entry') else '—',str(r['stop']) if r.get('stop') else '—',
          str(r['tp1']) if r.get('tp1') else '—',r.get('risk','OK'),lab]
    for col,v in enumerate(vals,1):
        c=ws.cell(row=row,column=col,value=v); c.font=Font(name='宋体',size=9)
        c.alignment=Alignment(horizontal='center',wrap_text=True); c.border=border
        if fill: c.fill=fill
    row+=1
col_widths=[8,10,7,5,7,5,5,5,4,6,4,20,5,14,5,5,7,7,7,6,28]
for i,w in enumerate(col_widths,1): ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width=w
ws.freeze_panes='A2'

# Sheet 2: 宏观 (填入当日数据)
ws2=wb.create_sheet('宏观')
# ... 见下方当日宏观模板

# Sheet 3: 综合推荐
for r in results:
    r['_rank']=r.get('s3d',0)*0.5+(r.get('old_xgb',0)*0.3 if r.get('in_zs') else 0)+(10 if r.get('v45s',0)>=8 else 0)
results.sort(key=lambda r:-r.get('_rank',0))
# ... 输出Top15

wb.save('/root/hs300_signals_YYYYMMDD_full.xlsx')
XEOF

# 3. 推送
cd /root/finance-market-analysis
cp /root/hs300_signals_YYYYMMDD_full.xlsx .
git add hs300_signals_YYYYMMDD_full.xlsx
git commit -m "report: MM/DD全功能扫描"
git push
```

## 宏观Sheet当日模板

```
MM月DD日收盘 | 缠论+双XGBoost+三维评分+风控 | 17模块全功能扫描

━━━ 市场指数 ━━━
上证指数: XXXX (中枢XXX下方/上方) | 期权PCR X.XXX
沪深300子指数: IF主力XXXX(X%), IC主力XXXX(X%), IM主力XXXX(X%)

━━━ 股指期货 ━━━
四大期指持仓变化: IM±X IC±X IF±X IH±X

━━━ 美债/美元/黄金 ━━━
T国债持仓变化 | COMEX黄金库存 | 美元贸易逆差/指数

━━━ 港股沽空 ━━━
快手/腾讯/小米/美团/阿里 沽空率

━━━ 综合判断 ━━━
今日扫描: XX中枢内买 XX等信号 XXSell
```

## 颜色规范

- 绿底(E2EFDA): 中枢内买
- 黄底(FFF2CC): 中枢内等信号
- 红底(FCE4D6): 中枢内Sell
- 蓝底标题(2F5496): 表头
