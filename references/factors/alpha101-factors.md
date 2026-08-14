# WorldQuant Alpha101 因子库

> **来源**: WorldQuant LLC — "101 Formulaic Alphas" (Kakushadze, 2016)
> **因子总数**: 101个
> **可直接实现**: 82个（使用OHLCV+VWAP+Returns数据）
> **不可直接实现**: 19个（需IndNeutralize行业中性化或cap市值数据）
> **原始论文**: https://arxiv.org/abs/1601.00991
> **数据字段**: open, high, low, close, volume, vwap, returns
> **关键算子**: rank(截面排名), delay(滞后), delta(差分), correlation, covariance, decay_linear(线性衰减加权), ts_rank(时序排名), ts_argmax/ts_argmin, scale, SignedPower, product

## 可用性说明

在将 Alpha101 算子映射到 Qlib DSL 时，请参考以下对应关系：

- `delay(x, d)` → `Ref(x, d)`
- `delta(x, d)` → `x - Ref(x, d)`
- `ts_sum` → `Sum`, `sma` → `Mean`, `stddev` → `Std`
- `correlation` → `Corr`, `covariance` → `Cov`
- `ts_rank`, `decay_linear` → 无直接 Qlib DSL 对应，通常需要自定义实现或通过基础算子组合
- `rank` (截面排名) → 需注意时序排名与截面排名的差异，Qlib 的 `Rank` 默认为截面排名
- `IndNeutralize` → 不可用（需行业分类数据）
- `adv{N}` = N 日平均成交量 = `Mean($volume, N)`

---

## 一、动量类因子 (Momentum)

### Alpha001
- **分类**: 动量类
- **原始公式**: `rank(Ts_ArgMax(SignedPower(((returns < 0) ? stddev(returns, 20) : close), 2.), 5)) - 0.5`
- **可用性**: ✅ 可直接计算
- **说明**: 条件波动率/价格的 5 日最大值位置排名。
- **使用建议**: 捕捉短期极值点后的趋势延续或反转。

### Alpha007
- **分类**: 动量类
- **原始公式**: `((adv20 < volume) ? ((-1 * ts_rank(abs(delta(close, 7)), 60)) * sign(delta(close, 7))) : (-1 * 1))`
- **可用性**: ✅ 可直接计算
- **说明**: 只有在当前成交量大于 20 日均量时，才计算 7 日价格变化的时序排名。
- **使用建议**: 用于放量突破场景下的动量确认。

### Alpha008
- **分类**: 动量类
- **原始公式**: `(-1 * rank(((sum(open, 5) * sum(returns, 5)) - delay((sum(open, 5) * sum(returns, 5)), 10))))`
- **可用性**: ✅ 可直接计算
- **说明**: 开盘价加权的 5 日累计收益率在 10 日间的动量变化变化。
- **使用建议**: 识别价格加权后的趋势加速度变化。

### Alpha009
- **分类**: 动量类
- **原始公式**: `((0 < ts_min(delta(close, 1), 5)) ? delta(close, 1) : ((ts_max(delta(close, 1), 5) < 0) ? delta(close, 1) : (-1 * delta(close, 1))))`
- **可用性**: ✅ 可直接计算
- **说明**: 如果过去 5 天每日收盘价都在上涨或都在下跌，则顺势而为，否则取反转方向。
- **使用建议**: 强趋势下的趋势追踪。

### Alpha010
- **分类**: 动量类
- **原始公式**: `rank(((0 < ts_min(delta(close, 1), 4)) ? delta(close, 1) : ((ts_max(delta(close, 1), 4) < 0) ? delta(close, 1) : (-1 * delta(close, 1)))))`
- **可用性**: ✅ 可直接计算
- **说明**: Alpha009 的截面排名版本，周期缩短至 4 日。
- **使用建议**: 增强了因子的选股区分度。

### Alpha019
- **分类**: 动量类
- **原始公式**: `((-1 * sign(((close - delay(close, 7)) + delta(close, 7)))) * (1 + rank((1 + sum(returns, 250)))))`
- **可用性**: ✅ 可直接计算
- **说明**: 短期反转信号与长期（一年）累计收益排名的乘积。
- **使用建议**: 寻找长期趋势股中的短期回调机会。

### Alpha024
- **分类**: 动量类
- **原始公式**: `((((delta((sum(close, 100) / 100), 100) / delay(close, 100)) < 0.05) || ((delta((sum(close, 100) / 100), 100) / delay(close, 100)) == 0.05)) ? (-1 * (close - ts_min(close, 100))) : (-1 * delta(close, 3)))`
- **可用性**: ✅ 可直接计算
- **说明**: 长期均线变化较小时，取价格与百日低点的偏离反转，否则取 3 日反转。
- **使用建议**: 典型的分段函数动量因子。

### Alpha029
- **分类**: 动量类
- **原始公式**: `(min(product(rank(rank(scale(log(sum(ts_min(rank(rank((-1 * rank(delta((close - 1), 5))))), 2), 1))))), 1), 5) + ts_rank(delay((-1 * returns), 6), 5))`
- **可用性**: ✅ 可直接计算
- **说明**: 深度嵌套的排名算子结合延迟 6 日的收益率排名。
- **使用建议**: 试图通过多层排名消除异常值并捕捉深层动量。

### Alpha030
- **分类**: 动量类
- **原始公式**: `(((1.0 - rank(((sign((close - delay(close, 1))) + sign((delay(close, 1) - delay(close, 2)))) + sign((delay(close, 2) - delay(close, 3)))))) * sum(volume, 5)) / sum(volume, 20))`
- **可用性**: ✅ 可直接计算
- **说明**: 价格上涨方向的一致性排名，结合近期成交量权重的调整。
- **使用建议**: 寻找缩量上涨或放量上涨的差异化机会。

