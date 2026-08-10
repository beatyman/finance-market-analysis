#!/usr/bin/env python3
"""
XGBoost 缠论信号训练器 — chan.py 原版 (Vespa314 CChan)
沪深300全量训练: K线→chan.py BSP回放→特征提取→XGBoost训练→模型导出
"""
import os,sys,time,re,json,csv,numpy as np,pickle
from datetime import datetime

HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,HERE)
sys.path.insert(0,os.path.join(HERE,'..','chanpy'))

# ── 使用原始 chan.py (Vespa314 CChan) trigger_step 模式 ──
from chan_engine import analyze as chan_analyze, get_bsp_label
from scorer import extract_features
from data import fetch_kline_hk, load_hk_stocks

import yfinance as yf
from Common.CEnum import KL_TYPE,DATA_FIELD
from Common.CTime import CTime
from KLine.KLine_Unit import CKLine_Unit
from Chan import CChan
from ChanConfig import CChanConfig

OUT=os.path.join(HERE,'..','models')
os.makedirs(OUT,exist_ok=True)

# ── Step 1: Data collection ──
def collect_training_data(symbols=None, max_stocks=300, lookback_years=3):
    """收集训练数据: K线回放 + chan.py BSP特征提取 + 标签"""
    import baostock as bs
    bs.login()
    
    if symbols is None:
        # Use CSI300 stocks via baostock
        stocks = []
        csv_path = os.path.join(HERE, '..', 'references', 'hs300_stocks.csv')
        if os.path.exists(csv_path):
            with open(csv_path, 'r', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    code = row.get('成分券代码', row.get('code', row.get('证券代码', '')))
                    name = row.get('成分券名称', row.get('name', row.get('证券名称', '')))
                    if code and len(code) == 6:
                        stocks.append((code, name))
        if not stocks:
            # Fallback core A-stock codes
            a_codes = ["002475","603019","002594","601899","002371","601138",
                       "600489","002837","300476","000977","688041","603986"]
            stocks = [(c, c) for c in a_codes]
        stocks = stocks[:max_stocks]
    else:
        stocks=[(f'hk{s}','') for s in symbols]
    
    samples=[]
    skipped = 0
    t_start = time.time()
    for idx,(code,_) in enumerate(stocks):
        if idx>0 and idx%10==0:
            elapsed = time.time()-t_start
            rate = idx/elapsed if elapsed>0 else 0
            eta = (len(stocks)-idx)/rate if rate>0 else 0
            print('  [%d/%d] 已收集 %d 样本, 跳过 %d | %.1fs/只 ETA %.0fs'%(
                idx,len(stocks),len(samples),skipped,elapsed/max(idx,1),eta),flush=True)
        try:
            # Fetch multi-year K-line via baostock
            suffix = 'sh' if code.startswith('6') else 'sz'
            symbol = suffix + '.' + code
            rs = bs.query_history_k_data_plus(symbol,
                'date,open,high,low,close,volume',
                start_date='2023-01-01', end_date='2026-08-10',
                frequency='d', adjustflag='2')
            rows = []
            while rs.error_code == '0' and rs.next(): 
                rows.append(rs.get_row_data())
            if len(rows) < 200: 
                skipped += 1
                continue
            
            dates = [r[0] for r in rows]
            opens = [float(r[1]) for r in rows]
            highs = [float(r[2]) for r in rows]
            lows = [float(r[3]) for r in rows]
            closes = [float(r[4]) for r in rows]
            vols = [float(r[5]) for r in rows]
            n = len(dates)
            
            # Replay: 滑动窗口 chan.py 分析 (step=60 for speed)
            stock_samples = 0
            for window_end in range(200, n, 60):  # ~10 windows per stock
                w = min(window_end, 250)  # max window 250
                start = max(0, window_end - w)
                seg_dates = dates[start:window_end]
                seg_opens = opens[start:window_end]
                seg_closes = closes[start:window_end]
                seg_highs = highs[start:window_end]
                seg_lows = lows[start:window_end]
                seg_vols = vols[start:window_end]
                
                # ── 使用原始 chan.py (Vespa314 CChan) ──
                cur, bsp_buy, bsp_types, px, zs, pos = chan_analyze(
                    seg_dates, seg_opens, seg_closes, seg_highs, seg_lows, code)
                
                if not bsp_types:
                    continue
                
                # Feature extraction → 56-dim vector
                fd = extract_features(
                    seg_closes, seg_highs, seg_lows, seg_opens, seg_vols,
                    bsp_buy, bsp_types, cur)
                vec = [fd[k] for k in sorted(fd.keys())]
                
                # Label: future 5-bar return > 2%?
                future_end = min(window_end + 5, n)
                future_return = (closes[future_end-1] / px - 1) * 100 if future_end > window_end else 0
                label = 1 if future_return > 2 else 0
                
                samples.append({
                    'features': vec,
                    'label': label,
                    'code': code,
                    'date': dates[window_end-1]
                })
                stock_samples += 1
                
        except Exception as e:
            if idx < 5:
                print('  ⚠ %s: %s' % (code, str(e)[:80]))
            skipped += 1
    
    bs.logout()
    pos = sum(1 for s in samples if s['label'] == 1)
    print('  收集完成: %d BSP样本 (正样本: %d, %.1f%%), 跳过 %d 只' % (
        len(samples), pos, pos/max(len(samples),1)*100, skipped))
    return samples


# ── Step 2: XGBoost training ──
def train_model(samples):
    """训练XGBoost分类器"""
    from sklearn.model_selection import train_test_split
    import xgboost as xgb
    
    X = np.array([s['features'] for s in samples])
    y = np.array([s['label'] for s in samples])
    
    pos_rate = sum(y) / max(len(y), 1)
    print('  特征维度: %d, 正样本: %d/%d (%.1f%%)' % (
        X.shape[1], sum(y), len(y), pos_rate * 100))
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42)
    
    # Train
    scale_weight = max(1, (len(y) - sum(y)) / max(sum(y), 1))
    model = xgb.XGBClassifier(
        max_depth=6,
        learning_rate=0.02,
        n_estimators=300,
        subsample=0.7,
        colsample_bytree=0.7,
        min_child_weight=15,
        reg_lambda=2,
        reg_alpha=0.5,
        scale_pos_weight=scale_weight,
        eval_metric='aucpr',
        tree_method='hist',
        random_state=42
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
    
    # Evaluate
    from sklearn.metrics import (accuracy_score, roc_auc_score, precision_score,
                                  recall_score, f1_score, classification_report)
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]
    
    acc = accuracy_score(y_test, y_pred)
    auc = roc_auc_score(y_test, y_proba)
    prec = precision_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    
    print('  准确率: %.1f%%, AUC: %.4f, Precision: %.3f, Recall: %.3f, F1: %.3f' % (
        acc * 100, auc, prec, rec, f1))
    
    # Feature importance
    importances = model.feature_importances_
    top_idx = np.argsort(importances)[-10:][::-1]
    print('  Top10特征重要性:')
    for i in top_idx:
        print('    F%02d: %.4f' % (i, importances[i]))
    
    return model, X_test, y_test


