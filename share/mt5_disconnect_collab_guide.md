# MT5 间歇性断连联合排查指南

适用场景：

- 现象不是稳定复现，而是“能连上，过一会突然连不上，随后又恢复”
- 你这边的后端日志常见表现为：
  - `start_tls.failed`
  - `ConnectError(EndOfStream())`
  - MT5 相关接口返回 `503`
- 当前已知：
  - `TLS 1.2` 与 `TLS 1.3` 都能成功握手
  - 因此“单纯 TLS 版本过高”不是当前主嫌疑

---

## 1. 当前判断

目前更像 MT5 服务器侧运行环境波动，而不是后端业务代码固定写错。

已有证据：

- 从应用外直接请求 `https://uat.ailhw.com:2000/api/auth/start`，也曾出现 TLS 握手失败
- MT5 内部日志接口可正常调用
- 当前没有查到明确的：
  - `WebAPI session timed out`
  - `connection limit exceeded`
  - `anti-flood`
  - `IP banned`
- 但查到了持续出现的服务器侧信号：
  - 时间同步失败
  - 连接到 `Local Main Backup Server`

因此，这次联合排查的目标不是“证明后端没问题”，而是：

- 判断故障发生时，问题落在：
  - MT5 Web API 本体
  - MT5 主备/内部网络
  - 服务器系统环境
  - 代理/TLS 终止层
  - 还是后端连接方式

---

## 2. 协作分工

### 你这边：应用侧

负责：

- 保持后端运行
- 在故障发生时第一时间记录应用报错时间
- 执行外部探活
- 提供本地请求失败的精确时间点

重点记录：

- 故障发生时间，精确到秒
- 报错接口
- 报错类型
- 是否所有 MT5 接口同时失败
- 当时本地是否能访问 `8000`

### MT5 同事：服务器侧

负责：

- 在 MT5 服务器本机同步执行探活
- 查看 MT5 服务器内部日志
- 查看 Windows 系统日志 / 服务状态
- 确认 `2000` 端口监听进程和前置代理情况

重点记录：

- 故障发生时本机请求 `127.0.0.1:2000` 是否成功
- MT5 服务端日志是否出现异常
- 主备服务器是否有切换/重连
- 时间同步是否失败
- 2000 端口对应的实际进程

---

## 3. 联合排查核心原则

一定要在“故障发生那一分钟”同步取证。

不要只做事后猜测，也不要只看一边日志。

最关键的是同时回答这三个问题：

1. 故障发生时，应用侧外部访问是不是失败？
2. 故障发生时，MT5 服务器本机访问是不是也失败？
3. 故障发生时，MT5 服务器日志里有没有主备、时间、服务、监听异常？

---

## 4. 标准联动流程

### 第一步：双方各自持续探活

#### 你这边执行

在项目目录执行：

```powershell
cd E:\ai-coding-study\astralw_back
python scripts\mt5_tls_probe.py --interval 5 --rounds 720
```

说明：

- 每 5 秒探测一次
- 连续跑约 1 小时
- 当前主要用于记录外部连通性
- 如果只需要普通探活，不关心 TLS 对比，也可以继续用它，因为两种 TLS 都已证明不是主因

#### MT5 同事在服务器本机执行

建议在 MT5 服务器本机开一个 PowerShell：

```powershell
while ($true) {
  $t = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  try {
    $r = Invoke-WebRequest -Uri "https://127.0.0.1:2000/api/auth/start?version=3470&agent=AstralWGateway&login=1015&type=manager" -UseBasicParsing -TimeoutSec 8
    "$t OK $($r.StatusCode)" | Out-File -FilePath C:\temp\mt5_probe_server.log -Append -Encoding utf8
  } catch {
    "$t FAIL $($_.Exception.Message)" | Out-File -FilePath C:\temp\mt5_probe_server.log -Append -Encoding utf8
  }
  Start-Sleep -Seconds 5
}
```

如果服务器本机没有证书信任问题，这个探测最有价值。

---

### 第二步：故障发生时立即同步记录

#### 你这边立刻记录

- 当前时间
- 前端/后端哪个接口失败
- 失败响应
- 终端或日志里的报错原文

建议直接记成这样：

```text
2026-03-24 10:33:22
GET /api/v1/market/tick_stat -> 503
GET /api/v1/market/quotes -> 503
connector start_tls.failed ConnectError(EndOfStream())
```

#### MT5 同事立刻执行

```powershell
netstat -ano | findstr :2000
tasklist | findstr <PID>
```

以及：