### Alpha031
- **分类**: 均值回复类
- **原始公式**: `((rank(rank(rank(decay_linear((-1 * rank(rank(delta(close, 10)))), 10)))) + rank((-1 * delta(close, 3)))) + sign(scale(correlation(adv20, low, 12))))`
- **可用性**: ✅ 可直接计算
- **说明**: 深度嵌套的收盘价变化排名，结合短期反转和量价相关性。
- **使用建议**: 捕捉中长期趋势衰减后的回归机会。

### Alpha038
- **分类**: 动量类
- **原始公式**: `((-1 * rank(Ts_Rank(close, 10))) * rank((close / open)))`
- **可用性**: ✅ 可直接计算
- **说明**: 收盘价时序排名的截面排名，与日内涨跌幅排名的复合。
- **使用建议**: 结合了时序价格位置和日内强度。

### Alpha039
- **分类**: 动量类
- **原始公式**: `((-1 * rank((delta(close, 7) * (1 - rank(decay_linear((volume / adv20), 9)))))) * (1 + rank(sum(returns, 250))))`
- **可用性**: ✅ 可直接计算
- **说明**: 结合了量调整后的 7 日价格动量和一年的长期收益。
- **使用建议**: 寻找放量后的中短期动量机会。

### Alpha046
- **分类**: 动量类
- **原始公式**: `((0.25 < (((delay(close, 20) - delay(close, 10)) / 10) - ((delay(close, 10) - close) / 10))) ? (-1 * 1) : (((((delay(close, 20) - delay(close, 10)) / 10) - ((delay(close, 10) - close) / 10)) < 0) ? 1 : (-1 * (close - delay(close, 1)))))`
- **可用性**: ✅ 可直接计算
- **说明**: 根据价格加速度的正负进行不同的反转或赋值操作。
- **使用建议**: 动量加速度衰减因子。

### Alpha047
- **分类**: 动量类
- **原始公式**: `((((rank((1 / close)) * volume) / adv20) * ((high * rank((high - close))) / (sum(high, 5) / 5))) - rank((vwap - delay(vwap, 5))))`
- **可用性**: ✅ 可直接计算
- **说明**: 复杂的量价复合动量因子。
- **使用建议**: 适用于寻找量价配合异常的标的。

### Alpha049
- **分类**: 动量类
- **原始公式**: `(((((delay(close, 20) - delay(close, 10)) / 10) - ((delay(close, 10) - close) / 10)) < (-1 * 0.1)) ? 1 : ((-1 * 1) * (close - delay(close, 1))))`
- **可用性**: ✅ 可直接计算
- **说明**: 当价格显著减速时发出买入信号，否则进行短期反转操作。
- **使用建议**: 捕捉急速下跌后的减速点。

### Alpha051
- **分类**: 动量类
- **原始公式**: `(((((delay(close, 20) - delay(close, 10)) / 10) - ((delay(close, 10) - close) / 10)) < (-1 * 0.05)) ? 1 : ((-1 * 1) * (close - delay(close, 1))))`
- **可用性**: ✅ 可直接计算
- **说明**: 与 Alpha049 相似，但提供了更宽松的加速度阈值。
- **使用建议**: 捕捉更广泛的减速反转机会。

### Alpha052
- **分类**: 动量类
- **原始公式**: `((((-1 * ts_min(low, 5)) + delay(ts_min(low, 5), 5)) * rank(((sum(returns, 240) - sum(returns, 20)) / 220))) * ts_rank(volume, 5))`
- **可用性**: ✅ 可直接计算
- **说明**: 结合了最低价的变化、长期与短期收益的差值以及近期成交量排名。
- **使用建议**: 寻找具有长期支撑且近期放量的股票。

### Alpha084
- **分类**: 动量类
- **原始公式**: `SignedPower(Ts_Rank((vwap - ts_max(vwap, 15.3217)), 20.7127), delta(close, 4.96796))`
- **可用性**: ✅ 可直接计算
- **说明**: VWAP 与其近期高点的距离排名，通过收盘价的变动进行指数化处理。
- **使用建议**: 高度非线性的动量因子。

---

## 二、波动率类因子 (Volatility)

### Alpha018
- **分类**: 波动率类
- **原始公式**: `(-1 * rank(((stddev(abs((close - open)), 5) + (close - open)) + correlation(close, open, 10))))`
- **可用性**: ✅ 可直接计算
- **说明**: 结合了日内振幅的波动、收盘价相对于开盘价的方向，以及两者的相关性。
- **使用建议**: 捕捉日内波动剧烈且方向不明确的标的。

### Alpha022
- **分类**: 波动率类
- **原始公式**: `(-1 * (delta(correlation(high, volume, 5), 5) * rank(stddev(close, 20))))`
- **可用性**: ✅ 可直接计算
- **说明**: 最高价与成交量相关性的 5 日变化量，乘以收盘价标准差排名。
- **使用建议**: 识别相关性剧烈变化伴随高波动的个股。

### Alpha034
- **分类**: 波动率类
- **原始公式**: `rank(((1 - rank((stddev(returns, 2) / stddev(returns, 5)))) + (1 - rank(delta(close, 1)))))`
- **可用性**: ✅ 可直接计算
- **说明**: 短期波动率相对于长期波动率的比值，结合价格变动进行排名。
- **使用建议**: 识别波动率突变的个股。

### Alpha040
- **分类**: 波动率类
- **原始公式**: `((-1 * rank(stddev(high, 10))) * correlation(high, volume, 10))`
- **可用性**: ✅ 可直接计算
- **说明**: 最高价的波动率排名与最高价成交量相关性的复合。
- **使用建议**: 用于识别在高波动且价量强相关的个股中的机会。

---

## 三、量价关系类因子 (Volume-Price)

