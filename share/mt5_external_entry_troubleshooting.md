# MT5 外部入口层排查指南

适用结论：

- 当前证据优先指向“服务器对外入口层”
- 当前不优先怀疑：
  - 后端业务代码
  - TLS 版本
  - MT5 Web API 本机服务整体宕机

当前证据基础：

- 外部探针会连续 `ConnectError`
- 服务器本机探针同时仍可 `OK 200`
- MT5 内部日志没有看到明确的 `WebAPI timeout / limit / flood` 证据

---

## 1. 当前目标

不要再花时间证明“是不是后端代码问题”。

下一步只做一件事：

- 查清楚 `uat.ailhw.com:2000` 这一层公网入口到底哪里不稳定

---

## 2. 你这边要做什么

### 动作 1：继续跑外部探针

如果探针停了，重新执行一次就行：

```powershell
cd E:\ai-coding-study\astralw_back
powershell -ExecutionPolicy Bypass -File .\scripts\probe_mt5_local.ps1
```

说明：

- 重新运行就可以
- 会继续往 [mt5_tls_probe_results.jsonl](/E:/ai-coding-study/astralw_back/share/mt5_tls_probe_results.jsonl) 追加写入
- 不需要复杂恢复

### 动作 2：一旦再次断开，只记录一个时间

你不需要精确到开始断开的第一秒，只需要记：

```text
我大概在 2026-03-24 15:13 左右发现断开
```

然后把这两个东西留给我：

- [mt5_tls_probe_results.jsonl](/E:/ai-coding-study/astralw_back/share/mt5_tls_probe_results.jsonl)
- 你看到的大概故障时间

---

## 3. MT5/运维同事要做什么

### 动作 1：继续跑服务器本机探针

如果停了，就重新执行下面这段：

```powershell
$Output = "C:\temp\mt5_probe_server.log"
$dir = Split-Path -Parent $Output
if (-not (Test-Path $dir)) {
  New-Item -ItemType Directory -Path $dir | Out-Null
}

while ($true) {
  $t = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  $result = curl.exe -k -s -o NUL -w "%{http_code}" "https://127.0.0.1:2000/api/auth/start?version=3470&agent=AstralWGateway&login=1015&type=manager"
  if ($LASTEXITCODE -eq 0) {
    "$t OK $result" | Out-File -FilePath $Output -Append -Encoding utf8
  } else {
    "$t FAIL CURL_EXIT=$LASTEXITCODE" | Out-File -FilePath $Output -Append -Encoding utf8
  }
  Start-Sleep -Seconds 5
}
```

说明：

- 重新运行就可以
- 日志在：
  - `C:\temp\mt5_probe_server.log`

### 动作 2：重点查 `uat.ailhw.com:2000` 前面有没有入口层

必须先确认：

- `uat.ailhw.com:2000` 是不是直接到 MT5 Web API
- 还是前面有：
  - Nginx
  - IIS
  - 负载均衡
  - 端口映射
  - 云防火墙
  - 安全组

如果有这些，就先查这一层，不要先查 MT5 业务逻辑。

### 动作 3：故障时，在服务器上立刻做两次请求

先请求本机：

```powershell
curl.exe -k -v "https://127.0.0.1:2000/api/auth/start?version=3470&agent=AstralWGateway&login=1015&type=manager"
```

再请求公网域名：

```powershell
curl.exe -k -v "https://uat.ailhw.com:2000/api/auth/start?version=3470&agent=AstralWGateway&login=1015&type=manager"
```

只要记录结果，不需要长篇分析。

### 动作 4：查入口层日志

如果 `2000` 前面有代理、转发、负载均衡，就查故障窗口内是否有：

- TLS handshake failed
- connection reset
- upstream unavailable
- backend timeout
- reload / restart
- health check fail

---

## 4. 双方怎么配合

### 你给我什么

你只需要给我：

1. 大概故障时间
2. [mt5_tls_probe_results.jsonl](/E:/ai-coding-study/astralw_back/share/mt5_tls_probe_results.jsonl)
3. 同事发你的 `C:\temp\mt5_probe_server.log`

### 同事给你什么

同事只需要给你：

1. `127.0.0.1:2000` 在故障时是否成功
2. `uat.ailhw.com:2000` 在故障时是否成功
3. `2000` 前面是否有代理/负载均衡/防火墙
4. 如果有，这一层有没有异常日志

---

## 5. 结果怎么判断

### 情况 A

- 本机 `127.0.0.1:2000` 成功
- 公网 `uat.ailhw.com:2000` 失败

结论：

- 问题就在服务器对外入口层

### 情况 B

- 本机也失败
- 公网也失败

结论：

- 再回头查 MT5 Web API 本体或服务器系统环境

### 情况 C

- 两边都成功
- 但你后端请求失败

结论：

- 再回头查应用连接器

---

## 6. 当前最重要的一句话

先查 `uat.ailhw.com:2000` 前面那一层，不要再优先怀疑后端代码和 TLS 版本。
