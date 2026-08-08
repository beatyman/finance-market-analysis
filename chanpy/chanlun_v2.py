# -*- coding: utf-8 -*-
"""
缠论核心 V2 (融合版): 包含 -> 分型 -> 笔 -> 中枢 -> 背驰

融合 V61 原版 + chan.py (Vespa314) + czsc (zengbin93) 三者优势:
  - K线合并: czsc 3根K线法确定方向(最稳定) + chan.py 一字K线处理 + 成交量合并
  - 分型识别: czsc 交替强制 + chan.py 4种分型验证模式(strict/loss/half/totally)
  - 笔构建: chan.py 峰值验证(end_is_peak) + czsc 笔破坏检测 + min_bi_len=6 + chan.py 虚笔
  - 中枢: chan.py 中枢合并(zs/peak模式) + czsc is_valid验证 + chan.py 一笔中枢
  - 背驰: chan.py end_bi_break验证(最关键) + 盘整背驰中枢归属检查 + 半笔面积 + divergence_rate可配

修复 V61 的 13 个算法缺陷 (#1-#13), 其中 #5/#6/#10/#11 为高危项。

所有函数输入均为 bars dict: {'date':[], 'open':[], 'high':[], 'low':[], 'close':[], 'volume':[], ...}
兼容无 volume 字段的输入。
"""
from statistics import mean as _mean

# ============================================================
# 配置常量
# ============================================================

CHAN_WINDOW = 120      # 中枢识别回看窗口
BI_MIN_GAP = 3         # 笔之间最小K线间隔 (用户确认: 分型高低点K线之间有3根就足够)
MIN_BI_LEN = 6         # 一笔至少包含的合并K线数 (czsc标准)
DIVERGENCE_RATE = 1.0  # 背驰力度判定阈值倍率 (1.0=标准, >1.0=严格, chan.py默认1.0)
FX_CHECK_METHOD = 'strict'  # 分型验证模式: strict/loss/half/totally
BI_END_IS_PEAK = True  # 笔结束端峰值验证 (chan.py: bi_end_is_peak)
ZS_NEED_COMBINE = False # V3结构门: 保留原始同级别中枢，禁止合并后丢失趋势序列
ZS_COMBINE_MODE = 'zs' # 中枢合并模式: zs/peak
ONE_BI_ZS = False      # 一笔中枢开关 (chan.py: one_bi_zs)
END_BI_BREAK = True    # 背驰验证: 离开笔必须突破中枢边界 (chan.py: end_bi_break)

# ============================================================
# V2.1 新增配置: 背离检测 + 背驰改进
# ============================================================
DIF_EXTEND = 3            # DIF极值搜索扩展窗口 (笔端点±N根K线, 捕获真实极值)
ZS_PLATFORM_MERGE = False # V3结构门: 禁止“人眼平台”式激进合并
ZS_PLATFORM_GAP = 2       # 平台合并: 相邻中枢最大间隔(笔数)
DESTRUCTION_MODE = 'force'  # 破坏判断模式: 'price'=纯价格 / 'force'=力度优先
DIVERGENCE_LOOKBACK = 80   # 趋势背离回看窗口 (约4个月, 覆盖一个完整下跌趋势)
DIVERGENCE_MIN_LOWS = 3    # 趋势背离最少低点数
DIVERGENCE_DIF_WINDOW = 5  # 趋势背离: 每个价格低点附近找DIF极值的窗口(±N根K线)
DIVERGENCE_RECENCY = 15    # 趋势背离: forming判定的最大recency(根K线)


def mean(xs):
    return _mean(xs) if xs else 0.0


def ema_series(vals, n):
    if not vals:
        return []
    a = 2.0 / (n + 1)
    out = [vals[0]]
    for v in vals[1:]:
        out.append(out[-1] + a * (v - out[-1]))
    return out


def macd(closes):
    e12 = ema_series(closes, 12)
    e26 = ema_series(closes, 26)
    dif = [e12[i] - e26[i] for i in range(len(closes))]
    dea = ema_series(dif, 9)
    hist = [2.0 * (dif[i] - dea[i]) for i in range(len(closes))]
    return dif, dea, hist


# ============================================================
# 模块一: K线合并 (修复 #1 #2 #3)
# ============================================================
# 改进来源:
#   #1 方向判断: czsc 3根K线法 (取前2根非包含K线的方向, 比V61的"首根默认True"稳定)
#   #2 一字K线: chan.py 处理 (high==low时按方向取值)
#   #3 成交量: 合并时累加成交量 (如果输入有volume字段)
# ------------------------------------------------------------
# 合并后的K线格式: [high, low, high_idx, low_idx, volume]
# 兼容V61格式: 外部访问 [0]=high [1]=low [2]=high_idx [3]=low_idx


def merge_inclusion(highs, lows, volumes=None):
    """
    K线包含合并 — 融合 czsc 3根K线法 + chan.py 一字K线处理 + 成交量合并

    改进 #1: 方向判断使用 czsc 的3根K线法
             - 找到最近2根非包含K线确定方向(而非V61的"首根默认True")
             - 方向向上: max(high), max(low)
             - 方向向下: min(high), min(low)
    改进 #2: 一字K线(high==low)处理 — chan.py方式
             - 一字K线视为可被任何方向包含, 不影响方向判断
    改进 #3: 成交量合并 — 如果有volume数据则累加
    """
    n = len(highs)
    if n == 0:
        return []

    vol = volumes if volumes is not None else [0.0] * n
    merged = []  # 每项: [high, low, high_idx, low_idx, volume]

    for i in range(n):
        h, l, v = highs[i], lows[i], vol[i]

        if not merged:
            merged.append([h, l, i, i, v])
            continue

        ph, pl, phi, pli, pv = merged[-1]

        # 判断包含关系: A包含B 或 B包含A
        contained = (h <= ph and l >= pl) or (h >= ph and l <= pl)

        # 一字K线特殊处理 (#2): high==low 时不改变方向
        is_one_price = (abs(h - l) < 1e-9)

        if contained:
            # 确定合并方向 — czsc 3根K线法 (#1)
            direction = _get_merge_direction(merged, i, highs, lows)
            if direction == 'up':
                nh, nl = max(h, ph), max(l, pl)
                nhi = i if h > ph else phi
                nli = i if l > pl else pli
            elif direction == 'down':
                nh, nl = min(h, ph), min(l, pl)
                nhi = i if h < ph else phi
                nli = i if l < pl else pli
            else:
                # 无法确定方向时(前2根也是包含的), 默认按向上处理
                nh, nl = max(h, ph), max(l, pl)
                nhi = i if h > ph else phi
                nli = i if l > pl else pli
            merged[-1] = [nh, nl, nhi, nli, pv + v]
        else:
            merged.append([h, l, i, i, v])

    return merged


def _get_merge_direction(merged, cur_idx, highs, lows):
    """
    czsc 3根K线法确定合并方向 (#1)
    - 找到 merged 中最近2根非包含K线的关系
    - 如果前一根的high < 当前非包含K线的high → 向上
    - 如果前一根的high > 当前非包含K线的high → 向下
    - 需要回溯到原始K线序列找方向
    """
    if len(merged) < 2:
        # 只有1根已合并K线, 用原始K线序列的方向
        orig_idx = merged[-1][2]  # high_idx 指向原始K线
        if orig_idx > 0:
            if highs[cur_idx] > highs[orig_idx]:
                return 'up'
            elif highs[cur_idx] < highs[orig_idx]:
                return 'down'
        return 'up'  # 无法确定时默认向上

    # 找 merged 中倒数第2根和最后1根的关系
    prev2 = merged[-2]
    prev1 = merged[-1]

    # 比较2根非包含K线的高点
    if prev1[0] > prev2[0]:
        return 'up'
    elif prev1[0] < prev2[0]:
        return 'down'
    else:
        # 高点相等比低点
        if prev1[1] > prev2[1]:
            return 'up'
        elif prev1[1] < prev2[1]:
            return 'down'

    return 'up'


# ============================================================
# 模块二: 分型识别 (修复 #4)
# ============================================================
# 改进来源:
#   #4 分型交替强制: czsc check_fxs — 不允许连续出现同类型分型
#   分型验证模式: chan.py bi_fx_check (strict/loss/half/totally)
#     - strict: 标准缠论, 顶分型high严格>左右, low严格>左右
#     - loss: 允许low相等(宽松)
#     - half: 半严格, 只验证high或low中的一个
#     - totally: 完全宽松, 只要high或low有一个满足即可
# ------------------------------------------------------------


def find_fractals(merged, fx_check=None):
    """
    分型识别 — 增加 czsc 交替强制 + chan.py 4种验证模式 (#4)

    参数:
      merged: merge_inclusion 返回的合并K线列表
      fx_check: 分型验证模式 'strict'/'loss'/'half'/'totally'
                None时使用全局 FX_CHECK_METHOD

    返回: [(type, idx, value, orig_idx), ...]
      type='top'/'bottom', idx=合并K线索引, value=价格, orig_idx=原始K线索引
    """
    if fx_check is None:
        fx_check = FX_CHECK_METHOD

    fr = []
    for i in range(1, len(merged) - 1):
        a, b, c = merged[i - 1], merged[i], merged[i + 1]

        is_top = _check_fx(a, b, c, 'top', fx_check)
        is_bottom = _check_fx(a, b, c, 'bottom', fx_check)

        if is_top:
            fr.append(('top', i, b[0], b[2]))
        elif is_bottom:
            fr.append(('bottom', i, b[1], b[3]))

    # czsc 分型交替强制 (#4): 不允许连续同类型分型
    fr = _enforce_fx_alternation(fr)

    return fr


def _check_fx(a, b, c, fx_type, method):
    """
    chan.py 4种分型验证模式
    a, b, c = 前一根, 当前根, 后一根 (合并K线)
    """
    a_h, a_l = a[0], a[1]
    b_h, b_l = b[0], b[1]
    c_h, c_l = c[0], c[1]

    if fx_type == 'top':
        if method == 'strict':
            # 严格: high和low都大于左右
            return b_h > a_h and b_h > c_h and b_l > a_l and b_l > c_l
        elif method == 'loss':
            # 宽松: 允许low相等
            return b_h > a_h and b_h > c_h and b_l >= a_l and b_l >= c_l
        elif method == 'half':
            # 半严格: 只验证high
            return b_h > a_h and b_h > c_h
        elif method == 'totally':
            # 完全宽松: high或low满足其一
            return (b_h > a_h and b_h > c_h) or (b_l > a_l and b_l > c_l)
    elif fx_type == 'bottom':
        if method == 'strict':
            return b_l < a_l and b_l < c_l and b_h < a_h and b_h < c_h
        elif method == 'loss':
            return b_l < a_l and b_l < c_l and b_h <= a_h and b_h <= c_h
        elif method == 'half':
            return b_l < a_l and b_l < c_l
        elif method == 'totally':
            return (b_l < a_l and b_l < c_l) or (b_h < a_h and b_h < c_h)

    return False


