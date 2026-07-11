# X/Twitter 内容拉取 — curl+socks5代理方案

## 背景

内置浏览器工具(`browser_navigate`)在非标准代理环境下（如本地1080端口socks5代理）会出现 `ERR_NO_SUPPORTED_PROXIES` 错误，导致无法访问X内容。此时需要回退到curl+socks5方案。

## 验证代理可用性

```bash
# 先验证代理是否连通
curl -x socks5h://127.0.0.1:1080 -sL --max-time 8 'https://www.google.com' | head -c 100
```

## 拉取X推文内容

```bash
# 1. 获取完整HTML（~50KB）
curl -x socks5h://127.0.0.1:1080 -sL --max-time 12 \
  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' \
  'https://x.com/USERNAME/status/TWEET_ID' \
  -o /tmp/tweet.html

# 2. 提取og:description（<title>标签在部分页面不可用）
grep -oP 'property="og:description"\s+content="\K[^"]+' /tmp/tweet.html

# 3. 提取title作为备选
grep -oP '<title>\K[^<]+' /tmp/tweet.html
```

## 关键陷阱

- **proxychains不可用**: X检测proxychains模式返回空响应
- **`<title>`标签不稳定**: 部分X页面title为空或用`&quot;`实体编码
- **必须要User-Agent头**: 不带UA的请求会被X拒绝
- **`socks5h` vs `socks5`**: 用`socks5h`让curl通过代理做DNS解析，避免DNS泄漏
- **grep正则**: `og:description`的meta标签格式为 `property="og:description" content="..."`，用`\K`丢弃前面的匹配

## 工作流优先级

```
1. browser_navigate → 最快但有代理限制
2. curl+socks5h:1080 → 可靠但需手动解析HTML
3. 用户直接粘贴内容 → 最可靠
```

## 2026-07-08验证

已验证成功拉取Rookiex9o/iiiinvest等4条推文，单条耗时~3秒。