### Alpha002
- **分类**: 量价关系类
- **原始公式**: `(-1 * correlation(rank(delta(log(volume), 2)), rank(((close - open) / open)), 6))`
- **可用性**: ✅ 可直接计算
- **说明**: 衡量成交量变化的排名与日内收益率排名之间的 6 日相关性。
- **使用建议**: 寻找量价方向持续背离的情况。

### Alpha003
- **分类**: 量价关系类
- **原始公式**: `(-1 * correlation(rank(open), rank(volume), 10))`
- **可用性**: ✅ 可直接计算
- **说明**: 开盘价排名与成交量排名之间的 10 日负相关。
- **使用建议**: 低开高放量或高开低放量的信号识别。

### Alpha006
- **分类**: 量价关系类
- **原始公式**: `(-1 * correlation(open, volume, 10))`
- **可用性**: ✅ 可直接计算
- **说明**: 开盘价与成交量 10 日滚动相关性的负值。
- **使用建议**: 观察价格水平与活跃度的直接关系。

### Alpha011
- **分类**: 量价关系类
- **原始公式**: `((rank(ts_max((vwap - close), 3)) + rank(ts_min((vwap - close), 3))) * rank(delta(volume, 3)))`
- **可用性**: ✅ 可直接计算
- **说明**: VWAP 偏离值的极值之和乘以成交量 3 日变化的排名。
- **使用建议**: 寻找放量且偏离均价极大的股票。

### Alpha012
- **分类**: 量价关系类
- **原始公式**: `(sign(delta(volume, 1)) * (-1 * delta(close, 1)))`
- **可用性**: ✅ 可直接计算
- **说明**: 最基础的量价背离：量增价跌或量减价涨为正信号。
- **使用建议**: 极简的背离检测算子。

### Alpha013
- **分类**: 量价关系类
- **原始公式**: `(-1 * rank(covariance(rank(close), rank(volume), 5)))`
- **可用性**: ✅ 可直接计算
- **说明**: 收盘价排名与成交量排名 5 日协方差的负排名。
- **使用建议**: 寻找价量异动的股票。

### Alpha014
- **分类**: 量价关系类
- **原始公式**: `((-1 * rank(delta(returns, 3))) * correlation(open, volume, 10))`
- **可用性**: ✅ 可直接计算
- **说明**: 收益率的变化速度排名与开盘价成交量相关性的乘积。
- **使用建议**: 动量加速度衰减伴随量能异常。

### Alpha015
- **分类**: 量价关系类
- **原始公式**: `(-1 * sum(rank(correlation(rank(high), rank(volume), 3)), 3))`
- **可用性**: ✅ 可直接计算
- **说明**: 高价排名与成交量排名相关性的 3 日累积排名。
- **使用建议**: 短期强量价信号的平滑。

### Alpha016
- **分类**: 量价关系类
- **原始公式**: `(-1 * rank(covariance(rank(high), rank(volume), 5)))`
- **可用性**: ✅ 可直接计算
- **说明**: 与 Alpha013 相似，但使用最高价排名。
- **使用建议**: 关注股价高点的量能承接能力。

### Alpha017
- **分类**: 量价关系类
- **原始公式**: `(((-1 * rank(ts_rank(close, 10))) * rank(delta(delta(close, 1), 1))) * rank(ts_rank((volume / adv20), 5)))`
- **可用性**: ✅ 可直接计算
- **说明**: 综合考虑了近期价格水平、价格加速度和相对成交量。
- **使用建议**: 多维量价共振识别。

### Alpha025
- **分类**: 量价关系类
- **原始公式**: `rank(((((-1 * returns) * adv20) * vwap) * (high - close)))`
- **可用性**: ✅ 可直接计算
- **说明**: 收益率、均量、均价和上影线长度的复合排名。
- **使用建议**: 识别带长上影线且缩量下跌的潜在反弹标的。

### Alpha026
- **分类**: 量价关系类
- **原始公式**: `(-1 * ts_max(correlation(ts_rank(volume, 5), ts_rank(high, 5), 5), 3))`
- **可用性**: ✅ 可直接计算
- **说明**: 衡量量价时序相关性在 3 日内的最大波动情况。
- **使用建议**: 识别量价关系不稳定的标的。

### Alpha027
- **分类**: 量价关系类
- **原始公式**: `((0.5 < rank((sum(correlation(rank(volume), rank(vwap), 6), 2) / 2.0))) ? (-1 * 1) : 1)`
- **可用性**: ✅ 可直接计算
- **说明**: 基于成交量与 VWAP 相关性强度的二值化多空信号。
- **使用建议**: 趋势转折点的阈值过滤。

### Alpha028
- **分类**: 量价关系类
- **原始公式**: `scale(((correlation(adv20, low, 5) + ((high + low) / 2)) - close))`
- **可用性**: ✅ 可直接计算
- **说明**: 均量与低价相关性加上价格中位值与收盘价的偏离。
- **使用建议**: 衡量收盘价相对于日内中轴的强弱，结合量能趋势。

### Alpha035
- **分类**: 量价关系类
- **原始公式**: `((Ts_Rank(volume, 32) * (1 - Ts_Rank(((close + high) - low), 16))) * (1 - Ts_Rank(returns, 32)))`
- **可用性**: ✅ 可直接计算
- **说明**: 成交量放大、价格在低位且收益率排名靠后的综合信号。
- **使用建议**: 用于底部放量回升的选股。

### Alpha036
- **分类**: 量价关系类
- **原始公式**: `加权：corr(close-open, delay(vol)), rank(open-close), ts_rank(delay(-returns)), corr(vwap,adv20), rank(MA偏离)`
- **可用性**: ✅ 可直接计算
- **说明**: 包含多个子项的超大规模加权复合量价信号。
- **使用建议**: 试图捕捉多种价量统计特征的均值。