def _enforce_fx_alternation(fractals):
    """
    czsc 分型交替强制 (#4)
    - 顶分型后面必须跟底分型, 反之亦然
    - 如果出现连续同类型, 保留更极端的那个
    """
    if len(fractals) <= 1:
        return fractals

    result = [fractals[0]]
    for f in fractals[1:]:
        last = result[-1]
        if f[0] == last[0]:
            # 同类型分型, 保留更极端的
            if f[0] == 'top' and f[2] > last[2]:
                result[-1] = f
            elif f[0] == 'bottom' and f[2] < last[2]:
                result[-1] = f
        else:
            result.append(f)

    return result


# ============================================================
# 模块三: 笔构建 (修复 #5 #6 #7)
# ============================================================
# 改进来源:
#   #5 峰值验证: chan.py end_is_peak — 笔的结束端必须是局部极值
#   #6 笔破坏检测: czsc check_bi — 后一笔必须"破坏"前一笔的结构
#   #7 min_bi_len: czsc min_bi_len=6 (V61原版BI_MIN_GAP=4偏小)
#   额外: chan.py 虚笔处理 — 允许未确认的笔临时存在
# ------------------------------------------------------------


def build_bis(fractals, bi_min_gap=None, merged=None, bars=None):
    """
    笔构建 — 融合 chan.py 峰值验证 + czsc 笔破坏检测 + min_bi_len=6 (#5 #6 #7)

    参数:
      fractals: find_fractals 返回的分型列表
      bi_min_gap: 笔之间最小K线间隔 (None时用BI_MIN_GAP=6)
      merged: 合并K线列表 (用于峰值验证, 可选)
      bars: 原始bars dict (用于峰值验证, 可选)

    改进:
      #5: 笔结束端峰值验证 — 确保笔的端点是真正的局部极值
      #6: 笔破坏检测 — 上升笔被后续K线跌破起点才算笔被破坏
      #7: min_bi_len=6 — 一笔至少6根合并K线 (czsc标准)
    """
    if bi_min_gap is None:
        bi_min_gap = BI_MIN_GAP

    bis = []
    for f in fractals:
        if not bis:
            bis.append(f)
            continue

        last = bis[-1]

        # 同类型分型: 更新极值 (不应出现, 交替强制已处理)
        if f[0] == last[0]:
            if (f[0] == 'top' and f[2] > last[2]) or \
               (f[0] == 'bottom' and f[2] < last[2]):
                bis[-1] = f
            continue

        # 不同类型: 检查是否可以构成一笔
        gap_ok = (f[1] - last[1]) >= bi_min_gap  # #7: 间距>=6
        price_ok = (f[2] > last[2]) if f[0] == 'top' else (f[2] < last[2])

        if not (gap_ok and price_ok):
            continue

        # #5: 峰值验证 — 笔的端点必须是局部极值
        if BI_END_IS_PEAK and merged is not None and bars is not None:
            if not _verify_peak(f, merged, bars):
                continue

        # #6: 笔破坏检测 — 确认笔结构被后续走势破坏
        if not _check_bi_break(bis, f, merged, bars):
            continue

        bis.append(f)

    return bis


def _verify_peak(fractal, merged, bars):
    """
    chan.py 峰值验证 (#5) — bi_end_is_peak
    确保分型端点在合并K线序列中是真正的局部极值

    改进: 使用合并K线而非原始K线进行验证, 窗口缩小到前后各1根
    (合并K线已处理包含关系, 验证更准确)
    """
    fx_type, merge_idx, value, orig_idx = fractal

    if merged is None or len(merged) == 0:
        return True

    # 用合并K线的前后各1根验证 (3根窗口)
    check_start = max(0, merge_idx - 1)
    check_end = min(len(merged), merge_idx + 2)

    if fx_type == 'top':
        for i in range(check_start, check_end):
            if merged[i][0] > value + 1e-9:
                return False
    else:
        for i in range(check_start, check_end):
            if merged[i][1] < value - 1e-9:
                return False

    return True


def _check_bi_break(bis, new_fx, merged, bars):
    """
    czsc 笔破坏检测 (#6) — 改进版
    检查笔的结构完整性: 在两个分型之间的合并K线不应显著突破起点

    改进: 使用合并K线而非原始K线 + 容差机制(0.5%)
    - 合并K线已处理包含关系, 检查更准确
    - 0.5%容差允许小幅波动, 只过滤显著的结构破坏
    """
    if len(bis) < 1 or merged is None:
        return True

    last = bis[-1]
    last_merge_idx = last[1]  # 合并K线索引
    new_merge_idx = new_fx[1]

    if last_merge_idx >= len(merged) or new_merge_idx > len(merged):
        return True

    # 笔方向: last是bottom → 上升笔; last是top → 下降笔
    is_up = (last[0] == 'bottom')

    # 容差: 允许0.5%的波动 (避免小幅震荡被误判为结构破坏)
    if is_up:
        last_low = last[2]
        tolerance = last_low * 0.005
        for i in range(last_merge_idx + 1, min(new_merge_idx, len(merged))):
            if merged[i][1] < last_low - tolerance:
                return False
    else:
        last_high = last[2]
        tolerance = last_high * 0.005
        for i in range(last_merge_idx + 1, min(new_merge_idx, len(merged))):
            if merged[i][0] > last_high + tolerance:
                return False

    return True


# ============================================================
# 模块四: 中枢 (修复 #8 #9)
# ============================================================
# 改进来源:
#   #8 中枢合并: chan.py ZS.combine (zs/peak两种模式)
#     - zs模式: 中枢区间有重叠时合并
#     - peak模式: 峰值有重叠时合并
#   #9 中枢有效性验证: czsc ZS.is_valid
#     - 验证中枢至少由3笔构成(或一笔中枢模式下的1笔+验证)
#   额外: chan.py 一笔中枢支持 (one_bi_zs)
# ------------------------------------------------------------


def find_centers(bis, need_combine=None, one_bi_zs=None):
    """
    V3.1 中枢识别（用户确认版 2026-07-25）。

    核心规则：
      1. 中枢 = 至少三笔重叠的区间，可以是三笔、四笔、五笔甚至更多
      2. ZG/ZD 由前三笔确定后固定不变，后续笔不改变 ZG/ZD
      3. 后续笔只要和中枢区间有重叠（hj >= ZD and lj <= ZG），就并入中枢
      4. 离开笔 = 中枢的最后一笔。判断标准：离开笔的下一笔没有再回到中枢区间
      5. 离开笔和中枢最后一笔可以是同一根（不冲突）
      6. 进入笔 = 中枢形成前的那根笔（不在中枢内）

    与V3的区别：
      - 不再用"终点跌出/涨出中枢"来判断离开笔
      - 离开笔可以部分跌出中枢（只要和中枢区间有重叠就并入）
      - 离开笔的确认标准是看下一笔是否回到中枢
    """
    if need_combine is None:
        need_combine = ZS_NEED_COMBINE
    if one_bi_zs is None:
        one_bi_zs = ONE_BI_ZS

    centers = []
    n_bi = len(bis) - 1

    if n_bi < 3:
        return centers

    # k=1 保留中枢前一笔，供 a+A+b 的进入段比较。
    k = 1
    while k <= n_bi - 3:
        l1, h1 = bi_range(bis, k)
        l2, h2 = bi_range(bis, k + 1)
        l3, h3 = bi_range(bis, k + 2)

        ZG = min(h1, h2, h3)
        ZD = max(l1, l2, l3)

        if ZG > ZD:
            GG, DD = max(h1, h2, h3), min(l1, l2, l3)
            bi_end = k + 2

            # 继续扩展：后续笔只要和中枢区间有重叠就并入
            departure_idx = None
            j = k + 3
            while j <= n_bi - 1:
                lj, hj = bi_range(bis, j)
                # 只要和中枢区间有重叠就并入
                if hj >= ZD and lj <= ZG:
                    bi_end = j
                    GG, DD = max(GG, hj), min(DD, lj)
                    j += 1
                else:
                    # 完全在中枢区间外，不并入
                    break

            # 判断最后一笔是否是离开笔：看下一笔是否回到中枢
            if bi_end + 1 <= n_bi - 1:
                next_l, next_h = bi_range(bis, bi_end + 1)
                if next_h < ZD or next_l > ZG:
                    # 下一笔没有回到中枢，确认离开
                    departure_idx = bi_end
                # else: 下一笔回到了中枢，不是离开笔，继续循环
            else:
                # 最后一根笔就是离开笔（后面没有更多笔了）
                departure_idx = bi_end

            # #9: 中枢有效性验证
            n_bi_in_zs = bi_end - k + 1
            if n_bi_in_zs >= 3 or (one_bi_zs and n_bi_in_zs >= 1):
                centers.append({
                    'bi_start': k, 'bi_end': bi_end,
                    'n_bi': n_bi_in_zs,
                    'ZG': ZG, 'ZD': ZD, 'GG': GG, 'DD': DD,
                    'x_start': bis[k][3],
                    'x_end': bis[bi_end + 1][3] if bi_end + 1 < len(bis) else bis[bi_end][3],
                    'combined': False,
                    'level_state': 'higher_level_candidate' if n_bi_in_zs >= 9 else (
                        'extension' if n_bi_in_zs > 3 else 'base'
                    ),
                    'departure_idx': departure_idx,
                })
            # 跳过已经确认的离开段。新中枢从其后的反向段开始。
            k = (departure_idx + 1) if departure_idx is not None else (bi_end + 1)
        else:
            k += 1

    # 仅保留显式兼容开关；V3默认关闭。开启后结果不再满足严格结构门。
    if need_combine and len(centers) >= 2:
        centers = _combine_centers(centers, bis)

    return centers


