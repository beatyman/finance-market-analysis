#!/usr/bin/env python3
"""宏观事件日历 — 未来一周关键日程"""
import yfinance as yf,subprocess as sp,json,time,os
from datetime import datetime,timedelta

HERE=os.path.dirname(os.path.abspath(__file__))
CACHE={};CACHE_TIME=None

def load_events():
    """未来一周宏观事件"""
    global CACHE,CACHE_TIME
    now=time.time()
    if CACHE and CACHE_TIME and now-CACHE_TIME<3600:  # 1h cache
        return CACHE
    
    today=datetime.now()
    events=[]
    
    # ── Fed schedule ──
    fed_events={
        '2026-06-25':('FOMC会议纪要公布','🏛️'),
        '2026-07-15':('CPI通胀数据','📊'),
        '2026-07-28':('FOMC利率决议','🔴'),
    }
    
    # ── US political ──
    political={
        '2026-06-25':('总统贸易政策讲话','🇺🇸'),
        '2026-07-04':('独立日假期','🇺🇸'),
    }
    
    # ── Geopolitical ──
    geo={
        '2026-06-25':('伊朗核谈判新一轮','⚔️'),
        '2026-06-28':('乌克兰和平峰会','🕊️'),
    }
    
    # ── China key dates ──
    china={
        '2026-06-30':('PMI制造业数据公布','🇨🇳'),
        '2026-07-10':('CPI/PPI通胀数据','🇨🇳'),
        '2026-07-15':('二季度GDP数据','🇨🇳'),
    }
    
    for date_str,label in [
        ('2026-06-25','FOMC会议纪要公布'),
        ('2026-06-28','乌克兰和平峰会'),
        ('2026-06-30','中国PMI公布'),
        ('2026-07-04','美国独立日休市'),
        ('2026-07-10','中国CPI/PPI'),
        ('2026-07-15','美国CPI'),
        ('2026-07-28','FOMC利率决议'),
    ]:
        try:
            dt=datetime.strptime(date_str,'%Y-%m-%d')
            days=(dt-today).days
            if -1<=days<=7:  # show yesterday through next week
                icon='🏛️' if 'FOMC' in label else('🇺🇸' if '美国' in label else('🇨🇳' if '中国' in label else('⚔️' if '乌克兰' in label or '伊朗' in label else('📊' if 'CPI' in label or 'PMI' in label else'📅'))))
                impact='🔴' if days<=1 else('🟡' if days<=3 else '🟢')
                events.append((days,date_str,icon,impact,label))
        except:pass
    
    events.sort()
    CACHE=events;CACHE_TIME=now
    return events

def format_calendar():
    """格式化事件日历"""
    events=load_events()
    today=datetime.now()
    lines=[]
    lines.append('🗓️ 未来一周关键事件:')
    for days,date,icon,impact,label in events:
        if days<0:
            tag='昨'
        elif days==0:
            tag='今🔴'
        elif days==1:
            tag='明🟡'
        else:
            tag='%dd'%days
        lines.append('  %s %s %s %s'%(impact,icon,label,date))
    return '\n'.join(lines)

if __name__=='__main__':
    print(format_calendar())
