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
        chg_pct = q['change_pct']

        # Fetch K-line
        data = fetch_kline_a(code)
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
        entry = px
        stop = px
        tp1 = px * 1.05
        rr = 0
        
        if supports and resistances:
            # Find nearest 中枢
            nearest_idx = 0
            min_dist = float('inf')
            for i, (zl, zh) in enumerate(zip(supports, resistances)):
                center = (zl + zh) / 2
                dist = abs(px - center)
                if dist < min_dist:
                    min_dist = dist
                    nearest_idx = i
            
            zl = supports[nearest_idx]
            zh = resistances[nearest_idx]
            
            if bsp_buy:
                # Buy: entry near 中枢下沿, stop below it
                entry = round(zl + (zh - zl) * 0.1, 2)
                stop = round(zl * 0.97, 2)
                tp1 = round(zh, 2)
                if entry > stop and stop > 0:
                    rr = round((tp1 - entry) / (entry - stop), 1)
            elif 'Sell' in label:
                entry = px
                stop = round(zh * 1.03, 2)
                tp1 = round(zl, 2)
                if stop > entry and stop > 0:
                    rr = round((entry - tp1) / (stop - entry), 1)
        
        rr = max(0, min(rr, 20))  # cap at 20
        
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
            'entry': round(entry, 2),
            'stop': round(stop, 2),
            'tp1': round(tp1, 2),
            'risk_status': 'BLOCKED' if blocked else 'OK',
            'tag': tag,
            'vol_signal': vol_analysis.get('signal', '-'),
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
               '买入', '止损', 'TP1', '风控', '标签']

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
            r['risk_status'], r['tag']
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

    # --- Sheet 2: Macro ---
    ws2 = wb.create_sheet('宏观')
    macro_lines = [
        [f'{today} 收盘', '缠论+双XGBoost+三维评分+风控', '17模块全功能扫描'],
        [''],
        ['━━━ 市场环境 ━━━'],
        [f'DXY: {macro.get("DXY",{}).get("value","?")}', 
         f'US10Y: {macro.get("UST10Y",{}).get("value","?")}%',
         f'USD/CNY: {macro.get("USDCNY",{}).get("value","?")}'],
        [f'扫描股票: {len(stocks)}只 CSI300 成分股'],
        [f'有效信号: {len(results)}只 (3D分≥{args.min_score})'],
        [''],
        ['━━━ 信号统计 ━━━'],
    ]
    # Stats
    buys = sum(1 for r in results if 'Buy' in r['bsp'])
    sells = sum(1 for r in results if 'Sell' in r['bsp'])
    holds = sum(1 for r in results if 'Hold' in r['bsp'])
    inzs = sum(1 for r in results if r['in_zs'] == '是')
    grade_a = sum(1 for r in results if r['grade'] == 'A')
    grade_b = sum(1 for r in results if r['grade'] == 'B')
    
    macro_lines.append([f'买入信号: {buys}', f'卖出信号: {sells}', f'Hold: {holds}'])
    macro_lines.append([f'中枢内: {inzs}', f'A级: {grade_a}', f'B级: {grade_b}'])
    macro_lines.append([f'3D分范围: {results[-1]["score3d"] if results else 0}-{results[0]["score3d"] if results else 0}'])

    for row_idx, line in enumerate(macro_lines, 1):
        for col_idx, val in enumerate(line, 1):
            ws2.cell(row_idx, col_idx, val)

    # --- Sheet 3: 综合推荐 ---
    ws3 = wb.create_sheet('综合推荐')
    rec_headers = ['#', '代码', '名称', '3D分', '等级', 'BSP', 'R:R', '买入', '止损', 'TP1', '标签']
    for c, h in enumerate(rec_headers, 1):
        cell = ws3.cell(1, c, h)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.border = thin_border
        cell.alignment = Alignment(horizontal='center')
    
    recs = [r for r in results if r['grade'] in ('A', 'B')][:15]
    for i, r in enumerate(recs):
        vals = [i+1, r['code'], r['name'], r['score3d'], r['grade'],
                r['bsp'], r['rr'], r['entry'], r['stop'], r['tp1'], r['tag']]
        for c, v in enumerate(vals, 1):
            cell = ws3.cell(i+2, c, v)
            cell.border = thin_border
            cell.alignment = Alignment(horizontal='center')
    
    # Column widths for sheet 3
    for c, w in [('A',4),('B',8),('C',12),('D',7),('E',5),('F',16),('G',5),('H',8),('I',8),('J',8),('K',18)]:
        ws3.column_dimensions[c].width = w

    # Save
    wb.save(out_path)
    
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


if __name__ == '__main__':
    main()
