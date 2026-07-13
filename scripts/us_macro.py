#!/usr/bin/env python3
"""美股+美债宏观数据抓取 — 用于沪深300分析的宏观背景板"""
import subprocess as sp, re, json
from datetime import datetime

def fetch_treasury_yields(year='2026'):
    """美国财政部: 最新收益率曲线"""
    url = f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
    r = sp.run(['curl','-x','socks5h://127.0.0.1:1080','-sL','--max-time','15',url],stdout=sp.PIPE,timeout=20)
    raw = r.stdout.decode('utf-8','ignore')
    entries = re.findall(r'<entry>(.*?)</entry>', raw, re.DOTALL)
    if not entries: return None
    
    latest = entries[-1]
    fields = {'1M':'BC_1MONTH','3M':'BC_3MONTH','6M':'BC_6MONTH','1Y':'BC_1YEAR',
              '2Y':'BC_2YEAR','5Y':'BC_5YEAR','7Y':'BC_7YEAR','10Y':'BC_10YEAR',
              '20Y':'BC_20YEAR','30Y':'BC_30YEAR'}
    result = {}
    date_m = re.search(r'<d:NEW_DATE[^>]*>([^<]+)</d:NEW_DATE>', latest)
    if date_m: result['date'] = date_m.group(1)
    for short, full in fields.items():
        m = re.search(f'<d:{full}[^>]*>([^<]+)</d:{full}>', latest)
        if m: result[short] = float(m.group(1))
    if '2Y' in result and '10Y' in result:
        result['2s10s'] = round(result['10Y'] - result['2Y'], 2)
    return result

def fetch_us_markets():
    """Yahoo Finance: 美股指数+AI半导体+宏观"""
    syms = '^GSPC,^IXIC,^DJI,^SOX,^VIX,NVDA,TSM,AMD,AVGO,DX-Y.NYB,GC=F,HG=F,CL=F'
    r = sp.run(['curl','-x','socks5h://127.0.0.1:1080','-sL','--max-time','15',
        f'https://query1.finance.yahoo.com/v8/finance/chart/{syms}?interval=1d&range=2d'],
        stdout=sp.PIPE,timeout=20)
    try:
        d = json.loads(r.stdout)
        results = {}
        labels = {'^GSPC':'标普500','^IXIC':'纳斯达克','^DJI':'道琼斯','^SOX':'费城半导体',
                  '^VIX':'VIX','NVDA':'英伟达','TSM':'台积电','AMD':'AMD','AVGO':'博通',
                  'DX-Y.NYB':'DXY','GC=F':'黄金','HG=F':'铜','CL=F':'原油'}
        for res in d['chart']['result']:
            sym = res['meta']['symbol']; name = labels.get(sym, sym)
            q = res['indicators']['quote'][0]
            closes = [c for c in q['close'] if c is not None]
            if len(closes)>=2:
                chg = (closes[-1]/closes[-2]-1)*100
                results[name] = {'close': round(closes[-1],2), 'chg%': round(chg,2)}
        return results
    except: return None

if __name__ == '__main__':
    print('=== 美债收益率 ===')
    y = fetch_treasury_yields()
    if y:
        for k in ['1M','3M','6M','1Y','2Y','5Y','10Y','30Y','2s10s']:
            if k in y: print(f'  {k}: {y[k]}{"%" if k!="2s10s" else "bp"}')
    
    print('\n=== 美股 ===')
    m = fetch_us_markets()
    if m:
        for name in ['标普500','纳斯达克','道琼斯','费城半导体','VIX','英伟达','台积电','AMD','博通','DXY','黄金','铜','原油']:
            if name in m:
                print(f'  {name}: {m[name]["close"]} {m[name]["chg%"]:+.2f}%')
    
    print('\n前瞻:')
    if m and y:
        sox = m.get('费城半导体',{}).get('chg%',0)
        spy = m.get('标普500',{}).get('chg%',0)
        t10y = y.get('10Y',0)
        vix = m.get('VIX',{}).get('close',0)
        copper = m.get('铜',{}).get('chg%',0)
        
        print(f'  半导体{sox:+.1f}% → A股科技{("承压" if sox<-1 else "缓解")}')
        print(f'  VIX {vix} → {("高波动不加仓" if vix>16 else "波动可接受")}')
        print(f'  铜{copper:+.1f}% → 铜持仓{("有利" if copper>0 else "不利")}')
        print(f'  10Y {t10y}% → {("压制成长" if t10y>4 else "中性")}')
