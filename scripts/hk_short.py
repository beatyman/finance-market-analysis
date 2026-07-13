#!/usr/bin/env python3
"""港股沽空数据抓取 — HKEX官网"""
import subprocess as sp, re
from datetime import datetime, timedelta

STOCKS = {'美团':'3690','腾讯':'0700','阿里':'9988','小米':'1810','快手':'1024'}

def fetch_hk_short(date_str=None):
    """获取HKEX每日沽空数据"""
    if not date_str:
        today = datetime.now()
        # Try last 5 trading days
        for i in range(10):
            d = (today - timedelta(days=i)).strftime('%Y%m%d')
            url = f'https://www.hkex.com.hk/eng/stat/smstat/ssturnover/{d[:6]}/ss_{d}.htm'
            r = sp.run(['curl','-x','socks5h://127.0.0.1:1080','-sL','--max-time','10',
                        '-H','User-Agent: Mozilla/5.0',url],
                       stdout=sp.PIPE,timeout=15)
            if r.returncode==0 and len(r.stdout)>5000:
                return parse_hkex_html(r.stdout.decode('utf-8','ignore'), d)
    return None

def parse_hkex_html(html, date):
    """Parse HKEX HTML table for short selling data"""
    result = {}
    for name, code in STOCKS.items():
        # Find the row containing this stock code
        pattern = re.compile(f'{code}.*?([\\d.,]+).*?([\\d.,]+)', re.DOTALL)
        # Simplified — actual parsing depends on HKEX HTML structure
        m = pattern.search(html)
        if m:
            result[name] = {'code': code, 'short_vol': m.group(1), 'short_val': m.group(2)}
    return {'date': date, 'stocks': result}

if __name__ == '__main__':
    data = fetch_hk_short()
    if data:
        print(f'Date: {data["date"]}')
        for name, info in data['stocks'].items():
            print(f'  {name}({info["code"]}): vol={info["short_vol"]} val={info["short_val"]}')
    else:
        print('HKEX data unavailable (proxy/network)')