def _combine_centers(centers, bis=None):
    """
    中枢合并 (#8 + V2.1平台合并)

    两阶段合并:
      阶段1 (标准合并): 相邻中枢ZG/ZD区间有重叠 → 合并 (chan.py zs模式)
      阶段2 (平台合并): 相邻中枢GG/DD范围有重叠 + 时间间隔不远 → 合并为大整理平台
        - 人类视角: 把多个小中枢看作一个大的整理平台
        - 解决问题: 算法拆太碎, 人类看到的大平台被分成多个小中枢

    参数:
      centers: 原始中枢列表
      bis: 笔列表 (平台合并时用于重新计算ZG/ZD)
    """
    if len(centers) < 2:
        return centers

    # 阶段1: 标准合并 (ZG/ZD重叠)
    combined = [centers[0]]
    for c in centers[1:]:
        prev = combined[-1]
        has_overlap = prev['ZD'] < c['ZG'] and prev['ZG'] > c['ZD']
        if has_overlap:
            merged_c = {
                'bi_start': prev['bi_start'],
                'bi_end': c['bi_end'],
                'n_bi': c['bi_end'] - prev['bi_start'] + 1,
                'ZG': min(prev['ZG'], c['ZG']),
                'ZD': max(prev['ZD'], c['ZD']),
                'GG': max(prev['GG'], c['GG']),
                'DD': min(prev['DD'], c['DD']),
                'x_start': prev['x_start'],
                'x_end': c['x_end'],
                'combined': True
            }
            combined[-1] = merged_c
        else:
            combined.append(c)

    # 阶段2: 平台合并 (GG/DD重叠 + 时间相近)
    if not ZS_PLATFORM_MERGE or len(combined) < 2:
        return combined

    platform = [combined[0]]
    for c in combined[1:]:
        prev = platform[-1]

        # 时间间隔检查: 两个中枢之间的笔数
        gap = c['bi_start'] - prev['bi_end']
        if gap > ZS_PLATFORM_GAP:
            platform.append(c)
            continue

        # 价格范围重叠: GG/DD有交集
        range_overlap = prev['DD'] <= c['GG'] and prev['GG'] >= c['DD']
        if not range_overlap:
            platform.append(c)
            continue

        # 合并: 从所有笔重新计算ZG/ZD
        bi_start = prev['bi_start']
        bi_end = c['bi_end']

        all_highs = []
        all_lows = []
        if bis is not None:
            for j in range(bi_start, min(bi_end + 1, len(bis) - 1)):
                l, h = bi_range(bis, j)
                all_highs.append(h)
                all_lows.append(l)

        if len(all_highs) >= 3:
            new_ZG = min(all_highs)
            new_ZD = max(all_lows)
        else:
            new_ZG = min(prev['ZG'], c['ZG'])
            new_ZD = max(prev['ZD'], c['ZD'])

        # 如果合并后ZG <= ZD, 说明不是一个有效中枢, 不合并
        if new_ZG <= new_ZD:
            platform.append(c)
            continue

        merged_c = {
            'bi_start': bi_start,
            'bi_end': bi_end,
            'n_bi': bi_end - bi_start + 1,
            'ZG': new_ZG,
            'ZD': new_ZD,
            'GG': max(prev['GG'], c['GG']),
            'DD': min(prev['DD'], c['DD']),
            'x_start': prev['x_start'],
            'x_end': c['x_end'],
            'combined': True,
            'platform': True,
        }
        platform[-1] = merged_c

    return platform


# ============================================================
# 模块五: 背驰检测 (修复 #10 #11 #12 #13)
# ============================================================
# 改进来源:
#   #10 end_bi_break验证: chan.py — 离开中枢的笔必须突破中枢边界才算背驰
#   #11 盘整背驰中枢归属检查: chan.py treat_pz_bsp1 — 确保盘整背驰的两笔属于同一线段/中枢
#   #12 半笔面积: chan.py Cal_MACD_half — 使用半笔面积提高精度
#   #13 divergence_rate可配: chan.py BSPointConfig — 背驰力度阈值可配置
# ------------------------------------------------------------


def bi_range(bis, j):
    a, b = bis[j][2], bis[j + 1][2]
    return (min(a, b), max(a, b))


def _force(dif, hist, x0, x1, up, dif_extend=None):
    """
    计算一笔的MACD力度 (#12 + V2.1改进)
    返回 (dif_peak, area, half_area)
      - dif_peak: DIF峰值(距零轴最远点)
      - area: 全笔MACD柱面积
      - half_area: 半笔面积(_chan.py Cal_MACD_half, 取力度更大的一半)

    V2.1改进: DIF极值搜索窗口扩展 (dif_extend)
      - 原版: 在[x0, x1]内找DIF极值
      - 改进: 在[x0-extend, x1+extend]内找DIF极值
      - 原因: DIF极值可能出现在笔端点附近但不完全重合(差1-3天)
      - 面积计算仍使用原始[x0, x1]范围, 只有DIF极值用扩展窗口
    """
    if dif_extend is None:
        dif_extend = DIF_EXTEND

    n_dif = len(dif)
    # 面积计算使用原始笔范围
    seg = dif[x0:x1 + 1]
    # DIF极值搜索使用扩展窗口
    d_start = max(0, x0 - dif_extend)
    d_end = min(n_dif, x1 + dif_extend + 1)
    wide_seg = dif[d_start:d_end]

    if up:
        peak = max(wide_seg) if wide_seg else 0.0
        area = sum(x for x in hist[x0:x1 + 1] if x > 0)
        # #12: 半笔面积 — 取峰值点为界, 计算面积更大的一半
        if seg:
            # 在扩展窗口中找到peak的位置, 然后钳位到笔范围内
            wide_peak_idx = wide_seg.index(peak) + d_start
            split_idx = max(x0, min(x1, wide_peak_idx))
            half1 = sum(x for x in hist[x0:split_idx + 1] if x > 0)
            half2 = sum(x for x in hist[split_idx:x1 + 1] if x > 0)
            half_area = max(half1, half2)
        else:
            half_area = area
    else:
        peak = min(wide_seg) if wide_seg else 0.0
        area = -sum(x for x in hist[x0:x1 + 1] if x < 0)
        # 半笔面积
        if seg:
            wide_peak_idx = wide_seg.index(peak) + d_start
            split_idx = max(x0, min(x1, wide_peak_idx))
            half1 = -sum(x for x in hist[x0:split_idx + 1] if x < 0)
            half2 = -sum(x for x in hist[split_idx:x1 + 1] if x < 0)
            half_area = max(half1, half2)
        else:
            half_area = area

    return peak, area, half_area


def _weaker(pa, aa, pb, ab, up, divergence_rate=None):
    """
    背驰力度判定 (#13)
    改进: divergence_rate 可配置
      - rate=1.0: 标准背驰 (B的面积<A的面积 且 DIF背离)
      - rate>1.0: 严格背驰 (B的面积 < A的面积 / rate, 更严格)
      - rate<1.0: 宽松背驰 (B的面积只需 < A的面积 * rate)

    参数:
      pa, aa: A笔的peak和area
      pb, ab: B笔的peak和area
      up: 方向(True=向上看顶背驰, False=向下看底背驰)
      divergence_rate: 力度倍率, None时用全局DIVERGENCE_RATE
    """
    if divergence_rate is None:
        divergence_rate = DIVERGENCE_RATE

    if aa <= 0:
        return False

    # 面积判定 (支持divergence_rate)
    area_weaker = ab < aa / divergence_rate if divergence_rate > 0 else ab < aa

    # DIF背离判定
    if up:
        dif_weaker = pb < pa
    else:
        dif_weaker = pb > pa

    return area_weaker and dif_weaker


def _consolidation_quality(dif, mid_start, mid_end, peak_a, peak_b, fluctuation_pct):
    """
    计算背驰中间段的整理充分度

    理想背驰形态: 中间段(盘整背驰的反弹笔 / 中枢背驰的中枢)波动小,
                  MACD回到零轴附近, 说明股价整理充分.

    参数:
      dif: DIF线数组
      mid_start, mid_end: 中间段的起止orig_idx
      peak_a, peak_b: A笔和B笔的DIF峰值(原始值, 可正可负)
      fluctuation_pct: 中间段的价格波动幅度(%)

    返回 dict:
      - dif_reset_ratio: DIF回到零轴程度 (0=完全回零轴, 1=未回零轴)
      - fluctuation_pct: 价格波动幅度
      - consolidation_score: 整理充分度评分 (0-20)
      - consolidation_label: '充分' / '一般' / '不足'
    """
    if mid_end <= mid_start:
        mid_end = mid_start + 1

    seg = dif[mid_start:mid_end + 1]
    if seg:
        min_abs_dif = min(abs(x) for x in seg)
    else:
        min_abs_dif = 0

    max_peak = max(abs(peak_a), abs(peak_b))
    if max_peak > 0:
        dif_reset_ratio = min_abs_dif / max_peak
    else:
        dif_reset_ratio = 0

    dif_reset_ratio = min(dif_reset_ratio, 1.0)

    # MACD回零轴评分 (0-12): ratio越小(越接近零轴)越好
    macd_reset_score = (1 - dif_reset_ratio) * 12

    # 波动幅度评分 (0-8): 波动越小越好
    fp = abs(fluctuation_pct)
    if fp < 5:
        fluct_score = 8
    elif fp < 8:
        fluct_score = 6
    elif fp < 12:
        fluct_score = 4
    elif fp < 18:
        fluct_score = 2
    else:
        fluct_score = 0

    quality_score = macd_reset_score + fluct_score

    if quality_score >= 15:
        quality_label = '充分'
    elif quality_score >= 8:
        quality_label = '一般'
    else:
        quality_label = '不足'

    return {
        'dif_reset_ratio': round(dif_reset_ratio, 4),
        'fluctuation_pct': round(fluctuation_pct, 2),
        'consolidation_score': round(quality_score, 1),
        'consolidation_label': quality_label,
    }