### Alpha043
- **分类**: 量价关系类
- **原始公式**: `(ts_rank((volume / adv20), 20) * ts_rank((-1 * delta(close, 7)), 8))`
- **可用性**: ✅ 可直接计算
- **说明**: 近期相对成交量排名与近期价格下跌幅度的排名。
- **使用建议**: 捕捉近期缩量阴跌后的反转机会。

### Alpha044
- **分类**: 量价关系类
- **原始公式**: `(-1 * correlation(high, rank(volume), 5))`
- **可用性**: ✅ 可直接计算
- **说明**: 最高价与成交量排名在 5 日内的负相关性。
- **使用建议**: 观察价格高位时的量能衰竭。

### Alpha045
- **分类**: 量价关系类
- **原始公式**: `(-1 * ((rank((sum(delay(close, 5), 20) / 20)) * correlation(close, volume, 2)) * rank(correlation(sum(close, 5), sum(close, 20), 2))))`
- **可用性**: ✅ 可直接计算
- **说明**: 延迟价格均值、极短期量价相关和不同期限价格相关性的复合。
- **使用建议**: 极复杂的趋势一致性与量能匹配度因子。

### Alpha050
- **分类**: 量价关系类
- **原始公式**: `(-1 * ts_max(rank(correlation(rank(volume), rank(vwap), 5)), 5))`
- **可用性**: ✅ 可直接计算
- **说明**: 成交量排名与 VWAP 排名相关性在 5 日内的最大值取负。
- **使用建议**: 寻找价量关系极度趋同后的背离。

### Alpha055
- **分类**: 量价关系类
- **原始公式**: `(-1 * correlation(rank(((close - ts_min(low, 12)) / (ts_max(high, 12) - ts_min(low, 12)))), rank(volume), 6))`
- **可用性**: ✅ 可直接计算
- **说明**: Williams %R（12日）排名与成交量排名的负相关。
- **使用建议**: 超买超卖指标与成交量的配合程度。

### Alpha057
- **分类**: 量价关系类
- **原始公式**: `(0 - (1 * ((close - vwap) / decay_linear(rank(ts_argmax(close, 30)), 2))))`
- **可用性**: ✅ 可直接计算
- **说明**: 收盘价偏离均价的程度，通过最高价位置进行加权。
- **使用建议**: 捕捉处于历史价格高位但由于均价偏离过大产生的反转。

### Alpha060
- **分类**: 量价关系类
- **原始公式**: `(0 - (1 * ((2 * scale(rank(((((close - low) - (high - close)) / (high - low)) * volume)))) - scale(rank(ts_argmax(close, 10))))))`
- **可用性**: ✅ 可直接计算
- **说明**: 结合了类似 CMF（蔡金资金流向）的逻辑与价格最高点时序位置。
- **使用建议**: 多重资金流向与动量位置复合。

### Alpha061
- **分类**: 量价关系类
- **原始公式**: `(rank((vwap - ts_min(vwap, 16))) < rank(correlation(vwap, adv180, 18)))`
- **可用性**: ✅ 可直接计算
- **说明**: VWAP 相对 16 日低点的位置，与 VWAP 和长期均量相关性的对比。
- **使用建议**: 衡量价格上涨动力与长期成交量的一致性。

### Alpha062
- **分类**: 量价关系类
- **原始公式**: `((rank(correlation(vwap, sum(adv20, 22.4098), 9.29875)) < rank((-1 * (1 * (rank(open) < rank(((open + close) / 2))))))) * -1)`
- **可用性**: ✅ 可直接计算
- **说明**: VWAP 与均量相关性与开盘价相对于日内中点排名的博弈。
- **使用建议**: 日内力量对比与量能趋势的结合。

### Alpha064
- **分类**: 量价关系类
- **原始公式**: `((rank(correlation(sum(((open * 0.178404) + (low * 0.821596)), 12.7449), sum(adv120, 12.7449), 17.0313)) < rank(delta(((((high + low) / 2) * 0.178404) + (vwap * 0.821596)), 3.62325))) * -1)`
- **可用性**: ✅ 可直接计算
- **说明**: 加权混合价与长期均量的相关性对比。
- **使用建议**: 对加权价格趋势的确认。

### Alpha065
- **分类**: 量价关系类
- **原始公式**: `((rank(correlation(((open * 0.00817205) + (vwap * (1 - 0.00817205))), sum(adv60, 8.6911), 6.121)) < rank((open - ts_min(open, 13.6282)))) * -1)`
- **可用性**: ✅ 可直接计算
- **说明**: 开盘价/均价混合值与 60 日均量的相关性，与开盘价相对位置对比。
- **使用建议**: 衡量开盘强度的可持续性。

### Alpha066
- **分类**: 量价关系类
- **原始公式**: `((rank(decay_linear(delta(vwap, 3.51013), 7.23052)) + Ts_Rank(decay_linear(((((low * 0.96633) + (low * (1 - 0.96633))) - vwap) / (open - ((high + low) / 2))), 11.4157), 6.72611)) * -1)`
- **可用性**: ✅ 可直接计算
- **说明**: 衰减加权的均价变化率与相对低位程度之和。
- **使用建议**: 典型的均值回归逻辑。

### Alpha068
- **分类**: 量价关系类
- **原始公式**: `((Ts_Rank(correlation(rank(high), rank(adv15), 8.91646), 13.9333) < rank(delta(((close * 0.518371) + (low * (1 - 0.518371))), 1.06157))) * -1)`
- **可用性**: ✅ 可直接计算
- **说明**: 捕捉高价与短均量相关性的突变。
- **使用建议**: 寻找高位放量的异常标的。

### Alpha071
- **分类**: 量价关系类
- **原始公式**: `max(Ts_Rank(decay_linear(correlation(Ts_Rank(close, 3.43976), Ts_Rank(adv180, 12.0647), 18.0175), 4.20501), 15.6948), Ts_Rank(decay_linear((rank(((low + open) - (vwap + vwap)))^2), 16.4462), 4.43034))`
- **可用性**: ✅ 可直接计算
- **说明**: 多层衰减时序排名与 VWAP 偏离平方的比较。
- **使用建议**: 寻找极端偏离后的相关性修复。

