# XGBoost 双模型对比框架

## 旧模型 (chan_xgb_56d.pkl)

- 训练数据：少量精选样本
- 特征维度：56维（可能和58维有细小差异）
- 评分特征：分数偏高（江铜85、铜陵73），可能过拟合
- 判断阈值：>50 = 优秀

## 新模型 (chan_xgb_300s.pkl) — 2026-07-10训练

- 训练数据：295只 CSI 300 股票 × 1年日线 × ~140天/只 = 41,459样本
- 正向样本：28.8%（forward 5-day return > 2%）
- 模型配置：XGBoost 300棵，max_depth=6，learning_rate=0.05
- 测试表现：准确率 73.4%，AUC 0.717
- 评分特征：分数偏低（江铜31、铜陵27），更保守但统计基础更强
- 判断阈值：>25 ≈ 旧模型 >50

## 训练脚本

```bash
# 全量训练（支持断点续传）
python3 /tmp/train_xgb_batch.py

# Checkpoint: /tmp/xgb_train_samples.json
```

## 扫描中的使用

```python
# 加载两个模型
old_model = pickle.load(open('models/chan_xgb_56d.pkl', 'rb'))
new_model = pickle.load(open('models/chan_xgb_300s.pkl', 'rb'))

# 特征向量化
feats = extract_features(c, h, l, o, v, bsb, bst, cur)
vec = np.array([[feats[k] for k in sorted(feats.keys())]])

# 双模型打分
old_xgb = int(old_model.predict_proba(vec)[0, 1] * 100)
new_xgb = int(new_model.predict_proba(vec)[0, 1] * 100)
```

## 模型存放

- `models/chan_xgb_56d.pkl` — 旧模型
- `models/chan_xgb_300s.pkl` — 新模型（300只训练）
- `models/chan_xgb_latest.pkl` → `chan_xgb_300s.pkl` (symlink)
