import numpy as np
#!/usr/bin/env python3
"""
缠论多维度分析 v3.0 — chan.py + XGB评分 + 知识库确认
  用法: python3 analyze.py 002475           # A股
        python3 analyze.py hk00700           # 港股
        python3 analyze.py --scan --market hk  # 全市场扫描
"""
import os,sys,argparse,openpyxl,time
from datetime import datetime
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,HERE)

from data import fetch_kline_a,fetch_kline_hk,load_a_stocks,load_hk_stocks,fetch_hk_quotes,fetch_a_quotes
from chan_engine import analyze as chan_analyze,get_bsp_label
from scorer import extract_features,score_from_features
from chan_kb import evaluate
from smc_insight import smc_analysis
from macro import load_macro,macro_signal
from volume_sector import volume_analysis,get_stock_sector,sector_analysis
from sector_heat import sector_signal,get_sector_heat
import pickle

MODEL_PATH=os.path.join(HERE,'..','models','chan_xgb_hk.pkl')
_xgb_model=None

def load_model():
    global _xgb_model
    if _xgb_model is None and os.path.exists(MODEL_PATH):
        try:
            _xgb_model=pickle.load(open(MODEL_PATH,'rb'))
            print('  📦 已加载训练模型 (XGBoost)')
        except:pass
    return _xgb_model

def predict_score(feats):
    """混合评分: 优先XGBoost模型，回退规则"""
    model=load_model()
    feat_len=len(feats)
    if model:
        vec=np.array([[feats[k] for k in sorted(feats.keys())]])
        # 尝试模型推理，维度不匹配则回退
        try:
            if model.n_features_in_==feat_len:
                proba=model.predict_proba(vec)[0,1]
                return int(proba*100)
        except:
            pass
    return score_from_features(feats)

def analyze_single(code_or_name,market='a'):
    """单股分析"""
    print('='*60)
    print('缠论多维度分析: %s'%code_or_name)
    print('='*60)
    
    # ── Macro overview ──
    try:
        from macro import load_macro,macro_signal
        from futures_sentiment import get_futures_position,analyze_sentiment
        from futures_analysis import analyze_all_futures
        
        macro=load_macro();ms=macro_signal(macro)
        fp=get_futures_position();fs=analyze_sentiment(fp)
        fm=analyze_all_futures()
        
        print()
        print('🌍 宏观环境:')
        print('  📈 股指期货: %s'%fs['bias'])
        print('  💵 美元: DXY %.1f (%s)'%(macro.get('DXY',{}).get('value',0),'强势' if macro.get('DXY',{}).get('value',100)>101 else '中性'))
        print('  📊 美债10Y: %.2f%% (%s)'%(macro.get('US10Y',{}).get('value',0),'高利率' if macro.get('US10Y',{}).get('value',0)>4.5 else '中性'))
        print('  🇨🇳 USD/CNY: %.2f'%macro.get('USDCNY',{}).get('value',0))
        print('  🥇 商品: ',end='')
        comm=[] 
        for f in fm:
            if f:comm.append('%s %s %+.1f%%'%(f['name'].replace('COMEX',''),f['bsp'],f['chg_pct']))
        print(' | '.join(comm[:3]))
        print()
    except:pass
    
    print('─ 个股分析 ─')
    
    if market=='hk':
        data=fetch_kline_hk(code_or_name)
    else:
        data=fetch_kline_a(code_or_name)
    
    if not data:
        print('❌ K线数据获取失败')
        return
    dates,opens,closes,highs,lows,vols=data
    px=closes[-1]
    
    # Step 1: chan.py
    print('[1/3] chan.py 结构分析...')
    cur,bsp_buy,bsp_types,px,zs,pos=chan_analyze(dates,opens,closes,highs,lows,code_or_name)
    label=get_bsp_label(bsp_buy,bsp_types,pos)
    types_str='/'.join(bsp_types) if bsp_types else '-'
    print('  BSP: %s | 中枢: %s | 位置: %s | Bi:%d ZS:%d'%(label,zs or '无',pos,len(cur.bi_list) if cur else 0,len(cur.zs_list) if cur else 0))
    
    # Step 2: scoring
    print('[2/3] XGB 56维特征提取+打分...')
    fd=extract_features(closes,highs,lows,opens,vols,bsp_buy,bsp_types,cur);score=predict_score(fd)
    print('  评分: %d/100'%score)
    
    # Step 3: KB confirmation
    print('[3/3] 缠论知识库确认...')
    result=evaluate(code_or_name if market=='hk' else code_or_name,code_or_name,px,bsp_buy,bsp_types,pos,zs,score)
    
    print('\n📊 最终分析:')
    print('  标的: %s (¥%s)'%(result['name'],str(int(result['price']))))
    print('  方向: %s | 信号: %s | 评分: %d/100'%(result['direction'],result['signal'],result['score']))
    print('  风险: %s | 盈利预期: %s'%(result['risk'],result['profit'] or 'N/A'))
    
    # 阿娇标准: 年涨>100%的二买存疑
    if len(closes)>=120:
        ytd_chg=(closes[-1]/closes[-120]-1)*100
        if ytd_chg>100 and bsp_buy and '3' not in str(bsp_types):
            print('  ⚠️ 阿娇警告: 年涨%.0f%% + 二买 — 趋势中二买存疑，等三买确认'%ytd_chg)
    
    # 止损止盈
    if cur and cur.zs_list:
        z_last=cur.zs_list[-1];zl=float(z_last.low);zh=float(z_last.high)
        if bsp_buy:
            entry=int(zl);stop=int(zl*0.97);tp1=int(zh);tp2=int(zh*1.1)
            rr=abs(tp1-entry)/max(abs(entry-stop),1)
            print('  🎯 买入区: ¥%d~¥%d | 止损: ¥%d | TP1: ¥%d(+%d%%) | TP2: ¥%d(+%d%%) | R:R=%.1f:1'%(
                entry,int(zl*1.03),stop,tp1,int((tp1-px)/px*100),tp2,int((tp2-px)/px*100),rr))
    
    smc=smc_analysis(code_or_name,result['name'],px,bsp_buy,zs,pos)
    print('  🧠 SMC视角: %s'%smc['verdict'])
    vol=volume_analysis([float(x) for x in closes],[float(x) for x in vols])
    print('  📊 量价: %s (vol_ratio=%.1fx)'%(vol['signal'],vol['vol_ratio']))
    sec=sector_analysis(code_or_name)
    print('  📈 板块: %s → %s'%(sec['sector'],sec['top_sector']))
    heat_data=get_sector_heat()
    sh=sector_signal(code_or_name,heat=heat_data)
    print('  🔥 板块热度: %s %+.1f%% (%d%%↑)'%(sh['signal'],sh['avg_chg'],sh['up_ratio']))
    if result['confirmations']:
        print('  ✅ 确认:')
        for c in result['confirmations']:print('    - '+c)
    
    return result

