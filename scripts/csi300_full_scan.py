#!/usr/bin/env python3
"""
沪深300 缠论全量分析 — 完整版
双XGBoost + V4.5 + GZK + 三维评分 + 风控计划 + PE + 宏观
输出: ~/chan_hs300_full_YYYYMMDD.xlsx
"""
import os, sys, csv, time, pickle, argparse
from datetime import datetime
import numpy as np
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REF = os.path.join(HERE, '..', 'references')
MODELS = os.path.join(HERE, '..', 'models')

from data import fetch_kline_a, fetch_a_quotes, load_a_stocks
from chan_engine import analyze as chan_analyze, get_bsp_label
from scorer import extract_features
from macro import load_macro, macro_signal
from sector_heat import sector_signal, get_sector_heat
from volume_sector import volume_analysis
from smc_insight import smc_analysis
from event_calendar import format_calendar
from enhanced_tools import (
    v45_experience_score, gzk_score, compute_3d_score, 
    check_risk, full_enhanced_analysis,
    mainline_score
)

# ═══════════════ Model Loading ═══════════════
_old_model = None
_new_model = None

def load_models():
    global _old_model, _new_model
    if _new_model is None:
        model_path = os.path.join(MODELS, 'chan_xgb_latest.pkl')
        if os.path.exists(model_path):
            with open(model_path, 'rb') as f:
                _new_model = pickle.load(f)
    if _old_model is None:
        old_path = os.path.join(MODELS, 'chan_xgb_56d.pkl')
        if os.path.exists(old_path):
            with open(old_path, 'rb') as f:
                _old_model = pickle.load(f)
    return _old_model, _new_model

def predict_score(feats, model):
    """Predict score using a given XGBoost model"""
    if model is None:
        return None
    try:
        nf = model.n_features_in_
        vec = np.array([[feats[k] for k in sorted(feats.keys())[:nf]]])
        return int(model.predict_proba(vec)[0, 1] * 100)
    except:
        return None

# ═══════════════ CSI 300 Stock List ═══════════════
def load_csi300_stocks():
    codes = []
    with open(os.path.join(REF, 'hs300_stocks.csv')) as f:
        for row in csv.DictReader(f):
            c = row['成分券代码'].strip()
            n = row['成分券名称'].strip().strip('"')
            if 'ST' in n or '退' in n:
                continue
            if c.startswith(('688', '8', '4', '83', '87')):
                continue
            codes.append((c, n))
    return codes

# ═══════════════ PE Batch Query (baostock) ═══════════════
def fetch_pe_batch(stocks, cache_file=None):
    """Batch query peTTM for all stocks via baostock. Returns {code: pe}"""
    if cache_file and os.path.exists(cache_file):
        with open(cache_file, 'rb') as f:
            return pickle.load(f)
    
    import baostock as bs
    bs.login()
    pe_map = {}
    for idx, (code, name) in enumerate(stocks):
        if idx % 50 == 0:
            print(f'    PE查询: {idx}/{len(stocks)}', flush=True)
        try:
            sym = 'sh.' + code if code.startswith('6') else 'sz.' + code
            # baostock day-end data: query last 5 days to catch latest
            from datetime import timedelta
            end_dt = datetime.now() - timedelta(days=1)
            start_dt = end_dt - timedelta(days=5)
            rs = bs.query_history_k_data_plus(sym, 'date,peTTM',
                start_date=start_dt.strftime('%Y-%m-%d'),
                end_date=end_dt.strftime('%Y-%m-%d'),
                frequency='d')
            while rs.next():
                d = rs.get_row_data()
                if len(d) > 1 and d[1]:
                    pe_map[code] = round(float(d[1]), 2)
        except:
            pass
    bs.logout()
    
    if cache_file:
        os.makedirs(os.path.dirname(cache_file) or '.', exist_ok=True)
        with open(cache_file, 'wb') as f:
            pickle.dump(pe_map, f)
    
    return pe_map