def detect_divergences(bis, centers, dif, hist, divergence_rate=None):
    """
    背驰检测 — 融合 chan.py end_bi_break + 盘整背驰中枢归属 + 半笔面积 (#10-#13)

    改进:
      #10: end_bi_break — 离开中枢的笔必须突破中枢ZG/ZD边界
           (chan.py: is_divergence中验证end_bi_break)
           → 防止"假背驰": 笔未突破中枢就判定为背驰
      #11: 盘整背驰中枢归属 — 确保盘整背驰的两笔属于同一个线段/中枢范围
           (chan.py: treat_pz_bsp1中检查seg_idx)
           → 防止跨线段的假盘整背驰
      #12: 半笔面积 — _force返回half_area, 使用max(area, half_area)提高精度
      #13: divergence_rate可配 — _weaker支持可配置力度倍率
    """
    if divergence_rate is None:
        divergence_rate = DIVERGENCE_RATE

    events = []
    n_bi = len(bis) - 1
    zs_oidx = set()

    # ============ 中枢背驰 + 两中枢背驰 ============
    # 用户确认版 2026-07-25:
    #   B段 = 中枢的最后一笔(bi_end)，如果它是离开笔(departure_idx == bi_end)
    #   离开笔和中枢最后一笔可以是同一根，不需要到中枢之后去找
    for ci, c in enumerate(centers):
        A_idx = c['bi_start'] - 1  # 进入中枢的笔
        if A_idx < 0:
            continue

        A_up = bis[A_idx][0] == 'bottom'
        A_end = bis[A_idx + 1][2]

        # B段 = 中枢的最后一笔，如果它是离开笔
        departure_idx = c.get('departure_idx')
        if departure_idx is None or departure_idx != c['bi_end']:
            continue  # 中枢没有确认的离开笔，不能检测中枢背驰

        B_idx = c['bi_end']  # 中枢的最后一笔就是离开笔

        # B段必须和A段同方向
        B_up = bis[B_idx][0] == 'bottom'
        if B_up != A_up:
            continue

        # B段必须创新极值
        B_end = bis[B_idx + 1][2]
        if A_up and B_end <= A_end:
            continue  # 顶背驰: B段高点必须超过A段
        if not A_up and B_end >= A_end:
            continue  # 底背驰: B段低点必须低于A段

        # end_bi_break验证: 离开笔必须突破中枢边界
        if END_BI_BREAK:
            if A_up and B_end <= c['ZG']:
                continue
            if not A_up and B_end >= c['ZD']:
                continue

        # 计算A笔和B笔的力度 (#12: 半笔面积)
        pa, aa, ha = _force(dif, hist, bis[A_idx][3], bis[A_idx + 1][3], A_up)
        pb, ab, hb = _force(dif, hist, bis[B_idx][3], bis[B_idx + 1][3], A_up)

        # 使用max(全笔面积, 半笔面积)提高精度 (#12)
        aa_eff = max(aa, ha)
        ab_eff = max(ab, hb)

        if not _weaker(pa, aa_eff, pb, ab_eff, A_up, divergence_rate):
            continue

        # 判断背驰类型
        mode = '中枢背驰'
        if ci >= 1:
            pv = centers[ci - 1]
            if (A_up and c['ZD'] > pv['ZG']) or ((not A_up) and c['ZG'] < pv['ZD']):
                mode = '两中枢背驰'

        events.append({
            'mode': mode,
            'kind': 'top' if A_up else 'bottom',
            'oidx': bis[B_idx + 1][3],
            'center_idx': ci,
            'A_idx': A_idx,
            'B_idx': B_idx,
            'area_ratio': ab_eff / aa_eff if aa_eff > 0 else 0,
            'dif_ratio': abs(pb / pa) if pa != 0 else 0,
            **_consolidation_quality(
                dif,
                bis[c['bi_start']][3], bis[c['bi_end']][3],
                pa, pb,
                (c['ZG'] - c['ZD']) / c['ZD'] * 100 if c['ZD'] > 0 else 0
            )
        })
        zs_oidx.add(bis[B_idx + 1][3])

    # ============ V2.2修正: 中枢内进入段 vs 离开段背驰 ============
    # 用户确认版 2026-07-25:
    #   A段 = 中枢内第一根同方向笔(进入段)
    #   B段 = 中枢的最后一笔(bi_end)，即离开笔(departure_idx == bi_end)
    #   离开笔和中枢最后一笔是同一根，不需要到中枢之后去找
    for ci, c in enumerate(centers):
        # 如果标准中枢背驰已覆盖此中枢, 跳过
        already_covered = any(
            e.get('center_idx') == ci and e['mode'] in ('中枢背驰', '两中枢背驰')
            for e in events
        )
        if already_covered:
            continue

        departure_idx = c.get('departure_idx')
        if departure_idx is None or departure_idx != c['bi_end']:
            continue  # 中枢没有确认的离开笔

        for want_bottom in [True, False]:
            if want_bottom:
                enter_fx = 'top'       # 向下笔起点是top
                up = False
            else:
                enter_fx = 'bottom'    # 向上笔起点是bottom
                up = True

            # 找中枢内第一根同方向笔(进入段)
            enter_bi = None
            for j in range(c['bi_start'], min(c['bi_end'] + 1, n_bi)):
                if bis[j][0] == enter_fx:
                    enter_bi = j
                    break
            if enter_bi is None:
                continue

            # B段 = 中枢的最后一笔(bi_end)，即离开笔
            leave_bi = c['bi_end']

            # B段必须和A段同方向
            if bis[leave_bi][0] != enter_fx:
                continue

            # B段必须创新极值
            enter_end = bis[enter_bi + 1][2]
            leave_end = bis[leave_bi + 1][2]
            if want_bottom and leave_end >= enter_end:
                continue  # 底背驰: B段低点必须低于A段
            if not want_bottom and leave_end <= enter_end:
                continue  # 顶背驰: B段高点必须超过A段

            # end_bi_break验证: 离开笔必须突破中枢边界
            if END_BI_BREAK:
                if want_bottom and leave_end >= c['ZD']:
                    continue
                if not want_bottom and leave_end <= c['ZG']:
                    continue

            # 比较力度
            pa, aa, ha = _force(dif, hist, bis[enter_bi][3], bis[enter_bi + 1][3], up)
            pb, ab, hb = _force(dif, hist, bis[leave_bi][3], bis[leave_bi + 1][3], up)
            aa_eff = max(aa, ha)
            ab_eff = max(ab, hb)

            if not _weaker(pa, aa_eff, pb, ab_eff, up, divergence_rate):
                continue

            # 判断背驰类型
            mode = '中枢背驰'
            if ci >= 1:
                pv = centers[ci - 1]
                if (up and c['ZD'] > pv['ZG']) or ((not up) and c['ZG'] < pv['ZD']):
                    mode = '两中枢背驰'

            events.append({
                'mode': mode,
                'kind': 'bottom' if want_bottom else 'top',
                'oidx': bis[leave_bi + 1][3],
                'center_idx': ci,
                'A_idx': enter_bi,
                'B_idx': leave_bi,
                'area_ratio': ab_eff / aa_eff if aa_eff > 0 else 0,
                'dif_ratio': abs(pb / pa) if pa != 0 else 0,
                **_consolidation_quality(
                    dif,
                    bis[c['bi_start']][3], bis[c['bi_end']][3],
                    pa, pb,
                    (c['ZG'] - c['ZD']) / c['ZD'] * 100 if c['ZD'] > 0 else 0
                )
            })
            zs_oidx.add(bis[leave_bi + 1][3])

    # ============ 盘整背驰 ============
    # 用户确认版 2026-07-25: 有中枢时优先中枢背驰，不对比中枢内的笔
    for j in range(2, n_bi):
        a0, a1 = bis[j][3], bis[j + 1][3]
        p0, p1 = bis[j - 2][3], bis[j - 1][3]

        if a1 - a0 < 2 or p1 - p0 < 2 or a1 in zs_oidx:
            continue

        up = bis[j][0] == 'bottom'

        if up and bis[j + 1][2] <= bis[j - 1][2]:
            continue
        if (not up) and bis[j + 1][2] >= bis[j - 1][2]:
            continue

        # #11: 盘整背驰中枢归属检查
        # 确保两笔属于同一个线段(中间没有中枢分隔)
        if not _check_pz_divergence_scope(bis, j, centers):
            continue

        # 用户新增: B段(bis[j]→bis[j+1])不能是中枢内的笔
        # 如果B段在某个中枢的范围内，则应该检测中枢背驰而非盘整背驰
        b_bi_idx = j  # B段起始笔索引
        b_in_center = False
        for c in centers:
            if c['bi_start'] <= b_bi_idx <= c['bi_end']:
                b_in_center = True
                break
        if b_in_center:
            continue

        # 力度对比 (#12: 半笔面积)
        pa, aa, ha = _force(dif, hist, p0, p1, up)
        pb, ab, hb = _force(dif, hist, a0, a1, up)

        aa_eff = max(aa, ha)
        ab_eff = max(ab, hb)

        if not _weaker(pa, aa_eff, pb, ab_eff, up, divergence_rate):
            continue

        # 盘整背驰中间段: bis[j-1] → bis[j] (反弹笔)
        mid_fluct = abs(bis[j][2] - bis[j - 1][2]) / bis[j - 1][2] * 100 if bis[j - 1][2] > 0 else 0

        events.append({
            'mode': '盘整背驰',
            'kind': 'top' if up else 'bottom',
            'oidx': a1,
            'area_ratio': ab_eff / aa_eff if aa_eff > 0 else 0,
            'dif_ratio': abs(pb / pa) if pa != 0 else 0,
            **_consolidation_quality(
                dif,
                bis[j - 1][3], bis[j][3],
                pa, pb,
                mid_fluct
            )
        })

    events.sort(key=lambda e: e['oidx'])
    return events


def _check_pz_divergence_scope(bis, j, centers):
    """
    盘整背驰中枢归属检查 (#11)
    chan.py treat_pz_bsp1 — 确保盘整背驰的两笔属于同一线段

    检查: 两笔(j-2,j-1)和(j,j+1)之间不应该有中枢分隔
    如果有中枢穿过两笔之间, 则这不是盘整背驰而是中枢背驰的范畴
    """
    # 两笔的范围: bis[j-2] 到 bis[j+1]
    seg_start = bis[j - 2][1]  # 合并K线索引
    seg_end = bis[j + 1][1]

    for c in centers:
        # 如果中枢完全包含在两笔之间, 则不属于盘整背驰
        if c['bi_start'] >= j - 1 and c['bi_end'] <= j:
            return False
        # 如果中枢的笔范围跨越了两笔的分界点
        c_bi_start = c['bi_start']
        c_bi_end = c['bi_end']
        # 两笔的索引范围是 j-2 到 j+1
        # 如果中枢开始于j-2之前且结束于j-1之后, 说明两笔被中枢分隔
        if c_bi_start <= j - 2 and c_bi_end >= j:
            return False

    return True


# ============================================================
# V3严格结构门
# ============================================================

def _leg_is_up(bis, leg_idx):
    """一笔从 bottom 起为向上，从 top 起为向下。"""
    return bis[leg_idx][0] == 'bottom'


def _price_zones_overlap(a, b):
    return max(a['ZD'], b['ZD']) < min(a['ZG'], b['ZG'])


def _classify_strict_mode(centers, center_idx, up):
    """按同级别中枢序列区分盘整背驰与趋势背驰。"""
    current = centers[center_idx]
    previous = None
    for candidate in reversed(centers[:center_idx]):
        if candidate['bi_end'] < current['bi_start'] - 1:
            previous = candidate
            break

    if previous is None:
        return '盘整背驰', None, None

    if _price_zones_overlap(previous, current):
        return None, previous, '相邻中枢区间重叠，属于扩张/更高级别候选，当前级别禁止硬判背驰'

    if up and current['ZD'] > previous['ZG']:
        return '趋势背驰', previous, None
    if (not up) and current['ZG'] < previous['ZD']:
        return '趋势背驰', previous, None

    # 前一中枢不构成当前方向的同级别趋势，当前中枢按单中枢盘整处理。
    return '盘整背驰', previous, None


