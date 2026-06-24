#!/usr/bin/env python3
"""宏观事件日历 — Fed官方日历核实"""
from datetime import datetime

SCHEDULE={
    '2026-06-25':('🇺🇸 麻省银行家协会讲话','🟢'),
    '2026-06-28':('🕊️ 乌克兰和平峰会','🟡'),
    '2026-06-30':('🇨🇳 中国PMI制造业数据','🟡'),
    '2026-07-08':('📋 FOMC 6月会议纪要','🟡'),
    '2026-07-10':('🇨🇳 CPI/PPI','🟡'),
    '2026-07-15':('🇨🇳 Q2 GDP + 🇺🇸 CPI','🔴'),
    '2026-07-28':('🔴 FOMC利率决议','🔴'),
}

def format_calendar():
    today=datetime.now();lines=['🗓️ 未来关键事件 (Fed官方核实):']
    for date_str,(event,impact) in sorted(SCHEDULE.items()):
        dt=datetime.strptime(date_str,'%Y-%m-%d')
        days=(dt-today).days
        if days<0:continue
        tag='今天🔴' if days==0 else('明天🟡' if days==1 else('%dd'%days))
        lines.append('  %s %s  %s  %s'%(impact,tag,date_str,event))
    return '\n'.join(lines)

if __name__=='__main__':
    print(format_calendar())