### Alpha072
- **分类**: 量价关系类
- **原始公式**: `(rank(decay_linear(correlation(((high + low) / 2), adv40, 8.93345), 10.1519)) / rank(decay_linear(correlation(Ts_Rank(vwap, 3.72469), Ts_Rank(volume, 18.5188), 6.86671), 2.95011)))`
- **可用性**: ✅ 可直接计算
- **说明**: 两种衰减相关性排名的比值。
- **使用建议**: 比较中价量趋势与均价量趋势的相对强弱。

### Alpha073
- **分类**: 量价关系类
- **原始公式**: `(max(rank(decay_linear(delta(vwap, 4.72775), 2.91864)), Ts_Rank(decay_linear(((delta(((open * 0.147155) + (low * (1 - 0.147155))), 2.03608) / ((open * 0.147155) + (low * (1 - 0.147155)))) * -1), 3.33829), 16.7411)) * -1)`
- **可用性**: ✅ 可直接计算
- **说明**: 均价变化率与加权低价变动率的衰减排名最大值的负值。
- **使用建议**: 寻找由于价格异常变动导致的短期超跌机会。

### Alpha074
- **分类**: 量价关系类
- **原始公式**: `((rank(correlation(close, sum(adv30, 37.4843), 15.1365)) < rank(correlation(rank(((high * 0.0261661) + (vwap * (1 - 0.0261661)))), rank(volume), 11.4761))) * -1)`
- **可用性**: ✅ 可直接计算
- **说明**: 长期均量相关性与价格-成交量排名相关性的对比。
- **使用建议**: 寻找长短期价量逻辑冲突的标的。

### Alpha075
- **分类**: 量价关系类
- **原始公式**: `(rank(correlation(vwap, volume, 4.24304)) < rank(correlation(rank(low), rank(adv50), 12.4269)))`
- **可用性**: ✅ 可直接计算
- **说明**: 短期价量相关性 vs 长期均量低价相关性。
- **使用建议**: 极短期与中长期的共振点识别。

### Alpha077
- **分类**: 量价关系类
- **原始公式**: `min(rank(decay_linear(((((high + low) / 2) + high) - (vwap + high)), 20.0451)), rank(decay_linear(correlation(((high + low) / 2), adv40, 3.1614), 5.64495)))`
- **可用性**: ✅ 可直接计算
- **说明**: 衰减的价格偏离与衰减的价量相关性的最小值。
- **使用建议**: 只有在两个逻辑同时走弱时发出买入信号。

### Alpha078
- **分类**: 量价关系类
- **原始公式**: `(rank(correlation(sum(((low * 0.352233) + (vwap * (1 - 0.352233))), 19.7428), sum(adv40, 19.7428), 6.83313))^rank(correlation(rank(vwap), rank(volume), 6.09617)))`
- **可用性**: ✅ 可直接计算
- **说明**: 复杂的幂次复合量价指标。
- **使用建议**: 非线性捕捉多重价量信号。

### Alpha081
- **分类**: 量价关系类
- **原始公式**: `((rank(log(product(rank(rank(correlation(vwap, sum(adv10, 49.6054), 8.47743))^4), 14.9655))) < rank(correlation(rank(vwap), rank(volume), 5.07914))) * -1)`
- **可用性**: ✅ 可直接计算
- **说明**: 嵌套排名的对数连乘与截面排名的对比。
- **使用建议**: 极强力度的异常值过滤因子。

### Alpha083
- **分类**: 量价关系类
- **原始公式**: `((rank(delay(((high - low) / (sum(close, 5) / 5)), 2)) * rank(rank(volume))) / (((high - low) / (sum(close, 5) / 5)) / (vwap - close)))`
- **可用性**: ✅ 可直接计算
- **说明**: 价格振幅相对于均价的延迟排名乘以成交量排名，除以当前振幅相对于均价偏离的比值。
- **使用建议**: 捕捉振幅突变伴随量能异常。

### Alpha085
- **分类**: 量价关系类
- **原始公式**: `(rank(correlation(((high * 0.876703) + (close * (1 - 0.876703))), adv30, 9.61331))^rank(correlation(Ts_Rank(((high + low) / 2), 3.70564), Ts_Rank(volume, 10.1595), 7.11408)))`
- **可用性**: ✅ 可直接计算
- **说明**: 价格-均量相关性的幂次复合。
- **使用建议**: 捕捉价量时序一致性的突变。

### Alpha086
- **分类**: 量价关系类
- **原始公式**: `((Ts_Rank(correlation(close, sum(adv20, 14.7444), 6.00049), 20.4195) < rank(((open + close) - (vwap + open)))) * -1)`
- **可用性**: ✅ 可直接计算
- **说明**: 收盘价与均量的相关性时序排名 vs 价格偏离排名。
- **使用建议**: 观察价格是否能得到量能支撑。

### Alpha088
- **分类**: 量价关系类
- **原始公式**: `min(rank(decay_linear(((rank(open) + rank(low)) - (rank(high) + rank(close))), 8.06882)), Ts_Rank(decay_linear(correlation(Ts_Rank(close, 8.44728), Ts_Rank(adv60, 20.6966), 8.01266), 6.65053), 2.61957))`
- **可用性**: ✅ 可直接计算
- **说明**: OHLC 排名的内部偏差对比 vs 均量相关性。
- **使用建议**: 寻找 K 线结构失衡的标的。

