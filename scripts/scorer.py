#!/usr/bin/env python3
"""56维特征提取器 — 对齐 chan-model-xgb V2"""
import numpy as np,os,sys

def extract_features(closes,highs,lows,opens,vols,bsp_buy,bsp_types,cur):
    """56维特征向量 — 完整版"""
    C=np.array(closes,dtype=float);H=np.array(highs,dtype=float)
    L=np.array(lows,dtype=float);O=np.array(opens,dtype=float);V=np.array(vols,dtype=float)
    n=len(C);cc,ch,cl,co,cv=C[-1],H[-1],L[-1],O[-1],V[-1]
    f={}
    
    # ═══ 1. BSP one-hot (12) ═══
    for d in ['buy','sell']:
        match=bsp_buy if d=='buy' else (not bsp_buy and bsp_types)
        for bt in ['type1','type1p','type2','type2s','type3a','type3b']:
            f['bsp_%s_%s'%(d,bt)]=1.0 if match and bt in str(bsp_types) else 0.0
    
    # ═══ 2. 价格动量 (6) ═══
    f['price_return_1']=(cc/C[-2]-1)*100 if n>=2 else 0
    f['price_return_3']=(cc/C[-4]-1)*100 if n>=4 else 0
    f['price_return_5']=(cc/C[-6]-1)*100 if n>=6 else 0
    f['price_return_10']=(cc/C[-11]-1)*100 if n>=11 else 0
    cr=max(ch-cl,1e-10)
    f['price_range']=(ch-cl)/max(cc,1e-10)*100
    f['body_ratio']=abs(cc-co)/cr if cr>0 else 0
    
    # ═══ 3. 均线偏离 (5) ═══
    for w in [5,10,20,60]:
        f['ma_%d_dist'%w]=(cc-np.mean(C[-w:]))/max(cc,1e-10)*100 if n>=w else 0
    if n>=20:
        ma5=np.mean(C[-5:]);ma20=np.mean(C[-20:])
        f['ma_cross_5_20']=(ma5-ma20)/max(ma20,1e-10)*100
    else:f['ma_cross_5_20']=0
    
    # ═══ 4. MACD (5) ═══
    if n>=26:
        ema12=ema(C,12);ema26=ema(C,26)
        macd_line=ema12-ema26
        sig=ema_smooth(macd_line,9)
        hist=macd_line-sig
        f['macd_value']=macd_line[-1]/max(cc,1e-10)*100
        f['macd_signal']=sig[-1]/max(cc,1e-10)*100
        f['macd_hist']=hist[-1]/max(cc,1e-10)*100
        f['macd_cross']=1.0 if (macd_line[-2]<sig[-2] and macd_line[-1]>sig[-1]) else (-1.0 if (macd_line[-2]>sig[-2] and macd_line[-1]<sig[-1]) else 0)
        f['macd_hist_slope']=(hist[-1]-hist[-5])/max(abs(hist[-5]),1e-10) if n>=5 else 0
    else:
        for k in ['macd_value','macd_signal','macd_hist','macd_cross','macd_hist_slope']:f[k]=0
    
    # ═══ 5. 布林带 (2) ═══
    if n>=20:
        sma20=np.mean(C[-20:]);std20=np.std(C[-20:])
        boll_upper=sma20+2*std20;boll_lower=sma20-2*std20
        f['boll_pct_b']=((cc-boll_lower)/(boll_upper-boll_lower)*100) if boll_upper!=boll_lower else 50
        f['boll_width']=((boll_upper-boll_lower)/max(sma20,1e-10)*100)
    else:
        f['boll_pct_b']=50;f['boll_width']=0
    
    # ═══ 6. 波动率 (3) ═══
    if n>=15:
        tr=[max(H[i]-L[i],abs(H[i]-C[i-1]),abs(L[i]-C[i-1])) for i in range(1,n)]
        f['atr_norm']=np.mean(tr[-14:])/max(cc,1e-10)*100 if tr else 0
        returns=[(C[i]-C[i-1])/C[i-1]*100 for i in range(max(1,n-5),n)]
        f['volatility_5']=np.std(returns) if len(returns)>1 else 0
        returns10=[(C[i]-C[i-1])/C[i-1]*100 for i in range(max(1,n-10),n)]
        f['volatility_10']=np.std(returns10) if len(returns10)>1 else 0
        # volatility ratio
        f['volatility_ratio']=f['volatility_5']/max(f['volatility_10'],1e-10) if f['volatility_10']>0 else 1
    else:
        f['atr_norm']=f['volatility_5']=f['volatility_10']=f['volatility_ratio']=0
    
    # ═══ 7. RSI (2) ═══
    if n>=15:
        gains=[];losses=[]
        for i in range(n-14,n):d=C[i]-C[i-1];gains.append(max(d,0));losses.append(max(-d,0))
        rsi=100-100/(1+np.mean(gains)/max(np.mean(losses),1e-10)) if np.mean(losses)>0 else 50
        f['rsi']=rsi
        # RSI divergence (simple: compare trend direction)
        if n>=30:
            rsi_old=sum(1 for i in range(n-29,n-14) if C[i]>C[i-1])/15*100
            f['rsi_divergence']=(rsi-rsi_old)
        else:f['rsi_divergence']=0
    else:
        f['rsi']=50;f['rsi_divergence']=0
    
    # ═══ 8. ADX (2) ═══
    if n>=28:
        adx_val=adx(H,L,C,14)
        f['adx']=adx_val
        f['trend_strength']=1.0 if adx_val>25 else 0.0
    else:
        f['adx']=0;f['trend_strength']=0
    
    # ═══ 9. Volume (2) ═══
    if n>=20:
        v_mean=np.mean(V[-20:]);v_std=np.std(V[-20:])
        f['volume_zscore']=((cv-v_mean)/max(v_std,1e-10)) if v_std>0 else 0
        f['volume_ratio_ma']=cv/max(v_mean,1e-10)
    else:
        f['volume_zscore']=0;f['volume_ratio_ma']=1
    
    # ═══ 10. 缠论 Chan features (17) ═══
    if cur:
        # Bi features (5)
        if cur.bi_list:
            last_bi=cur.bi_list[-1]
            bi_begin=float(last_bi.begin_klc.low) if last_bi.is_down else float(last_bi.begin_klc.high)
            bi_end=float(last_bi.end_klc.high) if last_bi.is_down else float(last_bi.end_klc.low)
            bi_len=abs(bi_end-bi_begin)/max(bi_begin,1e-10)*100
            f['bi_slope']=bi_len/(last_bi.end_klc.idx-last_bi.begin_klc.idx+1) if last_bi.end_klc.idx>last_bi.begin_klc.idx else 0
            f['bi_strength']=bi_len
            f['bi_len_klu']=float(last_bi.end_klc.idx-last_bi.begin_klc.idx+1)
            f['bi_macd_area']=0  # complex
            f['bi_macd_peak']=0
        else:
            for k in ['bi_slope','bi_strength','bi_len_klu','bi_macd_area','bi_macd_peak']:f[k]=0
        
        # ZS features (3)
        f['zs_count']=len(cur.zs_list)/3.0
        if cur.zs_list:
            z=cur.zs_list[-1];zl=float(z.low);zh=float(z.high)
            z_width=(zh-zl)/max(cc,1e-10)*100
            f['zs_width_norm']=z_width
            f['zs_peak_range_norm']=z_width  # simplified
            f['zs_breakout_dir']=1.0 if cc>zh else(-1.0 if cc<zl else 0)
        else:
            f['zs_width_norm']=f['zs_peak_range_norm']=f['zs_breakout_dir']=0
        
        # Seg features (3)
        if hasattr(cur,'seg_list') and cur.seg_list and len(cur.seg_list)>0:
            seg=cur.seg_list[-1]
            # CSeg compatible: use bi_list for amp
            if hasattr(seg,'bi_list') and seg.bi_list:
                f['seg_amp']=1.0  # simplified
                f['seg_bi_cnt']=len(seg.bi_list)
                f['seg_is_up']=1.0 if seg.bi_list[-1].is_up else 0.0
            else:
                f['seg_amp']=f['seg_bi_cnt']=f['seg_is_up']=0
        else:
            f['seg_amp']=f['seg_bi_cnt']=f['seg_is_up']=0
        
        # Divergence (2)
        f['divergence_ratio']=0;f['divergence_type']=0
        # bsp_distance (1)
        f['bsp1_distance']=0
        # Multi-TF (3)
        f['higher_tf_trend']=0;f['multi_tf_agreement']=0;f['nesting_confirmed']=0
    else:
        for k in ['bi_slope','bi_strength','bi_len_klu','bi_macd_area','bi_macd_peak',
                  'zs_count','zs_width_norm','zs_peak_range_norm','zs_breakout_dir',
                  'seg_amp','seg_bi_cnt','seg_is_up',
                  'divergence_ratio','divergence_type','bsp1_distance',
                  'higher_tf_trend','multi_tf_agreement','nesting_confirmed']:f[k]=0
    
    return f

