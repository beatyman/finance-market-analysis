# 数据源说明

## 行情
- A股腾讯: `http://qt.gtimg.cn/q=sh600001,sz002475,...` 批量获取, parts[32]=涨跌幅
- 港股腾讯: `http://qt.gtimg.cn/q=hk00700,...` hk前缀

## K线
- A股腾讯: `ifzq.gtimg.cn/...?param=sz002475,day,,,200,qfq` → `qfqday`(非day)
- 港股腾讯: `ifzq.gtimg.cn/...?param=hk00700,day,,,200,qfq` → `day`(需-L重定向)
- yfinance单股: MultiIndex列, 需`np.array(df['Close']).ravel()`
- 港股yfinance: `'%04d.HK'%int(code)` 如0700.HK

## 期货/宏观
- COMEX: yfinance GC=F SI=F HG=F
- 美债: yfinance ^TNX ^FVX
- 美元: yfinance DX-Y.NYB CNY=X
- 股指期货: AKShare ak.get_rank_sum_daily() (CFFEX)

## chan.py API
- Bi: bi.begin_klc.low (不是.begin_klc.klc.low)
- Seg: CSeg, 属性因版本而异, 用bi_list推导amp
- ZS: float(z.low), float(z.high)
