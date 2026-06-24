#!/usr/bin/env python3
"""宏观因子分析 — 美债收益率+美元+汇率"""
import yfinance as yf,os,sys
HERE=os.path.dirname(os.path.abspath(__file__))

def load_macro(period='3mo'):
    """获取宏观因子"""
    # US Treasuries: 3M, 5Y, 10Y, 30Y
    # USD index, USD/CNY
    tickers={'US10Y':'^TNX','US5Y':'^FVX','US3M':'^IRX','US30Y':'^TYX','DXY':'DX-Y.NYB','USDCNY':'CNY=X'}
    macro={}
    for name,sym in tickers.items():
        try:
            df=yf.download(sym,period=period,progress=False)
            if len(df)>0:
                def fv(x):return float(x.item() if hasattr(x,'item') else x)
                px=fv(df['Close'].values[-1])
                px5=fv(df['Close'].values[-5]) if len(df)>=5 else px
                chg=round((px-px5)/px5*100,2)
                macro[name]={'value':round(px,2),'chg_5d':chg,'trend':'↑' if px>px5 else '↓'}
        except:pass
    return macro

def macro_signal(macro):
    """解读宏观信号"""
    signals=[]
    if 'US10Y' in macro:
        v=macro['US10Y']['value']
        signals.append(('US10Y','%.2f%%'%v,'利率高位' if v>4 else '中性','对成长股/黄金不利' if v>4.5 else '可接受'))
    if 'US5Y' in macro:
        v=macro['US5Y']['value']
        # Yield curve: 10Y - 5Y spread
        if 'US10Y' in macro:
            spread=macro['US10Y']['value']-v
            inverted=spread<0
            signals.append(('2s10s','%.2f'%spread,'倒挂' if inverted else '正常','衰退信号' if inverted else '经济健康'))
    if 'DXY' in macro:
        v=macro['DXY']['value'];chg=macro['DXY'].get('chg_5d',0)
        signals.append(('DXY','%.1f'%v,'强势' if v>101 else('弱势' if v<98 else '中性'),'利空黄金/新兴市场' if v>101 else ''))
    if 'USDCNY' in macro:
        v=macro['USDCNY']['value'];chg=macro['USDCNY'].get('chg_5d',0)
        signals.append(('USD/CNY','%.2f'%v,'人民币贬值' if chg>0.2 else '稳定','外资流出压力' if chg>0.5 else ''))
    
    # Overall bias
    dxy=macro.get('DXY',{})
    us10y=macro.get('US10Y',{})
    if dxy.get('value',100)>101:
        if 'inverted' in str(signals):bias='避险模式 — 黄金/债券占优'
        else:bias='美元强势 — 新兴市场/商品承压'
    elif dxy.get('value',100)<98:bias='美元弱势 — 新兴市场/商品受益'
    else:bias='中性 — 各品种按自身结构操作'
    
    return {'signals':signals,'bias':bias}

def stock_macro_context(stock_type):
    """根据股票类型给出宏观背景影响"""
    macro=load_macro()
    impacts=[]
    dxy=macro.get('DXY',{}).get('value',100)
    us10y=macro.get('US10Y',{}).get('value',4.5)
    
    if stock_type in ('gold','copper','commodity'):
        if dxy>101:impacts.append('⚠️ 美元强势压制金价/商品')
        elif dxy<98:impacts.append('✅ 美元弱势利好商品')
    if stock_type in ('tech','growth'):
        if us10y>4.5:impacts.append('⚠️ 高利率压制成股估值')
        elif us10y<4:impacts.append('✅ 低利率利好成长股')
    if stock_type in ('bank','financial'):
        if us10y>4:impacts.append('✅ 高利率利好银行息差')
    if stock_type in ('hk','export'):
        cny=macro.get('USDCNY',{}).get('chg_5d',0)
        if cny>0.3:impacts.append('⚠️ 人民币贬值,港股/出口承压')
    
    return impacts

if __name__=='__main__':
    macro=load_macro()
    s=macro_signal(macro)
    print('宏观因子:')
    for sig in s['signals']:
        print('  %-12s %s %s'%(sig[0],sig[1],sig[3] if sig[3] else sig[2]))
    print('\n宏观基调:',s['bias'])
