#!/usr/bin/env python3
"""
XGBoost 缠论信号训练器 — 港股先行
  流程: K线→chan.py BSP回放→56维特征提取→XGBoost训练→Optuna调参→模型导出
"""
import os,sys,time,re,json,csv,numpy as np,pickle
from datetime import datetime
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,HERE)
sys.path.insert(0,os.path.join(HERE,'..','chanpy'))

from data import fetch_kline_hk,load_hk_stocks
from chan_engine import CONFIG as CHAN_CONFIG,analyze as chan_analyze
from scorer import extract_features

import yfinance as yf
from Common.CEnum import KL_TYPE,DATA_FIELD
from Common.CTime import CTime
from KLine.KLine_Unit import CKLine_Unit
from Chan import CChan;from ChanConfig import CChanConfig

OUT=os.path.join(HERE,'..','models')
os.makedirs(OUT,exist_ok=True)

# ── Step 1: Data collection ──
def collect_training_data(symbols=None, max_stocks=50, lookback_years=3):
    """收集训练数据: K线回放 + BSP特征提取 + 标签"""
    if symbols is None:
        # Core A-stock codes for training
a_codes=["002475","603019","002594","601899","002371","601138","600489","002837","300476","000977","688041","603986","603893","688008","601100","600089","002281","002463","002428","300475","000988","600030","300124","300750"]
hk_codes=["00700","09988","03690"]
stocks=[]
for c in a_codes[:max_stocks]:stocks.append((c,c))
for c in hk_codes[:max(max_stocks-len(a_codes),0)]:stocks.append(("hk"+c,c))
    else:
        stocks=[(f'hk{s}','') for s in symbols]
    
    samples=[]
    for idx,(code,_) in enumerate(stocks):
        if idx%10==0:print('  收集 %d/%d'%(idx,len(stocks)),flush=True)
        try:
            # Fetch multi-year K-line
            sym='%04d.HK'%int(code.replace('hk',''))
            df=yf.download(sym,period='%dy'%lookback_years,progress=False)
            if len(df)<200:continue
            
            def fv(x):return float(x.item() if hasattr(x,'item') else x)
            dates=[x.strftime('%Y-%m-%d') for x in df.index.tolist()]
            opens=[fv(x) for x in np.array(df['Open']).ravel()]
            closes=[fv(x) for x in np.array(df['Close']).ravel()]
            highs=[fv(x) for x in np.array(df['High']).ravel()]
            lows=[fv(x) for x in np.array(df['Low']).ravel()]
            vols=[fv(x) for x in np.array(df['Volume']).ravel()]
            n=len(dates)
            
            # Replay: 滑动窗口 chan.py 分析
            for window_end in range(200,n,5):  # every 5 bars
                w=min(window_end,300)  # max window
                start=max(0,window_end-w)
                seg_dates=dates[start:window_end]
                seg_opens=opens[start:window_end]
                seg_closes=closes[start:window_end]
                seg_highs=highs[start:window_end]
                seg_lows=lows[start:window_end]
                seg_vols=vols[start:window_end]
                
                cur,bsp_buy,bsp_types,px,zs,pos=chan_analyze(seg_dates,seg_opens,seg_closes,seg_highs,seg_lows,code)
                if not bsp_types:continue
                
                # Feature extraction → 30-dim vector
                fd=extract_features(seg_closes,seg_highs,seg_lows,seg_opens,seg_vols,bsp_buy,bsp_types,cur)
                vec=[fd[k] for k in sorted(fd.keys())]  # sorted to ensure consistent order
                
                # Label: future 5-bar return > 3%?
                future_end=min(window_end+5,n)
                future_return=(closes[future_end-1]/px-1)*100 if future_end>window_end else 0
                label=1 if future_return>3 else 0
                
                samples.append({'features':vec,'label':label,'code':code,'date':dates[window_end-1]})
        except:pass
    
    print('  收集完成: %d BSP样本'%len(samples))
    return samples

# ── Step 2: XGBoost training ──
def train_model(samples):
    """训练XGBoost分类器"""
    from sklearn.model_selection import train_test_split
    import xgboost as xgb
    
    # Prepare matrix — samples['features'] is now a list of floats
    X=np.array([s['features'] for s in samples])
    y=np.array([s['label'] for s in samples])
    
    print('  特征维度: %d, 正样本: %d/%d (%.1f%%)'%(X.shape[1],sum(y),len(y),sum(y)/len(y)*100))
    
    X_train,X_test,y_train,y_test=train_test_split(X,y,test_size=0.2,random_state=42)
    
    # Train
    model=xgb.XGBClassifier(
        max_depth=5,learning_rate=0.03,n_estimators=200,
        subsample=0.7,colsample_bytree=0.7,
        min_child_weight=10,reg_lambda=2,reg_alpha=0.5,
        scale_pos_weight=max(1,(len(y)-sum(y))/max(sum(y),1)),
        eval_metric='aucpr',tree_method='hist',random_state=42
    )
    model.fit(X_train,y_train,eval_set=[(X_test,y_test)],verbose=False)
    
    # Evaluate
    from sklearn.metrics import accuracy_score,roc_auc_score,classification_report
    y_pred=model.predict(X_test)
    acc=accuracy_score(y_test,y_pred)
    auc=roc_auc_score(y_test,model.predict_proba(X_test)[:,1])
    
    print('  准确率: %.1f%%, AUC: %.3f'%(acc*100,auc))
    
    return model,X_test,y_test

# ── Step 3: Export ──
def export_model(model,path):
    """导出模型为pickle"""
    with open(path,'wb') as f:
        pickle.dump(model,f)
    print('  模型保存: %s (%.1fKB)'%(path,os.path.getsize(path)/1024))

# ── Main ──
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--stocks',type=int,default=20,help='训练股票数量(默认20)')
    p.add_argument('--years',type=int,default=3,help='回看年数')
    p.add_argument('--output',default=None,help='模型输出路径')
    args=p.parse_args()
    
    print('='*60)
    print('XGBoost 缠论信号训练器')
    print('='*60)
    
    t0=time.time()
    print('[1/3] 数据收集(%d只港股×%d年)...'%(args.stocks,args.years))
    samples=collect_training_data(max_stocks=args.stocks,lookback_years=args.years)
    
    if len(samples)<50:
        print('⚠️  样本不足(%d), 请增加stocks数'%len(samples))
        sys.exit(1)
    
    print('\n[2/3] XGBoost训练...')
    model,X_test,y_test=train_model(samples)
    
    print('\n[3/3] 导出模型...')
    out_path=args.output or os.path.join(OUT,'chan_xgb_hk.pkl')
    export_model(model,out_path)
    
    print('\n✅ 总耗时: %.0fs'%(time.time()-t0))