def evaluate_structure_gates(bis, centers, dif, hist, divergence_rate=None):
    """
    对每个中枢执行不可绕过的结构门，并返回完整审计记录。

    硬条件：完整进入段 + 中枢 + 完整离开段；两段同级别、同方向；
    离开段有效突破中枢并创新高/新低。只有结构通过后才比较 MACD 力度。
    """
    if divergence_rate is None:
        divergence_rate = DIVERGENCE_RATE

    decisions = []
    n_legs = len(bis) - 1
    for ci, center in enumerate(centers):
        reasons = []
        entry_idx = center['bi_start'] - 1
        exit_idx = center['bi_end'] + 1

        if center.get('combined'):
            reasons.append('中枢经过合并，原始同级别序列已丢失')
        if center.get('level_state') == 'higher_level_candidate' or center.get('n_bi', 0) >= 9:
            reasons.append('中枢达到9笔，级别已升级或待重组')
        if entry_idx < 0:
            reasons.append('缺少中枢前完整进入段')
        if exit_idx > n_legs - 1:
            reasons.append('缺少中枢后完整离开段')

        decision = {
            'center_idx': ci,
            'entry_idx': entry_idx,
            'exit_idx': exit_idx,
            'structure_passed': False,
            'force_passed': False,
            'passed': False,
            'reasons': reasons,
            'level_basis': '同一笔级代理（操作级别的次级走势段）',
            'center': {
                'bi_start': center['bi_start'],
                'bi_end': center['bi_end'],
                'ZG': center['ZG'],
                'ZD': center['ZD'],
                'n_bi': center['n_bi'],
                'level_state': center.get('level_state', 'base'),
            },
        }
        if reasons:
            decisions.append(decision)
            continue

        entry_up = _leg_is_up(bis, entry_idx)
        exit_up = _leg_is_up(bis, exit_idx)
        mode, previous, mode_error = _classify_strict_mode(centers, ci, entry_up)
        if mode_error:
            reasons.append(mode_error)
        if entry_up != exit_up:
            reasons.append('进入段与离开段方向不同')

        entry_end = bis[entry_idx + 1][2]
        exit_end = bis[exit_idx + 1][2]
        breaks_center = exit_end > center['ZG'] if entry_up else exit_end < center['ZD']
        makes_extreme = exit_end > entry_end if entry_up else exit_end < entry_end
        if not breaks_center:
            reasons.append('离开段未有效突破中枢边界')
        if not makes_extreme:
            reasons.append('离开段未相对进入段创新高/新低')

        decision.update({
            'mode': mode,
            'kind': 'top' if entry_up else 'bottom',
            'same_direction': entry_up == exit_up,
            'complete_entry': True,
            'complete_exit': True,
            'breaks_center': breaks_center,
            'makes_extreme': makes_extreme,
            'previous_center': ({
                'bi_start': previous['bi_start'],
                'bi_end': previous['bi_end'],
                'ZG': previous['ZG'],
                'ZD': previous['ZD'],
            } if previous is not None else None),
        })
        if reasons:
            decisions.append(decision)
            continue

        decision['structure_passed'] = True
        pa, aa, _ = _force(
            dif, hist, bis[entry_idx][3], bis[entry_idx + 1][3], entry_up
        )
        pb, ab, _ = _force(
            dif, hist, bis[exit_idx][3], bis[exit_idx + 1][3], entry_up
        )
        force_passed = _weaker(pa, aa, pb, ab, entry_up, divergence_rate)
        decision.update({
            'entry_force': {'dif_peak': pa, 'macd_area': aa},
            'exit_force': {'dif_peak': pb, 'macd_area': ab},
            'area_ratio': ab / aa if aa > 0 else 0,
            'dif_ratio': abs(pb / pa) if pa != 0 else 0,
            'force_passed': force_passed,
            'passed': force_passed,
        })
        if not force_passed:
            reasons.append('结构成立，但完整离开段的MACD力度未衰减')
        decisions.append(decision)

    return decisions


def detect_structural_divergences_strict(
    bis, centers, dif, hist, divergence_rate=None
):
    """只返回通过 V3 结构门和完整走势力度比较的背驰事件。"""
    events = []
    for gate in evaluate_structure_gates(
        bis, centers, dif, hist, divergence_rate=divergence_rate
    ):
        if not gate['passed']:
            continue

        entry_idx = gate['entry_idx']
        exit_idx = gate['exit_idx']
        center = centers[gate['center_idx']]
        pa = gate['entry_force']['dif_peak']
        pb = gate['exit_force']['dif_peak']
        events.append({
            'mode': gate['mode'],
            'kind': gate['kind'],
            'oidx': bis[exit_idx + 1][3],
            'center_idx': gate['center_idx'],
            'A_idx': entry_idx,
            'B_idx': exit_idx,
            'area_ratio': gate['area_ratio'],
            'dif_ratio': gate['dif_ratio'],
            'structure_gate': gate,
            **_consolidation_quality(
                dif,
                bis[center['bi_start']][3],
                bis[center['bi_end'] + 1][3],
                pa,
                pb,
                (center['ZG'] - center['ZD']) / center['ZD'] * 100
                if center['ZD'] > 0 else 0,
            ),
        })

    events.sort(key=lambda event: event['oidx'])
    return events


# 保留旧实现供历史对照，但所有生产入口从这里起都使用严格结构门。
detect_divergences_legacy = detect_divergences


def detect_divergences(bis, centers, dif, hist, divergence_rate=None):
    return detect_structural_divergences_strict(
        bis, centers, dif, hist, divergence_rate=divergence_rate
    )


# ============================================================
# 对外接口 (兼容V61原版)
# ============================================================

def chan_centers(bars, si, chan_window=None, bi_min_gap=None):
    """
    对外接口 — 兼容V61原版调用方式
    返回 (centers, bis, s_win)
    """
    if chan_window is None:
        chan_window = CHAN_WINDOW
    cw = min(chan_window, si + 1)
    s_win = si - cw + 1

    # V2: 传入volume进行合并
    volumes = bars.get('volume') if isinstance(bars, dict) else None
    merged = merge_inclusion(
        bars['high'][s_win:si + 1],
        bars['low'][s_win:si + 1],
        volumes[s_win:si + 1] if volumes else None
    )

    # V2: 笔构建传入merged和bars用于峰值验证和笔破坏检测
    sub_bars = {k: v[s_win:si + 1] for k, v in bars.items()} if isinstance(bars, dict) else None
    fr = find_fractals(merged)
    bis = build_bis(fr, bi_min_gap=bi_min_gap, merged=merged, bars=sub_bars)

    centers = find_centers(bis)
    return centers, bis, s_win


def relevant_center(centers, s_win, di):
    """兼容V61: 找到在di之前形成的最近中枢"""
    best = None
    for cen in centers:
        if s_win + cen['x_end'] < di:
            best = cen
    return best


def classify_form(amp, n_bi, narrow_pct=20.0):
    """兼容V61: 中枢形态分类"""
    if amp <= narrow_pct:
        return '一类·窄幅中枢'
    if n_bi <= 3:
        return '二类·标准中枢'
    return '三类·延伸中枢'


def analyze(highs, lows, closes, volumes=None):
    """
    对外接口 — 兼容V61原版, 返回增强结果
    返回 (bis, centers, dif, dea, hist, divs)

    V2增强:
      - divs中每个事件包含 area_ratio 和 dif_ratio 字段
      - centers中包含 combined 标记
      - 支持volumes参数
    """
    bars = {'high': highs, 'low': lows, 'close': closes}
    if volumes is not None:
        bars['volume'] = volumes

    merged = merge_inclusion(highs, lows, volumes)
    fr = find_fractals(merged)
    bis = build_bis(fr, merged=merged, bars=bars)
    centers = find_centers(bis)
    dif, dea, hist = macd(closes)
    divs = detect_divergences(bis, centers, dif, hist)
    return bis, centers, dif, dea, hist, divs


# ============================================================
# V2新增: 评分函数 (兼容scan_divergence.py调用)
# ============================================================

def strength_score(event):
    """
    V2背驰力度评分 — 供scan_divergence.py调用

    评分公式 (V3: 加入整理充分度):
      基础分: 盘整背驰60 / 趋势背驰75
      面积力度: (1-min(面积比,1))*100 * 0.5  (0-50)
      DIF力度: (1-min(DIF比,1))*100 * 0.5    (0-50)
      整理充分度: consolidation_score           (0-20)
      面积比=0给满分(最强背驰信号)

    整理充分度: 中间段波动小+MACD回零轴 → 整理充分 → 背驰更可靠
    """
    base = {'盘整背驰': 60, '趋势背驰': 75}.get(event.get('mode', ''), 60)

    area_ratio = event.get('area_ratio', 1.0)
    dif_ratio = event.get('dif_ratio', 1.0)

    area_score = (1 - min(area_ratio, 1.0)) * 100 * 0.5
    dif_score = (1 - min(dif_ratio, 1.0)) * 100 * 0.5

    consolidation_score = event.get('consolidation_score', 0)

    return base + area_score + dif_score + consolidation_score


def divergence_label(event):
    """背驰确认标签"""
    area_ratio = event.get('area_ratio', 1.0)
    dif_ratio = event.get('dif_ratio', 1.0)

    if area_ratio < 0.01 and dif_ratio < 0.1:
        return '极强背驰'
    elif area_ratio < 0.3:
        return '强背驰'
    else:
        return '背驰'


# ============================================================
# V2新增: recent_top_divergence (兼容V61原版接口)
# ============================================================

def recent_top_divergence(bars, n_recent=20, bi_gap=None):
    """兼容V61: 检测最近的顶背驰"""
    n = len(bars['close'])
    if n < 30:
        return ''

    volumes = bars.get('volume') if isinstance(bars, dict) else None
    merged = merge_inclusion(bars['high'], bars['low'],
                             volumes if volumes else None)
    bis = build_bis(find_fractals(merged), bi_min_gap=bi_gap,
                    merged=merged, bars=bars)
    if len(bis) < 4:
        return ''

    centers = find_centers(bis)
    dif, dea, hist = macd(bars['close'])
    divs = detect_divergences(bis, centers, dif, hist)

    tops = [e for e in divs if e['kind'] == 'top' and e['oidx'] >= n - n_recent]
    if tops:
        return tops[-1]['mode']
    return ''


def simple_top_div_lookback(bars, di, lookback=30, hist_ratio=0.70):
    """兼容V61: 简单顶背驰检测"""
    if di < lookback or di < 26:
        return False
    start = max(0, di - lookback)
    high_window = bars['high'][start:di]
    if not high_window:
        return False
    cur_high = bars['high'][di]
    if cur_high <= max(high_window) * 1.01:
        return False
    closes = bars['close'][:di + 1]
    e12 = ema_series(closes, 12)
    e26 = ema_series(closes, 26)
    dif_s = [e12[i] - e26[i] for i in range(len(closes))]
    dea_s = ema_series(dif_s, 9)
    hist_s = [2.0 * (dif_s[i] - dea_s[i]) for i in range(len(closes))]
    if hist_s[di] <= 0:
        return False
    prev_peak = max(hist_s[start:di])
    if prev_peak <= 0.001:
        return False
    return hist_s[di] < prev_peak * hist_ratio


# ============================================================
# V2新增: 配置接口
# ============================================================

