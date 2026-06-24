#!/usr/bin/env python3
"""
日内做T策略 — 价格区间+量价+日线方向
前提: 持有底仓
核心: 日线定方向 + 盘中极值点 + 量异常 = 做T信号
"""
import yfinance as yf,numpy as np,sys,os
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,HERE);sys.path.insert(0,os.path.join(HERE,'..','chanpy'))
from chan_engine import analyze as chan_analyze,get_bsp_label
import warnings;warnings.filterwarnings('ignore')

def _get_kl(d):
    try:
        if hasattr(d.columns,'levels'):
            d=d.xs(d.columns.get_level_values(1)[0],axis=1,level=1)
    except:pass
    C=[float(x) for x in np.array(d['Close']).ravel()][-250:]
    H=[float(x) for x in np.array(d['High']).ravel()][-250:]
    L=[float(x) for x in np.array(d['Low']).ravel()][-250:]
    O=[float(x) for x in np.array(d['Open']).ravel()][-250:]
    V=[float(x) for x in np.array(d['Volume']).ravel()][-250:]
    D=[x.strftime('%Y-%m-%d') for x in d.index.tolist()][-250:]
    return D,O,C,H,L,V

def t0_analysis(code):
    sym=code+('.SS' if code.startswith('6') else '.SZ')
    
    # Daily trend
    dd=yf.download(sym,period='1mo',progress=False)
    if len(dd)<10:return None
    D_d,O_d,C_d,H_d,L_d,V_d=_get_kl(dd)
    cur_d,bb_d,bt_d,px_d,zs_d,pos_d=chan_analyze(D_d,O_d,C_d,H_d,L_d,code)
    bias='bull' if bb_d else('bear' if 'Sell' in get_bsp_label(bb_d,bt_d,pos_d) else 'neutral')
    
    # 30m intraday data
    dm=yf.download(sym,period='5d',interval='30m',progress=False)
    if len(dm)<20:return None
    D30,O30,C30,H30,L30,V30=_get_kl(dm)
    n=len(C30);px=C30[-1]
    
    # Today's bars
    today=D30[-1].split(' ')[0]
    tb=[i for i,d in enumerate(D30) if d.startswith(today)]
    if not tb:return None
    tC=[C30[i] for i in tb];tL=[L30[i] for i in tb];tH=[H30[i] for i in tb];tV=[V30[i] for i in tb]
    t_open=tC[0];t_hi=max(tH);t_lo=min(tL)
    avg_v=sum(tV)/len(tV) if tV else 1
    
    # MA20 on 30m
    ma20=sum(C30[-20:])/20
    atr_30=sum(tH[i]-tL[i] for i in range(len(tb)))/len(tb)
    
    # Signal logic
    action=None;entry=None;stop=None
    
    # 1. 回补信号 (buy back / add)
    if bias in ('bull','neutral'):
        dist_lo=(px-t_lo)/t_lo*100
        if px<t_lo*1.005:  # within 0.5% of today low
            action=f'🎯 回补: 接近今日低点 ¥{t_lo:.1f}(距{px-t_lo:+.1f})'
            entry=t_lo;stop=t_lo*0.99
        elif px<ma20 and tV and tV[-1]>avg_v*1.3:  # below MA20 + volume spike
            action=f'💡 回补: 低于MA20(¥{ma20:.0f})+放量({tV[-1]/avg_v:.1f}x)'
            entry=px;stop=px*0.98
        elif bias=='bull' and px>t_hi*0.98 and px<t_hi and tV and tV[-1]<avg_v*0.6:
            action=f'🔻 减仓: 接近今日高点 ¥{t_hi:.1f}+缩量—卖压不足,可卖'
            entry=t_hi;stop=t_hi*1.005
    
    # 2. 减仓信号
    if bias in ('bear','neutral'):
        dist_hi=(t_hi-px)/px*100
        if px>t_hi*0.995:  # near today high
            action=f'🔻 减仓: 接近今日高点 ¥{t_hi:.1f}'
            entry=t_hi;stop=t_hi*1.005
        elif tV and tV[-1]>avg_v*1.5 and px>px*0.995:  # volume spike at relative high
            action=f'🔻 减仓: 放量冲高({tV[-1]/avg_v:.1f}x)'
            entry=px;stop=px*1.005
    
    return {
        'code':code,'px':round(px,2),'bias':bias,
        't_hi':round(t_hi,2),'t_lo':round(t_lo,2),'ma20':round(ma20,1),
        'atr':round(atr_30,2),'v_ratio':round(tV[-1]/avg_v,1) if tV else 1,
        'action':action,'bars':len(tb),'d_label':get_bsp_label(bb_d,bt_d,pos_d)
    }

if __name__=='__main__':
    code=sys.argv[1] if len(sys.argv)>1 else '002475'
    r=t0_analysis(code)
    if r:
        bm={'bull':'🟢偏多→优先回补','bear':'🔴偏空→优先减仓','neutral':'🟡中性→双向'}.get(r['bias'],'?')
        print(f'{code} ¥{r["px"]} | 日线:{r["d_label"]}({bm})')
        print(f'今日: ¥{r["t_lo"]}~¥{r["t_hi"]} | MA20:¥{r["ma20"]} | ATR:¥{r["atr"]} | 量:{r["v_ratio"]}x')
        print(f'已交易{r["bars"]}根30m')
        if r['action']:print(r['action'])
        else:print('🟡 无做T信号')
