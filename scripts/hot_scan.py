#!/usr/bin/env python3
"""热点板块批量缠论扫描器 — 读取 references/hot_stocks.csv 全量分析"""
import csv, subprocess, sys, os, time
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(SCRIPT_DIR, '..', 'references', 'hot_stocks.csv')

def load_stocks():
    themes = defaultdict(list)
    with open(CSV_PATH, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            code = r['code']
            name = r['name']
            for t in r['themes'].split('|'):
                themes[t].append((code, name))
    return themes

def analyze_one(code):
    """Run analyze.py for one stock, return key fields"""
    try:
        r = subprocess.run([sys.executable, os.path.join(SCRIPT_DIR, 'analyze.py'), code],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=35, cwd=SCRIPT_DIR)
        out = r.stdout.decode(errors='replace')
        
        result = {'code': code, 'bsp': '?', 'score': 0, 'zs': '', 'pos': '', 'price': 0, 'ytd': 0}
        for line in out.split('\n'):
            if 'BSP:' in line:
                result['bsp'] = line.split('BSP:')[1].strip()[:30]
            if '评分:' in line:
                try: result['score'] = int(line.split('评分:')[1].strip().split('/')[0])
                except: pass
            if '中枢:' in line:
                result['zs'] = line.split('中枢:')[1].strip()[:40]
            if '位置:' in line:
                result['pos'] = line.split('位置:')[1].strip()[:20]
        return result
    except subprocess.TimeoutExpired:
        return {'code': code, 'bsp': 'TIMEOUT', 'score': 0, 'zs': '', 'pos': '', 'price': 0, 'ytd': 0}
    except Exception as e:
        return {'code': code, 'bsp': f'ERR', 'score': 0, 'zs': '', 'pos': '', 'price': 0, 'ytd': 0}

def main():
    themes = load_stocks()
    all_codes = set()
    theme_map = defaultdict(list)  # code -> [theme_names]
    for theme, stocks in themes.items():
        for code, name in stocks:
            all_codes.add(code)
            theme_map[code].append(theme)
    
    print(f"# 热点板块缠论分析 ({time.strftime('%Y-%m-%d')})")
    print(f"# {len(all_codes)} 只个股 | {len(themes)} 个主题\n")
    
    # Analyze
    results = {}
    codes = sorted(all_codes)
    for i, code in enumerate(codes):
        print(f"[{i+1}/{len(codes)}] {code} ", end='', flush=True)
        r = analyze_one(code)
        results[code] = r
        print(f"BSP={r['bsp']} 评分={r['score']} ZS={r['zs']}")
    
    # By theme
    print(f"\n---\n## 各板块分析\n")
    for theme in sorted(themes.keys()):
        stocks = themes[theme]
        buys = [s for s in stocks if 'Buy' in results.get(s[0], {}).get('bsp', '')]
        print(f"\n### {theme} ({len(stocks)}只, 买入:{len(buys)})\n")
        print(f"| 代码 | 名称 | BSP | 评分 | 中枢 | 位置 |")
        print(f"|------|------|-----|------|------|------|")
        for code, name in stocks:
            r = results.get(code, {})
            print(f"| {code} | {name} | {r.get('bsp','?')} | {r.get('score','?')} | {r.get('zs','?')} | {r.get('pos','?')} |")
    
    # Buy summary
    all_buys = [(code, r) for code, r in results.items() if 'Buy' in r.get('bsp', '')]
    all_buys.sort(key=lambda x: x[1].get('score', 0), reverse=True)
    print(f"\n---\n## 🎯 买入标的汇总 ({len(all_buys)}只)\n")
    if all_buys:
        print(f"| 代码 | 名称 | 主题 | BSP | 评分 | 中枢 |")
        print(f"|------|------|------|-----|------|------|")
        for code, r in all_buys:
            themes_str = ', '.join(theme_map.get(code, []))
            print(f"| {code} | {r.get('name','?')} | {themes_str} | {r['bsp']} | {r['score']} | {r['zs']} |")

if __name__ == '__main__':
    main()