def configure(**kwargs):
    """
    动态配置V2参数 (运行时覆盖全局默认值)

    可配置项:
      chan_window: 中枢回看窗口 (默认120)
      bi_min_gap: 笔最小K线间隔 (默认6)
      min_bi_len: 一笔最小K线数 (默认6)
      divergence_rate: 背驰力度倍率 (默认1.0)
      fx_check_method: 分型验证模式 (默认'strict')
      bi_end_is_peak: 笔峰值验证 (默认True)
      zs_need_combine: 中枢合并 (V3默认False；开启会绕过严格结构门)
      zs_combine_mode: 中枢合并模式 (默认'zs')
      one_bi_zs: 一笔中枢 (默认False)
      end_bi_break: 背驰突破验证 (默认True)
      --- V2.1新增 ---
      dif_extend: DIF极值搜索扩展窗口 (默认3)
      zs_platform_merge: 平台中枢合并 (V3默认False)
      zs_platform_gap: 平台合并最大间隔笔数 (默认2)
      destruction_mode: 破坏判断模式 (默认'force')
      divergence_lookback: 趋势背离回看窗口 (默认120)
      divergence_min_lows: 趋势背离最少低点数 (默认3)
      divergence_dif_window: 趋势背离DIF搜索窗口 (默认5)
      divergence_recency: 趋势背离forming判定recency (默认15)
    """
    global CHAN_WINDOW, BI_MIN_GAP, MIN_BI_LEN, DIVERGENCE_RATE
    global FX_CHECK_METHOD, BI_END_IS_PEAK, ZS_NEED_COMBINE
    global ZS_COMBINE_MODE, ONE_BI_ZS, END_BI_BREAK
    global DIF_EXTEND, ZS_PLATFORM_MERGE, ZS_PLATFORM_GAP, DESTRUCTION_MODE
    global DIVERGENCE_LOOKBACK, DIVERGENCE_MIN_LOWS, DIVERGENCE_DIF_WINDOW, DIVERGENCE_RECENCY

    config_map = {
        'chan_window': 'CHAN_WINDOW',
        'bi_min_gap': 'BI_MIN_GAP',
        'min_bi_len': 'MIN_BI_LEN',
        'divergence_rate': 'DIVERGENCE_RATE',
        'fx_check_method': 'FX_CHECK_METHOD',
        'bi_end_is_peak': 'BI_END_IS_PEAK',
        'zs_need_combine': 'ZS_NEED_COMBINE',
        'zs_combine_mode': 'ZS_COMBINE_MODE',
        'one_bi_zs': 'ONE_BI_ZS',
        'end_bi_break': 'END_BI_BREAK',
        'dif_extend': 'DIF_EXTEND',
        'zs_platform_merge': 'ZS_PLATFORM_MERGE',
        'zs_platform_gap': 'ZS_PLATFORM_GAP',
        'destruction_mode': 'DESTRUCTION_MODE',
        'divergence_lookback': 'DIVERGENCE_LOOKBACK',
        'divergence_min_lows': 'DIVERGENCE_MIN_LOWS',
        'divergence_dif_window': 'DIVERGENCE_DIF_WINDOW',
        'divergence_recency': 'DIVERGENCE_RECENCY',
    }

    for key, value in kwargs.items():
        if key in config_map:
            globals()[config_map[key]] = value

    return {k: globals()[v] for k, v in config_map.items()}


# ============================================================
# V2新增: 自检/调试接口
# ============================================================

def get_config():
    """获取当前所有配置项"""
    return {
        'chan_window': CHAN_WINDOW,
        'bi_min_gap': BI_MIN_GAP,
        'min_bi_len': MIN_BI_LEN,
        'divergence_rate': DIVERGENCE_RATE,
        'fx_check_method': FX_CHECK_METHOD,
        'bi_end_is_peak': BI_END_IS_PEAK,
        'zs_need_combine': ZS_NEED_COMBINE,
        'zs_combine_mode': ZS_COMBINE_MODE,
        'one_bi_zs': ONE_BI_ZS,
        'end_bi_break': END_BI_BREAK,
        'dif_extend': DIF_EXTEND,
        'zs_platform_merge': ZS_PLATFORM_MERGE,
        'zs_platform_gap': ZS_PLATFORM_GAP,
        'destruction_mode': DESTRUCTION_MODE,
        'divergence_lookback': DIVERGENCE_LOOKBACK,
        'divergence_min_lows': DIVERGENCE_MIN_LOWS,
        'divergence_dif_window': DIVERGENCE_DIF_WINDOW,
        'divergence_recency': DIVERGENCE_RECENCY,
    }


def get_version_info():
    """获取版本信息"""
    return {
        'version': '3.0.0-structure-gate',
        'name': 'chanlun_v2',
        'description': '缠论背驰 V3 严格结构门；MACD只在完整结构后比较力度',
        'v3_structure_gate': [
            '无中枢不判缠论背驰',
            '只比较同级别、同方向、完整进入段与完整离开段',
            '单中枢a+A+b归为盘整背驰；两个同向非重叠中枢归为趋势背驰',
            '未完成离开段只能observing，不能confirmed或PASS',
            '价格-DIF背离仅作上下文，不能独立进入结构候选池',
            '默认关闭中枢合并与平台合并，保留同级别中枢序列',
        ],
        'fixes': [
            '#1 K线合并方向判断 (czsc 3根K线法)',
            '#2 一字K线处理 (chan.py)',
            '#3 成交量合并',
            '#4 分型交替强制 (czsc) + 4种验证模式 (chan.py)',
            '#5 笔峰值验证 bi_end_is_peak (chan.py) [高危]',
            '#6 笔破坏检测 (czsc) [高危]',
            '#7 min_bi_len=6 (czsc标准)',
            '#8 中枢合并 zs/peak模式 (chan.py)',
            '#9 中枢有效性验证 is_valid (czsc)',
            '#10 end_bi_break背驰突破验证 (chan.py) [高危]',
            '#11 盘整背驰中枢归属检查 (chan.py) [高危]',
            '#12 半笔面积 Cal_MACD_half (chan.py)',
            '#13 divergence_rate可配 (chan.py)',
        ],
        'sources': {
            'V61': 'V61选股器 chanlun.py (281行)',
            'chan.py': 'Vespa314/zh3wave (5300行)',
            'czsc': 'zengbin93/waditu (Rust+PyO3)',
        }
    }


# ============================================================
# V2新增: 可操作背驰检测 (actionable divergence)
# ============================================================
# 检测两类有操作价值的底背驰:
#   1. forming — 正在形成中: 最后一笔是下跌笔(top→current), MACD力度已衰减
#      → 底分型尚未确认, 但背驰条件已满足, 是最佳潜伏时机
#   2. confirmed — 刚确认: 底分型已形成且在最近N根K线内
#      → 下跌笔已结束, 反弹已开始, 适合追涨
# ------------------------------------------------------------