### Alpha094
- **分类**: 量价关系类
- **原始公式**: `((rank((vwap - ts_min(vwap, 11.5783)))^Ts_Rank(correlation(Ts_Rank(vwap, 19.6462), Ts_Rank(adv60, 4.02992), 18.0926), 2.70756)) * -1)`
- **可用性**: ✅ 可直接计算
- **说明**: VWAP 位置排名的幂次复合。
- **使用建议**: 增强极值点的信号强度。

### Alpha095
- **分类**: 量价关系类
- **原始公式**: `(rank((open - ts_min(open, 12.4354))) < Ts_Rank((rank(correlation(sum(((high + low) / 2), 19.1351), sum(adv40, 19.1351), 12.656))^5), 11.7586))`
- **可用性**: ✅ 可直接计算
- **说明**: 开盘价相对位置与中位价均量相关排名的 5 次幂对比。
- **使用建议**: 寻找极端价量不匹配的标的。

### Alpha096
- **分类**: 量价关系类
- **原始公式**: `(max(Ts_Rank(decay_linear(correlation(rank(vwap), rank(volume), 3.83874), 4.16783), 8.38151), Ts_Rank(decay_linear(Ts_ArgMax(correlation(Ts_Rank(close, 7.45404), Ts_Rank(adv60, 4.13247), 3.65459), 12.6556), 14.0365), 13.4143)) * -1)`
- **可用性**: ✅ 可直接计算
- **说明**: 价量相关性的多层时序特征比较。
- **使用建议**: 捕捉多周期相关的波峰。

### Alpha098
- **分类**: 量价关系类
- **原始公式**: `(rank(decay_linear(correlation(vwap, sum(adv5, 26.4719), 4.58418), 7.18088)) - rank(decay_linear(Ts_Rank(Ts_ArgMin(correlation(rank(open), rank(adv15), 20.8187), 8.62571), 6.95668), 8.07206)))`
- **可用性**: ✅ 可直接计算
- **说明**: VWAP 相关性趋势与开盘价相关性低点的差值。
- **使用建议**: 相关性趋势的相对强度选股。

### Alpha099
- **分类**: 量价关系类
- **原始公式**: `((rank(correlation(sum(((high + low) / 2), 19.8975), sum(adv60, 19.8975), 8.8136)) < rank(correlation(Ts_Rank(vwap, 3.72469), Ts_Rank(volume, 18.5188), 6.86671))) * -1)`
- **可用性**: ✅ 可直接计算
- **说明**: 中位价趋势相关性 vs VWAP 时序相关性。
- **使用建议**: 典型的主流趋势与均价趋势的对比。

---

## 四、均值回复类因子 (Mean-Reversion)

### Alpha005
- **分类**: 均值回复类
- **原始公式**: `(rank((open - (sum(vwap, 10) / 10))) * (-1 * abs(rank((close - vwap)))))`
- **可用性**: ✅ 可直接计算
- **说明**: 开盘价相对于 10 日均价的偏离，乘以收盘价相对于均价偏离排名的负绝对值。
- **使用建议**: 典型的均值回归思路：偏离过大必有回撤。

### Alpha020
- **分类**: 均值回复类
- **原始公式**: `(((-1 * rank((open - delay(high, 1)))) * rank((open - delay(close, 1)))) * rank((open - delay(low, 1))))`
- **可用性**: ✅ 可直接计算
- **说明**: 衡量今日开盘价相对于昨日高点、收盘价 and 低点的跳空情况。
- **使用建议**: 用于捕捉大幅跳空后的反向回归机会。

### Alpha021
- **分类**: 均值回复类
- **原始公式**: `((((sum(close, 8) / 8) + stddev(close, 8)) < (sum(close, 2) / 2)) ? (-1 * 1) : (((sum(close, 2) / 2) < ((sum(close, 8) / 8) - stddev(close, 8))) ? 1 : (((1 < (volume / adv20)) || ((volume / adv20) == 1)) ? 1 : (-1 * 1))))`
- **可用性**: ✅ 可直接计算
- **说明**: 结合了布林带突破逻辑和相对成交量。
- **使用建议**: 用于识别超买/超卖区的放量转折点。

### Alpha023
- **分类**: 均值回复类
- **原始公式**: `(((sum(high, 20) / 20) < high) ? (-1 * delta(high, 2)) : 0)`
- **可用性**: ✅ 可直接计算
- **说明**: 如果当前最高价高于 20 日均值，则做空其两日内的价格增量。
- **使用建议**: 寻找由于前期涨幅过大导致的短期回调。

### Alpha032
- **分类**: 均值回复类
- **原始公式**: `(scale(((sum(close, 7) / 7) - close)) + (20 * scale(correlation(vwap, delay(close, 5), 230))))`
- **可用性**: ✅ 可直接计算
- **说明**: 7 日价格偏差加 230 日长期均价相关的缩放值。
- **使用建议**: 结合短期偏离与长期相关性的稳健型均值回归。

### Alpha037
- **分类**: 均值回复类
- **原始公式**: `(rank(correlation(delay((open - close), 1), close, 200)) + rank((open - close)))`
- **可用性**: ✅ 可直接计算
- **说明**: 延迟一日的日内涨跌幅与收盘价的长期相关性。
- **使用建议**: 寻找日内幅度与收盘水平出现背离的回归机会。

---

## 五、微观结构类因子 (Microstructure)

### Alpha004
- **分类**: 微观结构类
- **原始公式**: `(-1 * Ts_Rank(rank(low), 9))`
- **可用性**: ✅ 可直接计算
- **说明**: 过去 9 天最低价截面排名的时序排名。
- **使用建议**: 衡量最低价在近期所处的相对位置强度。

### Alpha033
- **分类**: 微观结构类
- **原始公式**: `rank((-1 * ((1 - (open / close))^1)))`
- **可用性**: ✅ 可直接计算
- **说明**: 衡量日内收益率（收盘相对于开盘）的排名。
- **使用建议**: 识别日内强势上涨或下跌的标的。