def scan_market(market='a',min_score=65):
    """全市场扫描"""
    print('🔍 %s全市场扫描 (min_score≥%d)...'%({'a':'A股','hk':'港股'}[market],min_score))
    
    if market=='a':
        stocks=load_a_stocks()
        print('  股票池: %d'%len(stocks))
        quotes=fetch_a_quotes(stocks)
        fetch_kline=fetch_kline_a
    else:
        stocks=load_hk_stocks()
        print('  股票池: %d'%len(stocks))
        quotes=fetch_hk_quotes(stocks)
        fetch_kline=fetch_kline_hk
    
    print('  行情: %d'%len(quotes))
    
    # Sort by change
    items=list(quotes.items())
    items.sort(key=lambda x:abs(x[1]['change_pct']),reverse=True)
    print('  全量分析: %d stocks...'%len(items))
    
    results=[]
    for idx,(code,q) in enumerate(items):
        if idx%30==0:print('    %d/%d, found %d'%(idx,len(items),len(results)))
        name='?'
        for c,n in stocks:
            if c==code or (market=='a' and c==code):name=n;break
        px=q['price'];chg=q['change_pct']
        
        data=fetch_kline(code)
        if not data:continue
        dates,opens,closes,highs,lows,vols=data
        
        cur,bsp_buy,bsp_types,px2,zs,pos=chan_analyze(dates,opens,closes,highs,lows,code)
        fd=extract_features(closes,highs,lows,opens,vols,bsp_buy,bsp_types,cur);score=predict_score(fd)
        
        if score>=min_score:
            label=get_bsp_label(bsp_buy,bsp_types,pos)
            results.append({'code':code,'name':name,'score':score,'price':px,'change_pct':chg,
                'suggestion':label,'reason':'%s|%s|%s'%(pos,'/'.join(bsp_types) if bsp_types else '-',zs),
                'time':datetime.now().strftime('%H:%M')})
    
    results.sort(key=lambda x:-x['score'])
    
    # Excel
    wb=openpyxl.Workbook();ws=wb.active;ws.title='缠论扫描'
    hdrs=['排名','代码','名称','评分','价格','涨跌幅','建议','理由','时间']
    from openpyxl.styles import Font,PatternFill
    hf=PatternFill(start_color='1a1a2e',end_color='1a1a2e',fill_type='solid')
    for c,h in enumerate(hdrs,1):ws.cell(1,c,h).fill=hf;ws.cell(1,c,h).font=Font(color='ffffff',bold=True)
    for i,r in enumerate(results):
        ws.cell(i+2,1,i+1)
        for c,k in enumerate(['code','name','score','price','change_pct','suggestion','reason','time'],1):
            ws.cell(i+2,c+1,r.get(k))
    out=os.path.expanduser('~/chan_scan_%s.xlsx'%market)
    wb.save(out)
    
    print('\n🏆 Top 15:')
    for i,r in enumerate(results[:15]):
        print(' %2d. %-10s %3d分 %+5.1f%% %s'%(i+1,r['name'],r['score'],r['change_pct'],r['suggestion']))
    print('Saved: %s | %d signals'%(out,len(results)))

if __name__=='__main__':
    p=argparse.ArgumentParser(description='缠论多维度分析')
    p.add_argument('code',nargs='?',help='股票代码/港股hk前缀')
    p.add_argument('--scan',action='store_true',help='全市场扫描')
    p.add_argument('--market',default='a',choices=['a','hk'],help='市场(a/hk)')
    p.add_argument('--min-score',type=int,default=60,help='最低评分')
    args=p.parse_args()
    
    if args.scan:
        scan_market(args.market,args.min_score)
    elif args.code:
        market='hk' if args.code.startswith('hk') else 'a'
        analyze_single(args.code,market)
    else:
        print('用法: python3 analyze.py <code> | --scan [--market a|hk]')