def detect_actionable_divergences(bis, centers, dif, hist, closes, max_recency=5):
    """
    检测可操作的底背驰 — 包括正在形成中的和刚确认的

    参数:
      bis, centers, dif, hist: analyze() 的返回值
      closes: 收盘价列表
      max_recency: 刚确认背驰的最大允许距离(默认5根K线)

    返回: list of dict, 每项包含:
      - status: 'forming' (正在形成) 或 'confirmed' (刚确认)
      - mode: 背驰类型
      - score: 力度评分
      - area_ratio, dif_ratio: 力度比值
      - oidx: 背驰位置(原始K线索引)
      - current_price: 当前价格
      - div_price: 背驰点价格
      - price_change: 从背驰点到现在的涨跌幅(%)
    """
    n = len(closes)
    if n < 30 or len(bis) < 4:
        return []

    # 先用标准检测获取已确认的背驰
    all_divs = detect_divergences(bis, centers, dif, hist)
    bottom_divs = [d for d in all_divs if d['kind'] == 'bottom']

    actionable = []

    # ============ 1. 检测刚确认的底背驰 (confirmed) ============
    for d in bottom_divs:
        # recency=0 表示信号落在最后一根K线。旧实现用 n-idx，
        # 会系统性多算1根，使边界信号被错过。
        recency = (n - 1) - d['oidx']
        if recency > max_recency:
            continue

        score = strength_score(d)
        div_price = closes[d['oidx']]
        current_price = closes[-1]
        price_change = (current_price - div_price) / div_price * 100 if div_price > 0 else 0

        # === V2.1改进: 力度优先的破坏判断 ===
        # 原版: current_price < div_price * 0.97 → 直接判死
        # 改进: 价格新低时, 检查MACD绿柱面积是否也放大
        #   - 中枢背驰: 如果离开段力度未放大 → 背驰仍有效(价格新低但力度衰减)
        #   - 盘整背驰: 保持原版价格判断(结构更简单)
        if current_price < div_price * 0.97:
            if DESTRUCTION_MODE == 'force' and d['mode'] in ('中枢背驰', '两中枢背驰') and 'B_idx' in d:
                # 中枢背驰: 力度优先判断
                b_idx = d['B_idx']
                _, b_area, b_half = _force(dif, hist, bis[b_idx][3], bis[b_idx + 1][3], up=False)
                b_area_eff = max(b_area, b_half)
                # 背驰点到当前的MACD绿柱面积
                post_area = -sum(x for x in hist[d['oidx']:n] if x < 0)
                # 如果力度未显著放大(<1.5倍), 背驰仍有效
                if b_area_eff > 0 and post_area < b_area_eff * 1.5:
                    pass  # 力度未放大, 背驰延伸, 保留
                else:
                    continue  # 力度放大, 背驰被破坏
            else:
                # 盘整背驰或price模式: 保持原版价格判断
                continue

        actionable.append({
            'status': 'confirmed',
            'mode': d['mode'],
            'score': round(score, 1),
            'label': divergence_label(d),
            'area_ratio': d.get('area_ratio', 0),
            'dif_ratio': d.get('dif_ratio', 0),
            'oidx': d['oidx'],
            'recency': recency,
            'current_price': current_price,
            'div_price': div_price,
            'price_change': round(price_change, 2),
            'dif_reset_ratio': d.get('dif_reset_ratio', 0),
            'fluctuation_pct': d.get('fluctuation_pct', 0),
            'consolidation_score': d.get('consolidation_score', 0),
            'consolidation_label': d.get('consolidation_label', '不足'),
        })

    # ============ 2. 检测正在形成中的底背驰 (forming) ============
    # 最后一根分型是 top → 当前处于下跌笔中 (top → current price)
    # 此时底分型尚未确认, 但可以检查MACD力度是否已衰减
    if len(bis) >= 5:
        last_fx = bis[-1]
        last_idx = len(bis) - 1

        if last_fx[0] == 'top':
            # bis[-1] = top (最后一根分型, 当前下跌笔的起点)
            # bis[-2] = bottom (上一根下跌笔的终点)
            # bis[-3] = top (上一根下跌笔的起点)
            # 上一根下跌笔: bis[-3](top) → bis[-2](bottom)
            # 当前未完成下跌笔: bis[-1](top) → current

            prev_top = bis[-3]
            prev_bottom = bis[-2]
            current_top = bis[-1]  # 当前下跌笔的起点

            if prev_top[0] == 'top' and prev_bottom[0] == 'bottom':
                c0 = current_top[3]   # 当前下跌笔起点的orig_idx
                c1 = n - 1            # 最新K线
                bars_in_current_bi = c1 - c0  # 当前下跌笔已走了多少根K线

                # === 关键修复 #1: 当前下跌笔必须有足够的K线才能判断背驰 ===
                # 至少需要 MIN_BI_LEN(6) 根K线, 否则MACD力度尚未发展
                if bars_in_current_bi < MIN_BI_LEN:
                    pass  # 跳过forming检测, 下跌笔太短
                else:
                    prev_bottom_val = prev_bottom[2]  # 上一根下跌笔的低点价格
                    current_price_now = closes[-1]

                    # === 关键修复 #2: 当前价格必须接近前低 ===
                    # 只有当当前价格跌到前低附近(3%以内)时, 才有意义比较力度
                    # 如果当前价格离前低还很远, 说明下跌笔还没发展到可以判断背驰的程度
                    price_near_prev_low = current_price_now <= prev_bottom_val * 1.03

                    if not price_near_prev_low:
                        pass  # 当前价格离前低太远, 跳过
                    else:
                        # === 关键修复 #3: 检查前低是否已被跌破(背驰已被打掉) ===
                        # 如果在上一根下跌笔(bis[-3]→bis[-2])之后, 有更低的低点
                        # 说明那个下跌笔的背驰已被新低打掉, 不能作为对比基准
                        prev_bottom_oi = prev_bottom[3]
                        # 检查bis[-2]之后是否还有更低的bottom分型
                        lower_low_after = False
                        for bi_check in bis[last_idx-1:]:  # bis[-2]之后的笔
                            if isinstance(bi_check, (list, tuple)):
                                if bi_check[0] == 'bottom' and bi_check[2] < prev_bottom_val:
                                    lower_low_after = True
                                    break

                        # 如果前低已被跌破, 用最新的低点作为对比基准
                        if lower_low_after:
                            # 找到bis[-2]之后最低的bottom分型作为新的对比基准
                            valid_tops = []
                            valid_bottoms = []
                            for i in range(len(bis)-2, -1, -1):
                                bi_c = bis[i]
                                if isinstance(bi_c, (list, tuple)):
                                    if bi_c[0] == 'top':
                                        valid_tops.append((i, bi_c))
                                    elif bi_c[0] == 'bottom':
                                        valid_bottoms.append((i, bi_c))
                                        if len(valid_bottoms) >= 1 and len(valid_tops) >= 1:
                                            break
                            if valid_tops and valid_bottoms:
                                prev_top = valid_tops[0][1]
                                prev_bottom = valid_bottoms[0][1]

                        # === 关键修复 #4: 结构破坏检测 ===
                        # 如果当前下跌笔的起点(顶)远高于前一下跌笔的起点(>10%),
                        # 说明中间反弹过大, 旧结构已被向上突破破坏,
                        # 当前下跌笔是新的独立下跌, 不是原结构的延续背驰
                        current_top_val = current_top[2]
                        prev_top_val = prev_top[2]
                        structure_broken = (
                            prev_top_val > 0 and
                            current_top_val > prev_top_val * 1.10
                        )

                        # === 关键修复 #5: 下跌笔幅度对比 ===
                        # 如果当前下跌幅度远大于前一下跌笔(>3倍),
                        # 说明是新一笔更大的下跌, 不是同一级别的背驰
                        if not structure_broken:
                            current_drop = current_top_val - closes[-1]
                            prev_drop = prev_top_val - prev_bottom[2]
                            if prev_drop > 0 and current_drop > prev_drop * 3.0:
                                structure_broken = True

                        if not structure_broken:
                            # 计算上一根下跌笔的力度
                            p0 = prev_top[3]  # orig_idx
                            p1 = prev_bottom[3]
                            pa, aa, ha = _force(dif, hist, p0, p1, up=False)
                            aa_eff = max(aa, ha)

                            # 当前未完成下跌笔的力度: current_top → 最新K线
                            pb, ab, hb = _force(dif, hist, c0, c1, up=False)
                            ab_eff = max(ab, hb)

                            # 检查力度衰减 (背驰条件)
                            if aa_eff > 0:
                                area_ratio = ab_eff / aa_eff
                                dif_ratio = abs(pb / pa) if pa != 0 else 0

                                # 背驰条件: 面积衰减 AND DIF背离
                                is_diverging = _weaker(pa, aa_eff, pb, ab_eff, False)

                                if is_diverging:
                                    # 检查中枢关系 (如果有中枢)
                                    mode = '盘整背驰'  # 默认
                                    center_ref = None  # 用于整理充分度计算

                                    # 检查是否有中枢在当前下跌笔之前
                                    for ci, c in enumerate(centers):
                                        if c['bi_end'] >= last_idx - 2 and c['bi_start'] <= last_idx - 3:
                                            # #10: end_bi_break验证 — 当前价格需要突破中枢ZD
                                            if END_BI_BREAK:
                                                if closes[-1] >= c['ZD']:
                                                    mode = '中枢背驰'
                                                    center_ref = c
                                                    if ci >= 1:
                                                        pv = centers[ci - 1]
                                                        if c['ZG'] < pv['ZD']:
                                                            mode = '两中枢背驰'
                                            else:
                                                mode = '中枢背驰'
                                                center_ref = c
                                                if ci >= 1:
                                                    pv = centers[ci - 1]
                                                    if c['ZG'] < pv['ZD']:
                                                        mode = '两中枢背驰'
                                            break

                                    # 整理充分度: 中枢背驰用中枢范围, 盘整背驰用反弹笔
                                    if center_ref is not None:
                                        consol = _consolidation_quality(
                                            dif,
                                            bis[center_ref['bi_start']][3],
                                            bis[center_ref['bi_end']][3],
                                            pa, pb,
                                            (center_ref['ZG'] - center_ref['ZD']) / center_ref['ZD'] * 100 if center_ref['ZD'] > 0 else 0
                                        )
                                    else:
                                        mid_fluct = abs(current_top[2] - prev_bottom[2]) / prev_bottom[2] * 100 if prev_bottom[2] > 0 else 0
                                        consol = _consolidation_quality(
                                            dif,
                                            prev_bottom[3], c0,
                                            pa, pb,
                                            mid_fluct
                                        )

                                    score = strength_score({
                                        'mode': mode,
                                        'area_ratio': area_ratio,
                                        'dif_ratio': dif_ratio,
                                        'consolidation_score': consol['consolidation_score'],
                                    })

                                    current_price = closes[-1]
                                    forming_price = closes[c0]

                                    actionable.append({
                                        'status': 'forming',
                                        'mode': mode,
                                        'score': round(score, 1),
                                        'label': divergence_label({
                                            'area_ratio': area_ratio,
                                            'dif_ratio': dif_ratio,
                                        }),
                                        'area_ratio': round(area_ratio, 4),
                                        'dif_ratio': round(dif_ratio, 4),
                                        'oidx': c0,  # 背驰起点(当前下跌笔的top)
                                        'recency': 0,  # 正在形成, recency=0
                                        'current_price': current_price,
                                        'div_price': forming_price,
                                        'price_change': round((current_price - forming_price) / forming_price * 100, 2) if forming_price > 0 else 0,
                                        'bars_in_bi': bars_in_current_bi,
                                        'dif_reset_ratio': consol['dif_reset_ratio'],
                                        'fluctuation_pct': consol['fluctuation_pct'],
                                        'consolidation_score': consol['consolidation_score'],
                                        'consolidation_label': consol['consolidation_label'],
                                })

    # 按评分排序
    actionable.sort(key=lambda x: x['score'], reverse=True)
    return actionable


# ============================================================
# V3严格的当下信号状态
# ============================================================

detect_actionable_divergences_legacy = detect_actionable_divergences


def _detect_structure_observations(bis, centers, dif, hist, closes):
    """
    识别“假设的背驰段”，只允许返回 observing，不允许确认或 PASS。

    当前未完成下跌段必须是最近中枢后的第一离开段，且已跌破中枢下沿
    和进入段低点。MACD衰减只用来说明值得观察，不能补足底分型缺失。
    """
    if len(closes) < 30 or len(bis) < 5 or not centers:
        return []
    if bis[-1][0] != 'top':
        return []

    center_idx = None
    for ci in range(len(centers) - 1, -1, -1):
        if centers[ci]['bi_end'] + 1 == len(bis) - 1:
            center_idx = ci
            break
    if center_idx is None:
        return []

    center = centers[center_idx]
    if center.get('combined') or center.get('n_bi', 0) >= 9:
        return []

    entry_idx = center['bi_start'] - 1
    if entry_idx < 0 or _leg_is_up(bis, entry_idx):
        return []

    leg_start = bis[-1][3]
    leg_end = len(closes) - 1
    bars_in_leg = leg_end - leg_start
    if bars_in_leg < MIN_BI_LEN:
        return []

    current_price = closes[-1]
    entry_low = bis[entry_idx + 1][2]
    if current_price >= center['ZD'] or current_price >= entry_low:
        return []

    mode, previous, mode_error = _classify_strict_mode(
        centers, center_idx, up=False
    )
    if mode_error or mode is None:
        return []

    pa, aa, _ = _force(
        dif, hist, bis[entry_idx][3], bis[entry_idx + 1][3], up=False
    )
    pb, ab, _ = _force(dif, hist, leg_start, leg_end, up=False)
    if not _weaker(pa, aa, pb, ab, up=False):
        return []

    area_ratio = ab / aa if aa > 0 else 0
    dif_ratio = abs(pb / pa) if pa != 0 else 0
    consolidation = _consolidation_quality(
        dif,
        bis[center['bi_start']][3],
        bis[center['bi_end'] + 1][3],
        pa,
        pb,
        (center['ZG'] - center['ZD']) / center['ZD'] * 100
        if center['ZD'] > 0 else 0,
    )
    gate = {
        'passed': False,
        'structure_passed': False,
        'force_passed': True,
        'state': 'partial_exit_unconfirmed',
        'reasons': ['离开段尚无确认底分型，完整性条件未满足'],
        'level_basis': '同一笔级代理（操作级别的次级走势段）',
        'center_idx': center_idx,
        'entry_idx': entry_idx,
        'exit_idx': None,
        'same_direction': True,
        'complete_entry': True,
        'complete_exit': False,
        'breaks_center': True,
        'makes_extreme': True,
        'center': {
            'bi_start': center['bi_start'],
            'bi_end': center['bi_end'],
            'ZG': center['ZG'],
            'ZD': center['ZD'],
            'n_bi': center['n_bi'],
            'level_state': center.get('level_state', 'base'),
        },
        'previous_center': ({
            'bi_start': previous['bi_start'],
            'bi_end': previous['bi_end'],
            'ZG': previous['ZG'],
            'ZD': previous['ZD'],
        } if previous is not None else None),
    }
    score = strength_score({
        'mode': mode,
        'area_ratio': area_ratio,
        'dif_ratio': dif_ratio,
        'consolidation_score': consolidation['consolidation_score'],
    })
    return [{
        'status': 'observing',
        'actionable': False,
        'mode': mode,
        'kind': 'bottom',
        'module': '结构背驰',
        'score': round(score, 1),
        'label': '假设背驰段',
        'area_ratio': round(area_ratio, 4),
        'dif_ratio': round(dif_ratio, 4),
        'oidx': leg_end,
        'leg_start_oidx': leg_start,
        'recency': 0,
        'current_price': current_price,
        'div_price': current_price,
        'price_change': 0.0,
        'bars_in_bi': bars_in_leg,
        'structure_gate': gate,
        'confirmation_condition': '该离开段形成确认底分型，且完整段MACD力度仍弱于进入段',
        'invalidation_condition': '走势延伸导致力度不再衰减，或中枢扩张/级别升级',
        **consolidation,
    }]