### Alpha041
- **分类**: 微观结构类
- **原始公式**: `(((high * low)^0.5) - vwap)`
- **可用性**: ✅ 可直接计算
- **说明**: 几何中位价相对于 VWAP 的距离。
- **使用建议**: 寻找价格中枢与市场成交均价的细微偏差。

### Alpha042
- **分类**: 微观结构类
- **原始公式**: `(rank((vwap - close)) / rank((vwap + close)))`
- **可用性**: ✅ 可直接计算
- **说明**: VWAP 与收盘价的差值相对于其和的比值排名。
- **使用建议**: 捕捉均价与收盘价的不对称性信号。

### Alpha053
- **分类**: 微观结构类
- **原始公式**: `(-1 * delta((((close - low) - (high - close)) / (close - low)), 9))`
- **可用性**: ✅ 可直接计算
- **说明**: 基于收盘价在 K 线中位置的 9 日变化率。
- **使用建议**: 识别 K 线实体重心移动的节奏变化。

### Alpha054
- **分类**: 微观结构类
- **原始公式**: `((-1 * ((low - close) * (open^5))) / ((low - high) * (close^5)))`
- **可用性**: ✅ 可直接计算
- **说明**: 使用 5 次方进行极度非线性的 K 线结构变换。
- **使用建议**: 挖掘 K 线极值与开收盘价的微妙规律。

### Alpha092
- **分类**: 微观结构类
- **原始公式**: `min(Ts_Rank(decay_linear(((high + low) / 2 + close) < (low + open), 14.7221), 18.8683), Ts_Rank(decay_linear(correlation(rank(low), rank(adv30), 7.58555), 6.94024), 6.80586))`
- **可用性**: ✅ 可直接计算
- **说明**: 内部价格结构不等式的时序排名比较。
- **使用建议**: 寻找 K 线微观结构与量能趋势的共振点。

### Alpha101
- **分类**: 微观结构类
- **原始公式**: `((close - open) / ((high - low) + 0.001))`
- **可用性**: ✅ 可直接计算
- **说明**: 标准化的 K 线实体占比：日内收益除以日内振幅。
- **使用建议**: 衡量日内多空对决的净胜出比例。

---

## 六、不可直接实现的因子

### Alpha048
- **分类**: 需中性化
- **原始公式**: `indneutralize(((correlation(delta(close, 1), delta(delay(close, 1), 1), 250) * delta(close, 1)) / close), subindustry)`
- **可用性**: ⚠️ 需 IndNeutralize
- **原因**: 需要细分行业（SubIndustry）分类数据进行截面中性化。

### Alpha056
- **分类**: 需市值
- **原始公式**: `(0 - (1 * (rank((sum(returns, 10) / sum(sum(returns, 2), 3))) * rank((returns * cap)))))`
- **可用性**: ⚠️ 需 cap 数据
- **原因**: `cap` 代表总市值（Market Capitalization），通常不属于基础量价 OHLCV 数据集。

### Alpha058
- **分类**: 需中性化
- **原始公式**: `(-1 * Ts_Rank(decay_linear(correlation(indneutralize(vwap, sector), volume, 3.92795), 7.89291), 19.9905))`
- **可用性**: ⚠️ 需 IndNeutralize
- **原因**: 需板块（Sector）信息进行 VWAP 中性化。

### Alpha059
- **分类**: 需中性化
- **原始公式**: `(-1 * Ts_Rank(decay_linear(correlation(indneutralize(vwap, industry), volume, 4.22304), 2.87474), 6.27878))`
- **可用性**: ⚠️ 需 IndNeutralize
- **原因**: 需行业（Industry）信息进行中性化。

### Alpha063
- **分类**: 需中性化
- **原始公式**: `((rank(decay_linear(delta(indneutralize(close, industry), 2.25164), 8.66371)) - rank(decay_linear(correlation(((close * 0.318108) + (vwap * (1 - 0.318108))), adv180, 3.72424), 13.5157))) * -1)`
- **可用性**: ⚠️ 需 IndNeutralize

### Alpha067
- **分类**: 需中性化
- **原始公式**: `((rank(high - ts_min(high, 2.14591)) < rank(indneutralize(vwap, sector))) * -1)`
- **可用性**: ⚠️ 需 IndNeutralize

### Alpha069
- **分类**: 需中性化
- **原始公式**: `((rank(ts_max(delta(indneutralize(vwap, industry), 2.72659), 4.79344))^Ts_Rank(correlation(((close * 0.490655) + (vwap * (1 - 0.490655))), adv20, 4.92416), 9.0615)) * -1)`
- **可用性**: ⚠️ 需 IndNeutralize

### Alpha070
- **分类**: 需中性化
- **原始公式**: `((rank(delta(indneutralize(close, sector), 1.28435))^Ts_Rank(correlation(vwap, adv40, 11.4661), 7.02292)) * -1)`
- **可用性**: ⚠️ 需 IndNeutralize

### Alpha076
- **分类**: 需中性化
- **原始公式**: `(max(rank(decay_linear(delta(indneutralize(vwap, sector), 1.24383), 11.8383)), Ts_Rank(decay_linear(Ts_Rank(correlation(indneutralize(low, sector), adv81, 8.14941), 14.9082), 6.876), 3.06525)) * -1)`
- **可用性**: ⚠️ 需 IndNeutralize

### Alpha079
- **分类**: 需中性化
- **原始公式**: `(rank(delta(indneutralize(((close * 0.60733) + (open * (1 - 0.60733))), sector), 1.23438)) < rank(correlation(Ts_Rank(vwap, 3.60973), Ts_Rank(volume, 12.6083), 3.79829)))`
- **可用性**: ⚠️ 需 IndNeutralize

