# 网络代理双通道模式

本服务器通过 SOCKS5 代理 (`127.0.0.1:1080`) 访问外部网络。但 Python urllib 不原生支持 SOCKS5。

## 规则

| 目标 | 代理 | 方式 |
|------|------|------|
| **外部 API** (X/Binance/Antpool API) | ✅ SOCKS5 | `curl -x socks5h://` 或 requests+socks |
| **国内 API** (东财push2/腾讯qt.gtimg.cn/baostock) | ❌ 不走代理 | `env -u http_proxy -u https_proxy` |
| **矿机内网** (172.16.x.x via 10.0.255.188:8899) | ❌ 不走外网代理 | HTTP代理到内网 |

## Python 中正确处理

```python
import os

# 清除全局 socks5 代理（避免 urllib 报错 "unknown url type: socks5h"）
for k in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
    os.environ.pop(k, None)

# 需要外网访问时用 curl subprocess
import subprocess as sp
r = sp.run(['curl', '-x', 'socks5h://127.0.0.1:1080', '-sL', '--max-time', '10', url],
           stdout=sp.PIPE)

# 需要 Python SOCKS5 时（requests 库可用）
import requests
proxies = {'http': 'socks5h://127.0.0.1:1080', 'https': 'socks5h://127.0.0.1:1080'}
r = requests.get(url, proxies=proxies, timeout=10)
```

## Pitfalls

- **Python socks 库** (`import socks; socks.set_default_proxy()`) 与本代理服务器协议不兼容，会报 "Connection closed unexpectedly"
- **Pip 安装 `PySocks` 可能被安全系统拦截** — 改用系统 `apt install python3-socks` 或直接用 curl subprocess
- **环境变量 `/etc/profile` 中的代理设置** 会全局生效，影响所有 urllib 请求
- **`env -u http_proxy -u https_proxy`** 前缀只对当前命令生效，Python 内部 os.environ 修改也只对当前进程生效