```powershell
curl.exe -vk "https://127.0.0.1:2000/api/auth/start?version=3470&agent=AstralWGateway&login=1015&type=manager"
```

如果有前置代理，还要查代理状态。

---

### 第三步：故障恢复后立刻回捞 MT5 内部日志

当前可用的日志接口：

- `GET /api/logger/server_request`

建议查询窗口：

- 故障时间前后各 5 分钟

例如故障发生在 `10:33:22`，则查询：

- `10:28:00 - 10:38:59`

重点筛这些关键词：

- `WebAPI`
- `disconnect`
- `timeout`
- `limit`
- `flood`
- `session`
- `Network`
- `Time`
- `Backup`

---

## 5. 结果判读矩阵

### 情况 A

- 外部探活失败
- 服务器本机探活也失败

说明：

- 问题在 MT5 服务器本体、MT5 Web API 服务、前置代理，或本机系统环境

优先排查：

- Web API 服务状态
- 2000 端口监听进程
- Windows 系统日志
- 时间同步
- 主备切换

### 情况 B

- 外部探活失败
- 服务器本机探活成功

说明：

- 问题更像外部链路、防火墙、安全组、代理、域名、SNI 或公网入口层

优先排查：

- 公网访问入口
- 反向代理
- 防火墙
- 是否存在负载均衡/多节点

### 情况 C

- 外部探活成功
- 服务器本机探活成功
- 但应用仍偶发失败

说明：

- 问题更像应用自身连接复用、重连策略或请求并发模型

优先排查：

- 连接器日志
- 心跳与普通请求是否冲突
- 是否存在会话复用异常

---

## 6. MT5 同事重点检查项

### 6.1 时间同步

目前已查到服务端重复出现：

```text
system time synchronization via 100.100.5.1(6000.00 ms ping) failed
```

需要确认：

- 这是不是 MT5 机器当前时间源
- 为什么持续失败
- 是否会影响证书校验、主备同步、会话稳定性

### 6.2 主备连接

目前已查到服务端重复出现：

```text
connecting to '$1 - Local Main Backup Server' at 172.31.249.113:2003
```

需要确认：

- 这是正常周期性心跳，还是异常重连
- 172.31.249.113 是主机、备机、还是内部控制节点
- 在客户端断连时间点附近，这条记录是否明显更频繁

### 6.3 监听与代理

确认：

- `2000` 端口到底是谁在监听
- 是 MT5 Web API 直接监听，还是前面有 Nginx / IIS / 其他代理

### 6.4 系统环境

查看：

- Windows 事件查看器
- 服务是否重启
- 网卡是否抖动
- 设备/驱动错误
- 资源占用异常

---

## 7. 你这边重点检查项

### 7.1 应用日志

重点保留以下报错原文：

- `start_tls.failed`
- `ConnectError(EndOfStream())`
- 哪个接口 first failure
- 失败前最后一次成功请求时间

### 7.2 接口级别现象

记录：

- 是只有行情接口失败，还是所有 MT5 接口都失败
- `/api/v1/health` 的 `mt5_connected` 是否立即变成 `false`

### 7.3 不要在排查期间频繁改代码

排查窗口内尽量保持：

- 同一套后端版本
- 同一套 MT5 配置
- 不额外引入新的重试/降级逻辑

否则会污染判断。

---

## 8. 本轮联合排查要回答的最终问题

这轮排查结束后，至少要能回答下面四个问题中的三个：

1. 故障发生时，服务器本机访问 `127.0.0.1:2000` 到底成不成功？
2. 故障发生时，`2000` 端口后面是谁在处理 TLS？
3. 故障发生时，主备连接是否在异常重连？
4. 故障发生时，时间同步失败是否仍在持续发生？

只要这几个问题答出来，问题范围就会明显缩小。

---

## 9. 当前不建议优先做的事

- 不建议先大改后端连接器
- 不建议先把心跳改得更激进
- 不建议先把 TLS 固定到旧版本
- 不建议在没有证据前把问题归结为“REST 用法不对”

因为目前已知证据更偏向服务器侧波动。

---

## 10. 协作产出格式

建议双方每次故障按下面格式各记一条：

### 应用侧记录

```text
时间：
失败接口：
报错原文：
health 状态：
是否恢复：
```

### MT5 侧记录

```text
时间：
127.0.0.1:2000 是否可用：
2000 端口监听进程：
MT5 日志关键行：
是否有主备连接动作：
是否有时间同步失败：
```

把这两份按同一时间点对齐，基本就能定位方向。