# ═══════════════ Main Scan ═══════════════
def main():
    parser = argparse.ArgumentParser(description='沪深300缠论全量分析-完整版')
    parser.add_argument('--min-score', type=int, default=35, help='3D综合评分最低阈值')
    parser.add_argument('--output', type=str, default=None, help='输出路径')
    args = parser.parse_args()

    today = datetime.now().strftime('%Y%m%d')
    out_path = args.output or os.path.expanduser(f'~/chan_hs300_full_{today}.xlsx')

    print(f'🔬 沪深300缠论全量分析 — 完整版 (17模块)')
    print(f'  输出: {out_path}')

    # Load models
    old_model, new_model = load_models()
    print(f'  模型: 旧={old_model is not None}, 新={new_model is not None}')

    # Load stocks
    stocks = load_csi300_stocks()
    print(f'  股票池: {len(stocks)} 只 (CSI 300)')

    # Macro
    try:
        macro = load_macro()
        ms = macro_signal(macro)
        print(f'  宏观: DXY={macro.get("DXY",{}).get("value","?")} | {ms.get("bias","?")}')
    except Exception as e:
        macro = {}
        print(f'  宏观: 获取失败 ({e})')

    # Sector heat
    try:
        heat = get_sector_heat()
        print(f'  板块: {len(heat)} 个')
    except:
        heat = {}

    # PE batch query (cached)
    pe_cache = os.path.expanduser('~/chan_pe_cache.pkl')
    pe_map = fetch_pe_batch(stocks, cache_file=pe_cache)
    print(f'  PE: {len(pe_map)} 只有效')

    # Fetch quotes
    print(f'  获取行情...')
    quotes = fetch_a_quotes([(c, n) for c, n in stocks])
    print(f'  行情: {len(quotes)} 只')

    # Pre-fetch all K-lines via baostock (shared connection, fast)
    import baostock as bs
    bs.login()
    kline_cache = {}
    for idx, (code, name) in enumerate(stocks):
        try:
            sym = 'sh.' + code if code.startswith('6') else 'sz.' + code
            rs = bs.query_history_k_data_plus(sym,
                'date,open,high,low,close,volume',
                start_date='2025-07-01', end_date=datetime.now().strftime('%Y-%m-%d'),
                frequency='d', adjustflag='2')
            rows = []
            while rs.error_code == '0' and rs.next():
                rows.append(rs.get_row_data())
            if len(rows) >= 100:
                dates = [str(r[0]) for r in rows]
                opens = [float(r[1]) for r in rows]
                closes = [float(r[4]) for r in rows]
                highs = [float(r[2]) for r in rows]
                lows = [float(r[3]) for r in rows]
                vols = [float(r[5]) for r in rows]
                kline_cache[code] = (dates, opens, closes, highs, lows, vols)
        except:
            pass
    bs.logout()
    print(f'  K线缓存: {len(kline_cache)} 只')

    # Scan
    name_map = {c: n for c, n in stocks}
    results = []
    
    for idx, (code, name) in enumerate(stocks):
        if code not in quotes:
            continue
        if idx % 10 == 0:
            print(f'    {idx}/{len(stocks)}, found {len(results)}', flush=True)
        
        q = quotes[code]
        px = q['price']

        # Fetch K-line from cache (baostock, preloaded)
        data = kline_cache.get(code)
        if not data:
            continue
        dates, opens, closes, highs, lows, vols = data
        
        # Chan analysis
        try:
            cur, bsp_buy, bsp_types, px2, zs_str, pos = chan_analyze(
                dates, opens, closes, highs, lows, code)
        except Exception as e:
            continue

        # Feature extraction
        feats = extract_features(closes, highs, lows, opens, vols, bsp_buy, bsp_types, cur)

        # Dual XGBoost
        old_xgb = predict_score(feats, old_model)
        new_xgb = predict_score(feats, new_model)

        # V4.5
        try:
            v45 = v45_experience_score(np.array(closes), np.array(highs), np.array(lows), np.array(vols))
            v45_score = v45.get('final_score', 0)
        except:
            v45_score = 0

        # GZK (returns dict with trend/deviation/k_ratio etc, NOT final_score)
        try:
            gzk = gzk_score(np.array(closes), np.array(highs), np.array(lows))
            # Compute GZK composite from available fields
            gzk_val = 0
            trend = gzk.get('trend', '')
            dev = gzk.get('deviation', '')
            k_ratio = gzk.get('k_ratio') or 0
            timing = gzk.get('timing_ok', False)
            # Trend scoring
            if trend == '走强': gzk_val += 30
            elif trend == '震荡': gzk_val += 20
            # Deviation scoring
            if dev == '超跌': gzk_val += 25
            elif dev == '正常': gzk_val += 15
            # K ratio scoring (capped)
            gzk_val += min(abs(k_ratio) * 15, 30)
            # Timing bonus
            if timing: gzk_val += 15
            gzk_val = max(0, min(100, round(gzk_val)))
        except:
            gzk_val = 0

        # 3D Composite — old model calibrated to higher range, favor it
        # Old model: 20-80 (avg 50), New model: 10-77 (avg 31)
        tech_score = max((old_xgb or 0), (new_xgb or 0) * 1.3)
        tech_score = max(0, min(100, tech_score))
        fund_score = max(0, min(100, v45_score * 0.6 + gzk_val * 0.6))
        score3d = compute_3d_score(tech_score, fund_score, 50)

        if score3d['composite'] < args.min_score:
            continue

        # PE from baostock batch query
        pe = pe_map.get(code)

        # YTD
        ytd = (closes[-1] / closes[-120] - 1) * 100 if len(closes) >= 120 else None

        # R:R and Entry/Stop/TP — calculate from 中枢
        label = get_bsp_label(bsp_buy, bsp_types, pos)
        
        # Parse zs for supports/resistances
        supports = []
        resistances = []
        if zs_str:
            for zs_part in zs_str.split(','):
                try:
                    zl, zh = map(float, zs_part.split('~'))
                    supports.append(zl)
                    resistances.append(zh)
                except:
                    pass

        # Calculate entry/stop/TP from最近的 中枢
        entry = None
        stop = None
        tp1 = None
        rr = None
        
        if supports and resistances:
            zl = zh = None
            # First: try to find the zhongshu the stock is currently inside
            for sl, sh in zip(supports, resistances):
                if sl <= px <= sh:
                    zl, zh = sl, sh
                    break
            
            if zl is None:
                # Not inside any zhongshu — find support (below) and resistance (above)
                supports_below = [s for s in supports if s < px]
                resistances_above = [r for r in resistances if r > px]
                
                if supports_below and resistances_above:
                    # Between two zhongshu: use nearest below as support, nearest above as TP
                    zl = max(supports_below)  # closest support below
                    zh = min(resistances_above)  # closest resistance above
                elif supports_below:
                    # Below all zhongshu: use nearest below
                    zl = max(supports_below)
                    zh = resistances[supports.index(zl)] if zl in supports else resistances[-1]
                elif resistances_above:
                    # Above all zhongshu: use nearest above
                    zh = min(resistances_above)
                    zl = supports[resistances.index(zh)] if zh in resistances else supports[0]
                else:
                    # Fallback to nearest
                    nearest_idx = 0
                    min_dist = float('inf')
                    for i, (sl, sh) in enumerate(zip(supports, resistances)):
                        center = (sl + sh) / 2
                        dist = abs(px - center)
                        if dist < min_dist:
                            min_dist = dist
                            nearest_idx = i
                    zl = supports[nearest_idx]
                    zh = resistances[nearest_idx]
            
            if zl is not None and zh is not None and bsp_buy:
                if zl <= px <= zh:
                    # Inside 中枢: entry near lower bound + 10%, stop = lower-3%
                    entry = round(zl + (zh - zl) * 0.1, 2)
                    stop = round(zl * 0.97, 2)
                    tp1 = round(zh, 2)
                elif px < zl:
                    # Below zhongshu: buy at current bargain price, stop based on entry
                    entry = round(px, 2)
                    stop = round(entry * 0.97, 2)
                    tp1 = round(zh, 2)
                else:
                    # Above zhongshu (三买): entry at px, stop at zhongshu upper-3%, TP next leg up
                    entry = round(px, 2)
                    stop = round(zh * 0.97, 2)
                    tp1 = round(zh + (zh - zl), 2)
                if entry > stop and stop > 0:
                    rr = round((tp1 - entry) / (entry - stop), 1)
            elif 'Sell' in label:
                entry = px
                # For Sell: find support below (TP) and resistance above (stop)
                # Use stop above entry as default
                sell_zl = [s for s in supports if s < px]
                sell_zh = [r for r in resistances if r > px]
                if sell_zh:
                    stop = round(min(sell_zh) * 1.03, 2)
                else:
                    stop = round(px * 1.03, 2)
                if sell_zl and sell_zl[-1] < px:
                    tp1 = round(sell_zl[-1], 2)
                else:
                    tp1 = round(px * 0.95, 2)
                if stop > entry and stop > 0 and tp1 < entry:
                    rr = round((entry - tp1) / (stop - entry), 1)
        
        rr = max(0, min(rr or 0, 20))  # cap at 20
        
        signal_type = 'buy' if bsp_buy else ('sell' if 'Sell' in label else 'neutral')

        # Determine if in central zone
        in_zs = False
        if zs_str and supports and resistances:
            for zl, zh in zip(supports, resistances):
                if zl <= px <= zh:
                    in_zs = True
                    break

        # Sector
        sec = sector_signal(code, heat=heat)
        
        # Volume
        vol_analysis = volume_analysis([float(x) for x in closes], [float(x) for x in vols])

        # Wyckoff state from volume + price context
        vol_sig = vol_analysis.get('signal', '')
        price5 = (closes[-1] / closes[-6] - 1) * 100 if len(closes) >= 6 else 0
        price20 = (closes[-1] / closes[-21] - 1) * 100 if len(closes) >= 21 else 0
        
        wyckoff = ''
        if in_zs and ('缩' in str(vol_sig) or '量价正常' in str(vol_sig)):
            wyckoff = 'S(弹簧/缩量区)' if price20 < 0 else 'A(吸筹待确认)'
        elif in_zs and '放' in str(vol_sig):
            wyckoff = 'B(放量突破)' if price5 > 0 else 'D(派发警告)'
        elif not in_zs and '放' in str(vol_sig) and price5 > 3:
            wyckoff = 'C(放量离开)'
        elif '顶背' in str(vol_sig):
            wyckoff = 'D(派发信号)'
        elif '底背' in str(vol_sig):
            wyckoff = 'A(吸筹底背离)'
        elif '背' in str(vol_sig):
            wyckoff = 'W(量价背离)'
        else:
            wyckoff = '-'

        # Tag
        tag = ''
        if in_zs and bsp_buy:
            tag = '中枢内买'
        elif in_zs and not bsp_buy:
            tag = '中枢内等信号'
        elif in_zs and ('Sell' in label):
            tag = '中枢内Sell'
        else:
            # Distance-based tag
            if supports:
                nearest_zl = min(supports, key=lambda z: abs(px - z))
                dist_pct = round((px - nearest_zl) / nearest_zl * 100, 0)
                tag = f'中枢外买(距{dist_pct:+.0f}%)'

        # Risk check
        blocked, risk_reasons = check_risk(code, name)
        
        results.append({
            'code': code,
            'name': name,
            'price': px,
            'pe': pe,
            'ytd': round(ytd, 1) if ytd is not None else None,
            'old_xgb': old_xgb if old_xgb is not None else 0,
            'new_xgb': new_xgb if new_xgb is not None else 0,
            'score3d': score3d['composite'],
            'grade': score3d['grade'],
            'position_pct': score3d['position'] * 100,
            'rr': round(rr, 1),
            'zs': zs_str or '-',
            'in_zs': '是' if in_zs else '否',
            'bsp': label,
            'v45': v45_score,
            'gzk': round(gzk_val, 1),
            'entry': round(entry, 2) if entry is not None else '—',
            'stop': round(stop, 2) if stop is not None else '—',
            'tp1': round(tp1, 2) if tp1 is not None else '—',
            'risk_status': 'BLOCKED' if blocked else 'OK',
            'tag': tag,
            'vol_signal': vol_analysis.get('signal', '-'),
            'wyckoff': wyckoff,
            'sector': sec.get('sector', '-'),
        })

    print(f'  完成: {len(results)} 只信号')

    # Sort by 3D score
    results.sort(key=lambda x: -x['score3d'])

    # ═══════════════ Excel Output ═══════════════
    wb = openpyxl.Workbook()
    
    # --- Sheet 1: Signals ---
    ws = wb.active
    ws.title = f'{today}信号'

    headers = ['代码', '名称', '现价', 'PE', 'YTD%', '旧XGB', '新XGB', '3D分', 
               '等级', '仓位%', 'R:R', '中枢', '中枢内', 'BSP', 'V4.5', 'GZK',
               '买入', '止损', 'TP1', '风控', '标签', '威科夫']

    # Header style
    hdr_fill = PatternFill(start_color='1a1a2e', end_color='1a1a2e', fill_type='solid')
    hdr_font = Font(color='ffffff', bold=True, size=10)
    green_fill = PatternFill(start_color='e8f5e9', end_color='e8f5e9', fill_type='solid')
    yellow_fill = PatternFill(start_color='fff8e1', end_color='fff8e1', fill_type='solid')
    red_fill = PatternFill(start_color='fce4ec', end_color='fce4ec', fill_type='solid')
    thin_border = Border(
        left=Side(style='thin', color='cccccc'),
        right=Side(style='thin', color='cccccc'),
        top=Side(style='thin', color='cccccc'),
        bottom=Side(style='thin', color='cccccc')
    )

    for c, h in enumerate(headers, 1):
        cell = ws.cell(1, c, h)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin_border

    for i, r in enumerate(results):
        row = i + 2
        vals = [
            r['code'], r['name'], r['price'], r['pe'], r['ytd'],
            r['old_xgb'], r['new_xgb'], r['score3d'],
            r['grade'], r['position_pct'], r['rr'],
            r['zs'], r['in_zs'], r['bsp'],
            r['v45'], r['gzk'],
            r['entry'], r['stop'], r['tp1'],
            r['risk_status'], r['tag'], r['wyckoff']
        ]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(row, c, v)
            cell.border = thin_border
            cell.alignment = Alignment(horizontal='center')

        # Color coding
        if r['grade'] == 'A':
            for c in range(1, len(headers)+1):
                ws.cell(row, c).fill = green_fill
        elif r['risk_status'] == 'BLOCKED':
            for c in range(1, len(headers)+1):
                ws.cell(row, c).fill = red_fill
        elif '中枢内买' == r['tag']:
            for c in range(1, len(headers)+1):
                ws.cell(row, c).fill = green_fill

    # Column widths
    widths = {'A':8, 'B':12, 'C':8, 'D':6, 'E':7, 'F':7, 'G':7, 'H':6,
              'I':5, 'J':6, 'K':5, 'L':20, 'M':6, 'N':16, 'O':5, 'P':5,
              'Q':8, 'R':8, 'S':8, 'T':6, 'U':18}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = f'A1:U{len(results)+1}'

    # --- Sheet 2: Macro (detailed) ---
    ws2 = wb.create_sheet('宏观')
    
    # Stats
    buys = sum(1 for r in results if 'Buy' in r['bsp'])
    sells = sum(1 for r in results if 'Sell' in r['bsp'])
    holds = sum(1 for r in results if 'Hold' in r['bsp'])
    inzs = sum(1 for r in results if r['in_zs'] == '是')
    grade_a = sum(1 for r in results if r['grade'] == 'A')
    grade_b = sum(1 for r in results if r['grade'] == 'B')
    buys_zs = sum(1 for r in results if r['in_zs'] == '是' and 'Buy' in r['bsp'])
    
    macro_lines = [
        [f'{today} 收盘 | 缠论+双XGBoost+三维评分+风控 | 17模块全功能扫描'],
        [''],
        ['━━━ 市场指数 ━━━'],
        [f'DXY: {macro.get("DXY",{}).get("value","?")} | US10Y: {macro.get("UST10Y",{}).get("value","?")}% | USD/CNY: {macro.get("USDCNY",{}).get("value","?")}'],
        [f'宏观方向: {macro_signal(macro).get("bias","中性")}'],
        [''],
        ['━━━ 扫描统计 ━━━'],
        [f'CSI300成分股: {len(stocks)}只 | 有效信号: {len(results)}只'],
        [f'Buy: {buys} | Sell: {sells} | Hold: {holds}'],
        [f'中枢内买: {buys_zs} | 中枢内总计: {inzs}'],
        [''],
        ['━━━ 3D评分分布 ━━━'],
        [f'A级(≥65): {grade_a} | B级(≥50): {grade_b} | C级(≥35): {len(results)-grade_a-grade_b}'],
        [f'分数范围: {results[-1]["score3d"]:.0f}-{results[0]["score3d"]:.0f}'],
        [''],
        ['━━━ 综合判断 ━━━'],
        ['评分按三维(技术40%+基本30%+消息30%)加权，中枢内买点优先。'],
        ['A级标的可重仓(50%)，B级可配置(20-30%)，C级观望(10%)。'],
        ['仅中枢内买点享有完整安全边际，中枢外买需次级别确认。'],
    ]
    
    for row_idx, line in enumerate(macro_lines, 1):
        for col_idx, val in enumerate(line, 1):
            c = ws2.cell(row_idx, col_idx, val)
            if '━' in str(val): c.font = Font(bold=True, size=11)
    ws2.column_dimensions['A'].width = 80
    
    # --- Sheet 3: 综合推荐 (full columns) ---
    ws3 = wb.create_sheet('综合推荐')
    rec_headers = ['#', '代码', '名称', '现价', '旧XGB', '新XGB', '3D分', '等级', '仓位%', 
                   'R:R', 'V4.5', 'GZK', '中枢', '买入', '止损', 'TP1', '方向', '威科夫', '逻辑']
    for c, h in enumerate(rec_headers, 1):
        cell = ws3.cell(1, c, h)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.border = thin_border
        cell.alignment = Alignment(horizontal='center')
    
    # Rank: 3D×0.5 + (XGB×0.3 if 中枢内) + V4.5 bonus
    for r in results:
        r['_rank'] = r['score3d'] * 0.5 + (r['old_xgb'] * 0.3 if r['in_zs'] == '是' else 0) + (10 if r['v45'] >= 8 else 0)
    results.sort(key=lambda x: -x['_rank'])
    
    recs = results[:15]
    for i, r in enumerate(recs):
        logic = '+'.join([x for x in [
            ('中枢内' if r['in_zs'] == '是' else ''),
            ('3D' + r['grade']) if r['grade'] in ('A','B') else '',
        ] if x])
        rr_s = r['rr'] if r['rr'] > 0 else '—'
        direction = '多' if 'Buy' in str(r.get('bsp','')) else ('空' if 'Sell' in str(r.get('bsp','')) else '观望')
        vals = [i+1, r['code'], r['name'], r['price'], r['old_xgb'], r['new_xgb'],
                r['score3d'], r['grade'], r['position_pct'], rr_s,
                r['v45'], r['gzk'], r['zs'][:15],
                r['entry'], r['stop'], r['tp1'], direction, r['wyckoff'], logic]
        for c, v in enumerate(vals, 1):
            cell = ws3.cell(i+2, c, v)
            cell.border = thin_border
            cell.alignment = Alignment(horizontal='center')
            if i < 5: cell.fill = green_fill
    
    for c, w in enumerate([4,8,10,7,5,5,5,4,6,4,5,5,15,7,7,7,18], 1):
        ws3.column_dimensions[openpyxl.utils.get_column_letter(c)].width = w
    ws3.freeze_panes = 'A2'


    
    # Print top 20
    print(f'\n{"="*60}')
    print(f'🏆 Top 20 (3D综合评分)')
    print(f'{"="*60}')
    print(f'{"排名":<4} {"名称":<12} {"现价":<8} {"YTD%":<7} {"旧XGB":<6} {"新XGB":<6} {"3D分":<6} {"等级":<4} {"BSP":<18} {"标签":<20} {"R:R":<5}')
    print('-' * 95)
    for i, r in enumerate(results[:20]):
        print(f'{i+1:<4} {r["name"]:<12} {r["price"]:<8} {str(r["ytd"]):<7} '
              f'{r["old_xgb"]:<6} {r["new_xgb"]:<6} {r["score3d"]:<6} {r["grade"]:<4} '
              f'{r["bsp"]:<18} {r["tag"]:<20} {r["rr"]:<5}')

    print(f'\nSaved: {out_path} | {len(results)} signals')
    print(f'A级: {grade_a} | B级: {grade_b} | 中枢内买: {inzs}')

    # --- 组合优化(Hierarchical Risk Parity) ---
    try:
        from portfolio_optimize import optimize_portfolio
        buy_codes = [r['code'] for r in results if 'Buy' in str(r.get('bsp','')) and r['in_zs'] == '是']
        if len(buy_codes) >= 3:
            print(f'\n[组合优化] {len(buy_codes)}只中枢Buy → HRP风险平价...')
            weights = optimize_portfolio(buy_codes, max_stocks=30, method='hrp')
            if weights:
                ws4 = wb.create_sheet('组合优化')
                opt_headers = ['#', '代码', '名称', '权重%', '现价', '等级', 'R:R', '威科夫', '方向', '逻辑']
                for c, h in enumerate(opt_headers, 1):
                    cell = ws4.cell(1, c, h)
                    cell.fill = hdr_fill; cell.font = hdr_font
                    cell.border = thin_border; cell.alignment = Alignment(horizontal='center')

                # Build name lookup
                name_map = {r['code']: r['name'] for r in results}
                rr_map = {r['code']: r['rr'] for r in results}
                grade_map = {r['code']: r['grade'] for r in results}
                price_map = {r['code']: r['price'] for r in results}
                wyckoff_map = {r['code']: r.get('wyckoff','-') for r in results}
                bsp_map = {r['code']: r.get('bsp','') for r in results}

                ranked = sorted(weights.items(), key=lambda x: -x[1])
                for i, (code, wt) in enumerate(ranked):
                    name = name_map.get(code, code)
                    direction = '多' if 'Buy' in str(bsp_map.get(code,'')) else ('空' if 'Sell' in str(bsp_map.get(code,'')) else '观望')
                    logic = '+'.join([
                        f'HRP{wt:.0%}',
                        f'RR{rr_map.get(code,0)}' if rr_map.get(code,0) > 0 else '',
                        wyckoff_map.get(code,'-') if wyckoff_map.get(code,'-') != '-' else ''
                    ]).strip('+')
                    vals = [i+1, code, name, round(wt*100,1), price_map.get(code,'-'),
                            grade_map.get(code,'-'), rr_map.get(code,'-'),
                            wyckoff_map.get(code,'-'), direction, logic]
                    for c, v in enumerate(vals, 1):
                        cell = ws4.cell(i+2, c, v)
                        cell.border = thin_border
                        cell.alignment = Alignment(horizontal='center')
                        if i < 3: cell.font = Font(color='2F5496', bold=True)
                print(f'  组合优化sheet: {len(ranked)}只 前3: {ranked[0][0]}({ranked[0][1]:.0%}) {ranked[1][0]}({ranked[1][1]:.0%}) {ranked[2][0]}({ranked[2][1]:.0%})')
    except Exception as e:
        print(f'  组合优化跳过: {e}')

    wb.save(out_path)


if __name__ == '__main__':
    main()