def ema(data,window):
    if len(data)<window:return np.zeros(len(data))
    alpha=2/(window+1)
    result=np.zeros(len(data));result[window-1]=np.mean(data[:window])
    for i in range(window,len(data)):result[i]=alpha*data[i]+(1-alpha)*result[i-1]
    return result

def ema_smooth(data,window):
    if len(data)<window:return np.zeros(len(data))
    alpha=2/(window+1)
    result=np.zeros(len(data));result[window-1]=data[window-1]
    for i in range(window,len(data)):result[i]=alpha*data[i]+(1-alpha)*result[i-1]
    return result

def adx(high,low,close,period=14):
    n=len(close)
    if n<period*2:return 0
    tr=[max(high[i]-low[i],abs(high[i]-close[i-1]),abs(low[i]-close[i-1])) for i in range(1,n)]
    plus_dm=[max(high[i]-high[i-1],0) if high[i]-high[i-1]>low[i-1]-low[i] else 0 for i in range(1,n)]
    minus_dm=[max(low[i-1]-low[i],0) if low[i-1]-low[i]>high[i]-high[i-1] else 0 for i in range(1,n)]
    tr_s=sum(tr[-period:]);plus_s=sum(plus_dm[-period:]);minus_s=sum(minus_dm[-period:])
    if tr_s==0:return 0
    plus_di=plus_s/tr_s*100;minus_di=minus_s/tr_s*100
    dx=abs(plus_di-minus_di)/(plus_di+minus_di)*100 if plus_di+minus_di>0 else 0
    return dx

def score_from_features(feats):
    """从56维特征计算规则评分(0-100)"""
    score=50
    buy=sum(1 for k,v in feats.items() if k.startswith('bsp_buy_') and v>0)
    sell=sum(1 for k,v in feats.items() if k.startswith('bsp_sell_') and v>0)
    if buy>0:
        if any(k.endswith('type3a') for k in feats if feats[k]>0):score+=25
        elif any(k.endswith('type2') or k.endswith('type2s') for k in feats if feats[k]>0):score+=20
    if sell>0:score-=15
    # ZS position
    bd=feats.get('zs_breakout_dir',0)
    if bd==0:score+=15
    elif bd>0:score+=5
    # MACD
    if feats.get('macd_cross',0)>0:score+=5
    elif feats.get('macd_cross',0)<0:score-=5
    # RSI
    rsi=feats.get('rsi',50)
    if 30<rsi<70:score+=5
    elif rsi>75:score-=5
    # ADX
    adx_v=feats.get('adx',0)
    if adx_v>30:score+=3  # strong trend
    # Volume
    vz=feats.get('volume_zscore',0)
    if vz>1.5:score+=5
    return max(0,min(100,score))