# ── Step 3: Export ──
def export_model(model, path):
    """导出模型为pickle"""
    with open(path, 'wb') as f:
        pickle.dump(model, f)
    print('  模型保存: %s (%.1fKB)' % (path, os.path.getsize(path) / 1024))


# ── Main ──
if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--stocks', type=int, default=300, help='训练股票数量(默认300)')
    p.add_argument('--years', type=int, default=3, help='回看年数')
    p.add_argument('--output', default=None, help='模型输出路径')
    args = p.parse_args()
    
    print('=' * 60)
    print('XGBoost 缠论信号训练器 — chan.py 原版 (Vespa314 CChan)')
    print('沪深300全量训练')
    print('=' * 60)
    
    t0 = time.time()
    print('[1/3] 数据收集(%d只×%d年) — chan.py BSP回放...' % (args.stocks, args.years))
    samples = collect_training_data(max_stocks=args.stocks, lookback_years=args.years)
    
    if len(samples) < 50:
        print('⚠️  样本不足(%d), 退出' % len(samples))
        sys.exit(1)
    
    print('\n[2/3] XGBoost训练...')
    model, X_test, y_test = train_model(samples)
    
    print('\n[3/3] 导出模型...')
    out_path = args.output or os.path.join(OUT, 'chan_xgb_chanpy_300.pkl')
    export_model(model, out_path)
    
    # Also save feature dimension info
    meta_path = out_path.replace('.pkl', '_meta.json')
    with open(meta_path, 'w') as f:
        json.dump({
            'feature_dim': len(samples[0]['features']),
            'n_samples': len(samples),
            'n_features': len(samples[0]['features']),
            'engine': 'chan.py (Vespa314 CChan)',
            'trained_at': datetime.now().isoformat(),
            'stocks_trained': args.stocks,
        }, f, indent=2)
    
    elapsed = time.time() - t0
    print('\n✅ 总耗时: %.0fs (%.1f分钟)' % (elapsed, elapsed / 60))