### Alpha080
- **分类**: 需中性化
- **原始公式**: `((rank(sign(delta(indneutralize(((open * 0.868128) + (high * (1 - 0.868128))), industry), 4.04545)))^Ts_Rank(correlation(high, adv10, 5.11456), 5.53756)) * -1)`
- **可用性**: ⚠️ 需 IndNeutralize

### Alpha082
- **分类**: 需中性化
- **原始公式**: `(min(rank(decay_linear(delta(open, 1.46063), 14.8717)), Ts_Rank(decay_linear(correlation(indneutralize(volume, sector), vwap, 7.2439), 6.2096), 9.74204)) * -1)`
- **可用性**: ⚠️ 需 IndNeutralize

### Alpha087
- **分类**: 需中性化
- **原始公式**: `(max(rank(decay_linear(delta(indneutralize(((close * 0.369701) + (vwap * (1 - 0.369701))), industry), 1.91233), 4.79377)), Ts_Rank(decay_linear(correlation(Ts_Rank(adv81, 5.8995), Ts_Rank(low, 8.68361), 6.20871), 13.4124), 4.98304)) * -1)`
- **可用性**: ⚠️ 需 IndNeutralize

### Alpha089
- **分类**: 需中性化
- **原始公式**: `(Ts_Rank(decay_linear(correlation(((low * 0.967285) + (low * (1 - 0.967285))), adv10, 6.94279), 5.51607), 3.799) - rank(decay_linear(delta(indneutralize(vwap, industry), 3.48158), 10.1467)))`
- **可用性**: ⚠️ 需 IndNeutralize

### Alpha090
- **分类**: 需中性化
- **原始公式**: `((rank((close - ts_max(close, 4.66719)))^Ts_Rank(correlation(indneutralize(adv40, subindustry), low, 5.38375), 3.21856)) * -1)`
- **可用性**: ⚠️ 需 IndNeutralize

### Alpha091
- **分类**: 需中性化
- **原始公式**: `((rank(decay_linear(decay_linear(correlation(indneutralize(close, industry), volume, 9.74928), 16.398), 3.83219)) - rank(decay_linear(correlation(vwap, adv30, 4.01303), 2.68451))) * -1)`
- **可用性**: ⚠️ 需 IndNeutralize

### Alpha093
- **分类**: 需中性化
- **原始公式**: `(Ts_Rank(decay_linear(correlation(indneutralize(vwap, industry), adv81, 17.4193), 19.848), 7.54455) / rank(decay_linear(delta(((close * 0.52971) + (vwap * (1 - 0.52971))), 3.14126), 7.25204)))`
- **可用性**: ⚠️ 需 IndNeutralize

### Alpha097
- **分类**: 需中性化
- **原始公式**: `((rank(decay_linear(delta(indneutralize(((low * 0.721001) + (vwap * (1 - 0.721001))), industry), 3.3705), 20.4523)) - Ts_Rank(decay_linear(Ts_Rank(correlation(Ts_Rank(low, 7.87871), Ts_Rank(adv60, 17.255), 4.97547), 17.5922), 15.7114), 7.56909)) * -1)`
- **可用性**: ⚠️ 需 IndNeutralize

### Alpha100
- **分类**: 需中性化
- **原始公式**: `(0 - (1 * (((1.5 * scale(indneutralize(rank(((((close - low) - (high - close)) / (high - low)) * volume)), subindustry))) - scale(indneutralize((correlation(close, rank(adv20), 5) - rank(ts_argmin(close, 30))), subindustry))) * (volume / adv20))))`
- **可用性**: ⚠️ 需 IndNeutralize

---

## 汇总统计

| 分类 | 数量 | 占比 |
| :--- | :---: | :---: |
| 动量类 (Momentum) | 17 | 16.8% |
| 波动率类 (Volatility) | 4 | 4.0% |
| 量价关系类 (Volume-Price) | 46 | 45.5% |
| 均值回复类 (Mean-Reversion) | 7 | 6.9% |
| 微观结构类 (Microstructure) | 8 | 7.9% |
| 需外部数据 (Industry/Cap) | 19 | 18.8% |
| **总计** | **101** | **100%** |

---

## Qlib DSL 实现示例

以下是几个典型因子的 Qlib DSL 实现，供研究参考：

### Alpha001 (Qlib 实现)
```yaml
# Qlib DSL 表达
# rank(Ts_ArgMax(SignedPower(((returns < 0) ? stddev(returns, 20) : close), 2.), 5)) - 0.5
"Rank(TArgMax(Power(If($returns < 0, Std($returns, 20), $close), 2), 5)) - 0.5"
```

### Alpha012 (Qlib 实现)
```yaml
# (sign(delta(volume, 1)) * (-1 * delta(close, 1)))
"Sign($volume - Ref($volume, 1)) * (-1 * ($close - Ref($close, 1)))"
```

### Alpha101 (Qlib 实现)
```yaml
# ((close - open) / ((high - low) + 0.001))
"($close - $open) / (($high - $low) + 0.001)"
```

---

---

## 类别使用建议

- **动量类**: 适用于捕捉强趋势个股，特别是在大盘环境良好时。建议结合市场情绪指标进行过滤。
- **波动率类**: 适合在震荡市或趋势转折点使用，高波动通常意味着更大的风险，但也蕴含潜在的剧烈波动收益。
- **量价关系类**: Alpha101 的核心组成部分，最能体现市场微观博弈。建议多因子加权使用，寻找量价共振的机会。
- **均值回复类**: 适用于宽幅震荡市场或遭遇黑天鹅事件后的超跌反弹。注意需设置严格的止损逻辑。
- **微观结构类**: 捕捉 K 线形态中的细微特征，通常具有较高的信噪比，适合与其他趋势类因子复合。
- **行业中性化因子**: 在实盘中非常重要，因为行业 Beta 往往会掩盖个股 Alpha。如果没有行业数据，可以通过截面排名（Rank）在全市场层面降低 Beta。
