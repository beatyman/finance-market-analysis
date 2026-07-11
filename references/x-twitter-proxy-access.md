# X/Twitter 推文获取 — SOCKS5代理模式 (2026-07-10更新)

本机无法直连X.com，通过socks5代理(127.0.0.1:1080)访问。

## 标准单条命令

```bash
curl -x socks5h://127.0.0.1:1080 -sL --max-time 10 \
  -H 'User-Agent: Mozilla/5.0' \
  'https://x.com/{USERNAME}/status/{TWEET_ID}' 2>/dev/null \
  | grep -oP 'property="og:description"\s+content="\K[^"]+'
```

## 备选（og:description为空时提取title）
```bash
curl -x socks5h://127.0.0.1:1080 ... \
  | grep -oP '<title>\K[^<]+'
```

## 2026-07-10 批量验证

单次会话50+条推文均用此模式提取，成功率>95%。湖若深/Mistery/华尔街观察/Phyrex等所有源均可用。

## 注意
- `socks5h://` (非 `socks5://`) — h表示由curl解析主机名
- 账号锁/私密时og:description为空（如WuChuanIJ） — 无需重试
- 浏览器工具在socks5代理下报`ERR_NO_SUPPORTED_PROXIES` → 始终用curl
- 不需要proxychains — X检测并返回空

## Python urllib与代理冲突

```python
# 代理env vars在/etc/profile中
export http_proxy="socks5h://127.0.0.1:1080"
export https_proxy="socks5h://127.0.0.1:1080"

# Python urllib不原生支持socks5 → 代理env vars会导致HTTP请求失败
# 国内API（东财push2/腾讯qt.gtimg.cn/baostock）需先清理代理:
import os
for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
    os.environ.pop(k, None)
```
