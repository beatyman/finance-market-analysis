#!/usr/bin/env python3
"""
分时量能分析 — 新浪财经数据源（免费,3秒延迟）
来源: @cnyezi/a-stock-analysis 设计理念
功能: 早盘30分/尾盘30分/放量TOP10/主力动向
"""
import subprocess as sp,json,time
from datetime import datetime

def get_minute_volume(code):
    """获取分时成交量分布 (新浪财经)"""
    prefix='sh' if code.startswith('6') else 'sz'
    url=f'https://quotes.sina.cn/cn/api/jsonp_v2.php/data/CN_MarketDataService.getKLineData?symbol={prefix}{code}&scale=5'
    r=sp.run(['curl','-sL','--max-time','5',url],stdout=sp.PIPE,stderr=sp.PIPE,timeout=7)
    data=r.stdout.decode('utf-8','ignore')
    try:
        j=json.loads(data)
        return j if isinstance(j,list) else []
    except:return []

def analyze_volume(code):
    """分时量能分析"""
    bars=get_minute_volume(code)
    if not bars:return None
    
    today=datetime.now().strftime('%Y-%m-%d')
    today_bars=[b for b in bars if b.get('day','')==today]
    if not today_bars:return None
    
    total_vol=sum(float(b.get('volume',0)) for b in today_bars)
    if total_vol==0:return None
    
    # 时段分布
    morning_first=0;morning_mid=0;afternoon=0;tail=0
    top_volumes=[]
    
    for b in today_bars:
        t=b.get('time','');vol=float(b.get('volume',0))
        top_volumes.append((t,vol,int(float(b.get('close',0))*100)))
        hh=int(t[:2]) if len(t)>=2 else 0;mm=int(t[2:4]) if len(t)>=4 else 0
        
        if hh==9 and mm>=30 or hh==10 and mm==0:morning_first+=vol
        elif hh==10 or (hh==11 and mm<=30):morning_mid+=vol
        elif hh>=13 and hh<14 or (hh==14 and mm<=30):afternoon+=vol
        elif hh==14 and mm>30:tail+=vol
    
    top_volumes.sort(key=lambda x:-x[1])
    
    morning_pct=morning_first/total_vol*100
    tail_pct=tail/total_vol*100
    
    # 主力判断
    signals=[]
    if morning_pct>30:signals.append('🔥 早盘主力抢筹')
    elif morning_pct>20:signals.append('📈 早盘较活跃')
    if tail_pct>25:signals.append('⚠️ 尾盘异动放量')
    elif tail_pct>15:signals.append('📊 尾盘有一定量')
    
    return {
        'total_vol':int(total_vol),
        'morning_pct':morning_pct,
        'morning_mid_pct':morning_mid/total_vol*100,
        'afternoon_pct':afternoon/total_vol*100,
        'tail_pct':tail_pct,
        'top5':top_volumes[:5],
        'signals':signals,
        'bars_count':len(today_bars)
    }

def format_minute_report(code,name=None):
    """格式化分时量能报告"""
    r=analyze_volume(code)
    if not r:return '(分时数据未获取)'
    
    lines=[f'【分时量能】{name or code}']
    lines.append(f'  全天成交: {r["total_vol"]}手')
    lines.append(f'  早盘30分: {r["morning_pct"]:.0f}% | 上午中段: {r["morning_mid_pct"]:.0f}%')
    lines.append(f'  下午中段: {r["afternoon_pct"]:.0f}% | 尾盘30分: {r["tail_pct"]:.0f}%')
    
    if r['signals']:
        lines.append(f'  【主力动向】')
        for s in r['signals']:lines.append(f'    {s}')
    
    lines.append(f'  放量 TOP5:')
    for t,vol,px in r['top5']:
        lines.append(f'    {t} ¥{px/100:.2f} {vol}手')
    
    return '\n'.join(lines)

if __name__=='__main__':
    import sys
    code=sys.argv[1] if len(sys.argv)>1 else '002475'
    print(format_minute_report(code,'立讯精密'))