def detect_actionable_divergences(bis, centers, dif, hist, closes, max_recency=5):
    """V3：确认背驰与未完成观察严格分层。"""
    n = len(closes)
    if n < 30 or len(bis) < 4:
        return []

    actionable = []
    for event in detect_divergences(bis, centers, dif, hist):
        if event['kind'] != 'bottom':
            continue
        recency = (n - 1) - event['oidx']
        if recency < 0 or recency > max_recency:
            continue

        div_price = closes[event['oidx']]
        current_price = closes[-1]
        # 已确认低点被再创新低，说明原离开段仍在延伸，旧确认失效。
        if current_price < div_price - 1e-9:
            continue

        actionable.append({
            'status': 'confirmed',
            'actionable': True,
            'mode': event['mode'],
            'kind': 'bottom',
            'module': '结构背驰',
            'score': round(strength_score(event), 1),
            'label': divergence_label(event),
            'area_ratio': round(event.get('area_ratio', 0), 4),
            'dif_ratio': round(event.get('dif_ratio', 0), 4),
            'oidx': event['oidx'],
            'recency': recency,
            'current_price': current_price,
            'div_price': div_price,
            'price_change': round(
                (current_price - div_price) / div_price * 100, 2
            ) if div_price > 0 else 0,
            'structure_gate': event['structure_gate'],
            'confirmation_condition': '结构门已通过；等待相邻低级别买点用于人工精确定位',
            'invalidation_condition': '跌破该确认低点，或后续结构显示级别升级',
            'dif_reset_ratio': event.get('dif_reset_ratio', 0),
            'fluctuation_pct': event.get('fluctuation_pct', 0),
            'consolidation_score': event.get('consolidation_score', 0),
            'consolidation_label': event.get('consolidation_label', '不足'),
        })

    actionable.extend(_detect_structure_observations(
        bis, centers, dif, hist, closes
    ))
    actionable.sort(
        key=lambda item: (item['status'] == 'confirmed', item['score']),
        reverse=True,
    )
    return actionable


# ============================================================
# V2.1趋势指标背离（V3仅保留为研究上下文，禁止进入结构候选池）
# ============================================================
# 背离 vs 背驰 (用户明确定义):
#   背离 = 指标和股价相反运行 (价格走低, MACD回升) — 看趋势, 不依赖结构
#   背驰 = 两个同方向的笔对比, 中间隔一笔或中枢 — 看结构
# 两者互补: 背离检测更宏观(能捕捉长期趋势), 背驰检测更精确(定位结构点)
# ------------------------------------------------------------


def _find_swing_lows(closes, start, end, window=5):
    """
    从收盘价序列找局部极小值 (swing lows)
    不依赖笔/中枢结构, 直接在价格序列上找

    参数:
      closes: 收盘价列表
      start, end: 搜索范围
      window: 局部极值窗口(前后各window根K线)

    返回: [(idx, price), ...] 按索引排序
    """
    lows = []
    for i in range(start + window, min(end, len(closes)) - window):
        seg = closes[i - window:i + window + 1]
        if closes[i] == min(seg) and closes[i] < closes[i - 1] and closes[i] < closes[i + 1]:
            lows.append((i, closes[i]))
    return lows


def _calc_divergence_trend_score(price_lows, dif_lows):
    """
    趋势背离强度评分

    评分维度:
      - DIF回升力度 (0-50): DIF从最深负值回升的幅度
      - 价格下跌幅度 (0-30): 价格从第一个低点到最后低点的跌幅
      - 低点数量 (0-20): 参与背离的低点越多, 趋势越确认

    总分: 0-100 (基础分60, 因为趋势背离比盘整背驰更宏观但不如中枢背驰精确)
    """
    if len(price_lows) < 2 or len(dif_lows) < 2:
        return 0

    # DIF回升力度: (最后DIF - 第一个DIF) / |第一个DIF|
    first_dif = dif_lows[0]
    last_dif = dif_lows[-1]
    if first_dif != 0:
        dif_improvement = (last_dif - first_dif) / abs(first_dif)
    else:
        dif_improvement = 0
    dif_score = min(abs(dif_improvement) * 50, 50)

    # 价格下跌幅度
    first_price = price_lows[0][1]
    last_price = price_lows[-1][1]
    if first_price > 0:
        price_drop = (first_price - last_price) / first_price
    else:
        price_drop = 0
    price_score = min(price_drop * 100, 30)

    # 低点数量
    n_lows = len(price_lows)
    count_score = min((n_lows - 2) * 10, 20)

    # 基础分60 (介于盘整背驰50和中枢背驰68之间)
    return 60 + dif_score + price_score + count_score


def detect_divergence_trend(
    closes, dif, hist, bis=None, lookback=None, min_lows=None,
    max_recency=None,
):
    """
    趋势背离检测 — 不依赖笔/中枢结构，直接看价格趋势与MACD趋势的相反运行

    背离定义: 价格低点持续走低，DIF低点持续回升（向零轴靠近）
    与背驰不同: 背离看趋势，背驰看结构（两笔对比）

    算法:
      1. 找价格低点 (swing lows) — 用笔的底分型或直接在close序列找局部极值
      2. 过滤: 只保留递减的价格低点 (每个比前一个更低, 过滤反弹噪音)
      3. 为每个价格低点找附近的DIF极值 (允许±N根K线偏差, 符合人类视觉)
      4. 检查DIF整体趋势: 第一个DIF低点 vs 最后一个DIF低点, 允许中间有波动
      5. 评分并返回

    参数:
      closes: 收盘价列表
      dif: DIF线列表
      hist: MACD柱列表
      bis: 可选，已有的笔列表(用底分型作为swing lows, 更精确)
      lookback: 回看窗口(默认DIVERGENCE_LOOKBACK=120)
      min_lows: 最少低点数(默认DIVERGENCE_MIN_LOWS=3)
      max_recency: 最后一个低点距离最新K线的最大根数。
                   None表示只做历史研究、不做时效过滤。

    返回: list of dict, 每项包含:
      - status: 'forming' (正在形成) 或 'confirmed' (已确认)
      - mode: '趋势背离'
      - score: 背离强度评分
      - price_lows: [(idx, price), ...] 价格低点序列
      - dif_lows: [dif_value, ...] 对应DIF低点
      - n_lows: 低点数量
      - oidx: 最后一个低点位置
      - recency: 距今天数
      - current_price, div_price, price_change
    """
    n = len(closes)
    if n < 30:
        return []

    if lookback is None:
        lookback = DIVERGENCE_LOOKBACK
    if min_lows is None:
        min_lows = DIVERGENCE_MIN_LOWS

    start = max(0, n - lookback)

    # 找价格低点
    if bis is not None and len(bis) > 0:
        # 用笔的底分型作为swing lows (更精确)
        all_lows = [(b[3], b[2]) for b in bis
                    if b[0] == 'bottom' and b[3] >= start]
    else:
        # 从close序列找局部极值
        all_lows = _find_swing_lows(closes, start, n)

    if len(all_lows) < min_lows:
        return []

    # 为每个价格低点找对应的DIF低点 (人类视角: 低点附近的双线低点)
    dif_window = DIVERGENCE_DIF_WINDOW
    all_difs = []
    for idx, price in all_lows:
        w_start = max(0, idx - dif_window)
        w_end = min(n, idx + dif_window + 1)
        seg = dif[w_start:w_end]
        dif_low = min(seg) if seg else dif[idx]
        all_difs.append(dif_low)

    # 过滤: 只保留递减的价格低点 (每个比前一个更低, 过滤反弹噪音)
    # 人类视觉: 只关注不断创新低的低点, 忽略中间的反弹高点
    filtered_lows = [all_lows[0]]
    filtered_difs = [all_difs[0]]
    for i in range(1, len(all_lows)):
        if all_lows[i][1] < filtered_lows[-1][1]:
            filtered_lows.append(all_lows[i])
            filtered_difs.append(all_difs[i])

    if len(filtered_lows) < min_lows:
        return []

    # 检查DIF整体趋势: 最后一个DIF低点 vs 第一个DIF低点
    # 允许中间有波动, 只要整体趋势是向上的(DIF回升)
    first_dif = filtered_difs[0]
    last_dif = filtered_difs[-1]

    if last_dif <= first_dif:
        # DIF整体未回升, 不是背离
        return []

    # 进一步检查: DIF低点序列中, 递增的占比应>50%
    increasing_count = sum(1 for i in range(len(filtered_difs) - 1)
                           if filtered_difs[i + 1] > filtered_difs[i])
    total_pairs = len(filtered_difs) - 1
    if total_pairs > 0 and increasing_count / total_pairs < 0.5:
        # 递增占比不足50%, 趋势不够明确
        return []

    # 背离确认!
    seq_lows = filtered_lows
    seq_difs = filtered_difs

    last_low_idx = seq_lows[-1][0]
    last_low_price = seq_lows[-1][1]
    recency = (n - 1) - last_low_idx

    # 趋势背离使用已确认的swing low，语义上只能是confirmed。
    # “正在形成”需要另外对未完成的当前下跌段建模，不能用
    # “低点距今较近”来冒充。
    if max_recency is not None and recency > max_recency:
        return []
    status = 'confirmed'

    score = _calc_divergence_trend_score(seq_lows, seq_difs)

    # 背离标签
    if first_dif != 0:
        dif_improvement = abs((last_dif - first_dif) / first_dif)
    else:
        dif_improvement = 0

    if dif_improvement > 0.5:
        label = '极强背离'
    elif dif_improvement > 0.2:
        label = '强背离'
    else:
        label = '背离'

    current_price = closes[-1]

    return [{
        'status': status,
        'mode': '趋势背离',
        'kind': 'bottom',
        'score': round(score, 1),
        'label': label,
        'price_lows': [(idx, round(price, 2)) for idx, price in seq_lows],
        'dif_lows': [round(d, 4) for d in seq_difs],
        'n_lows': len(seq_lows),
        'dif_improvement': round(dif_improvement, 4),
        'dif_increasing_ratio': round(increasing_count / total_pairs, 2) if total_pairs > 0 else 0,
        'oidx': last_low_idx,
        'recency': recency,
        'current_price': current_price,
        'div_price': last_low_price,
        'price_change': round((current_price - last_low_price) / last_low_price * 100, 2) if last_low_price > 0 else 0,
        # 兼容字段
        'area_ratio': 0,
        'dif_ratio': round(abs(last_dif / first_dif) if first_dif != 0 else 0, 4),
    }]


# ============================================================
# V2.1新增: 统一可操作检测 (背离 + 背驰)
# ============================================================

def detect_actionable_unified(bis, centers, dif, hist, closes, max_recency=5):
    """
    V3统一入口：只有结构背驰可以进入候选池。

    普通价格—DIF背离仍可计算，但只能作为 ``indicator_context`` 附着在
    已经通过结构入口的信号上，绝不能独立绕过中枢和完整走势门槛。
    """
    structural = detect_actionable_divergences(
        bis, centers, dif, hist, closes, max_recency=max_recency
    )
    indicator = detect_divergence_trend(
        closes, dif, hist, bis=bis, max_recency=max_recency
    )
    context = indicator[0] if indicator else None
    for item in structural:
        item['module'] = '结构背驰'
        item['indicator_context'] = ({
            'present': True,
            'mode': '价格-DIF背离',
            'oidx': context['oidx'],
            'recency': context['recency'],
            'dif_improvement': context['dif_improvement'],
        } if context else {'present': False})
    return structural
