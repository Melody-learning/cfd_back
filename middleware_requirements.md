# AstralW 中间件需求文档

> **项目代号**: AstralW Gateway  
> **角色**: Android 客户端与 MT5 交易服务器之间的中间层  
> **状态**: 草案 v2.0  
> **更新日期**: 2026-03-19

---

## 1. 业务背景

AstralW 是一款 CFD 差价合约交易安卓应用，客户端已完成 6 个功能页面（Auth/Market/Chart/Trading/Portfolio/Account），当前全部使用 Mock 数据。

**中间件的职责**：作为 Gateway 层代理 MT5 Web API，向 Android 客户端提供标准化的 REST / WebSocket 接口。

```
┌─────────────┐     REST / WebSocket     ┌──────────────┐     MT5 Web API (HTTPS)     ┌─────────────┐
│  Android 端  │ ◄─────────────────────► │  Gateway 中间件 │ ◄───────────────────────► │  MT5 Server  │
└─────────────┘                          └──────────────┘                              └─────────────┘
```

### 用户管理策略

> [!IMPORTANT]
> 由于 MT5 正式用户名额有限（约 2.5 万个），本项目使用 **MT5 Demo 账户** 容纳所有终端用户。Gateway 通过 MT5 Web API 创建和管理 Demo 账户，同时维护自己的用户数据库存储扩展信息。

### 为什么需要中间件？

1. **MT5 Web API 使用 Manager 账户认证**（MD5 挑战-应答），不能暴露给客户端
2. **MT5 没有标准 JWT 认证**，中间件负责签发/验证 JWT Token
3. **行情推送**需要中间件轮询 MT5 并通过 WebSocket 转发给客户端
4. **接口标准化**：MT5 接口格式非标准 REST，中间件统一转为标准 JSON REST API
5. **用户扩展**：MT5 Demo 账户的 login 是纯数字 ID，中间件提供 email/手机号等友好登录方式

---

## 2. 系统架构

```
                          ┌──────────────────────────────────────────┐
                          │            AstralW Gateway               │
                          │                                          │
  Client ──REST──►        │  ┌──────────┐  ┌──────────────┐          │       MT5 Web API
                          │  │ Auth 模块 │  │ MT5 Connector │─────────┼──► /api/user/add
  Client ──REST──►        │  │ (JWT)    │  │ (Keep-Alive)  │─────────┼──► /api/user/check_password
                          │  ├──────────┤  │               │─────────┼──► /api/tick_last
  Client ◄─WS────        │  │ Quote 推送│  │               │─────────┼──► /api/chart/get
                          │  │(WebSocket)│  │               │─────────┼──► /api/dealer/send_request
                          │  ├──────────┤  └──────────────┘          │
                          │  │ 用户数据库 │ (SQLite / PostgreSQL)      │
                          │  │ email↔login│                          │
                          │  └──────────┘                            │
                          └──────────────────────────────────────────┘
```

### 2.1 Gateway 自建数据库

Gateway 需维护一个本地数据库，存储 MT5 账户无法覆盖的扩展信息：

| 表 | 字段 | 说明 |
|---|---|---|
| `users` | `id`, `email`, `phone`, `mt5_login`, `nickname`, `created_at` | email/手机号 ↔ MT5 login 映射 |
| `refresh_tokens` | `id`, `user_id`, `token_hash`, `expires_at`, `created_at` | JWT refresh token 管理 |
| `user_preferences` | `user_id`, `language`, `theme`, `favorite_symbols` | 用户偏好设置 |

> [!NOTE]
> 初期可使用 SQLite 快速上手，后续根据并发量迁移至 PostgreSQL。

---

## 3. 功能模块与接口定义

### 3.1 注册模块（新增）

| 接口 | 方法 | 说明 | MT5 对应接口 |
|---|---|---|---|
| `/api/v1/auth/register` | POST | 用户注册 | `/api/user/add` + `/api/trade/balance` |

#### 注册流程

```
Client                    Gateway                           MT5
  │ POST /auth/register    │                                 │
  │ {email, password,      │                                 │
  │  nickname}             │                                 │
  │───────────────────────►│                                 │
  │                        │ 1. 验证 email 唯一性（本地DB）     │
  │                        │                                 │
  │                        │ 2. POST /api/user/add            │
  │                        │    ?group=demoforex&leverage=100 │
  │                        │    body: {PassMain, PassInvestor,│
  │                        │           Name}                 │
  │                        │────────────────────────────────►│
  │                        │◄────────────────────────────────│
  │                        │ {login: 954402}                 │
  │                        │                                 │
  │                        │ 3. GET /api/trade/balance        │
  │                        │    ?login=954402&type=2          │
  │                        │    &balance=10000               │
  │                        │────────────────────────────────►│
  │                        │◄────────────────────────────────│
  │                        │                                 │
  │                        │ 4. 本地 DB 保存                   │
  │                        │    email ↔ mt5_login 映射        │
  │                        │                                 │
  │                        │ 5. 签发 JWT                      │
  │ {access_token,          │                                 │
  │  refresh_token,         │                                 │
  │  mt5_login: 954402,     │                                 │
  │  expires_in}            │                                 │
  │◄───────────────────────│                                 │
```

> [!IMPORTANT]
> **MT5 密码要求严格**：至少 8 位，必须包含小写字母、大写字母、数字和特殊字符（如 `#@!`）。例如 `1Ar#pqkj`。最大长度 16 位。客户端注册 UI 需做好规则校验提示。

#### 注册请求

```json
// POST /api/v1/auth/register
{
  "email": "user@example.com",
  "password": "1Ar#pqkj",
  "nickname": "John"
}
```

#### 注册响应

```json
{
  "access_token": "eyJ...",
  "refresh_token": "dGhp...",
  "mt5_login": 954402,
  "expires_in": 900
}
```

---

### 3.2 认证模块

> 中间件管理终端用户（交易者）的认证。Manager 连接在 Gateway 启动时独立完成，与用户登录流程无关。

| 接口 | 方法 | 说明 | MT5 对应接口 |
|---|---|---|---|
| `/api/v1/auth/login` | POST | 用户登录，返回 JWT Token | `/api/user/check_password` |
| `/api/v1/auth/refresh` | POST | 刷新 Token | — (本地 JWT 操作) |
| `/api/v1/auth/logout` | POST | 登出 | — (本地 JWT 操作) |

#### 用户登录流程

```
Client                    Gateway                           MT5
  │ POST /auth/login       │                                 │
  │ {email, password}      │                                 │
  │───────────────────────►│                                 │
  │                        │ 1. 本地 DB 查询 email → mt5_login │
  │                        │                                 │
  │                        │ 2. POST /api/user/check_password │
  │                        │    body: {Login: 954402,        │
  │                        │           Type: "main",         │
  │                        │           Password: "1Ar#pqkj"} │
  │                        │────────────────────────────────►│
  │                        │◄────────────────────────────────│
  │                        │ retcode=0 (密码正确)             │
  │                        │                                 │
  │                        │ 3. 签发 JWT                      │
  │ {access_token,          │                                 │
  │  refresh_token,         │                                 │
  │  mt5_login: 954402,     │                                 │
  │  expires_in}            │                                 │
  │◄───────────────────────│                                 │
```

> [!NOTE]
> **用户登录 ≠ Manager 认证**。用户登录使用 `/api/user/check_password` 校验密码（retcode=0 表示正确，3006 表示错误），完全不涉及 MD5 挑战-应答。Manager 认证流程仅在 Gateway 连接 MT5 服务器时使用。

---

### 3.3 Manager 连接（内部模块）

> **此模块不暴露任何接口给客户端**，仅在 Gateway 内部使用。

Gateway 启动时使用 Manager 账户连接 MT5 服务器，后续所有 MT5 API 调用都通过此连接进行。

#### Manager 认证流程

```
Gateway                                MT5
  │ GET /api/auth/start                  │
  │ ?version=3470&agent=AstralW          │
  │ &login=1000&type=manager             │
  │─────────────────────────────────────►│
  │◄─────────────────────────────────────│
  │ {retcode: "0 Done",                  │
  │  srv_rand: "d4e005...07eb"}          │
  │                                      │
  │ 计算 srv_rand_answer (见下方 MD5 算法)  │
  │ 生成 cli_rand (16字节随机数)            │
  │                                      │
  │ GET /api/auth/answer                  │
  │ ?srv_rand_answer=8b67...df2           │
  │ &cli_rand=34b6...1cc                  │
  │─────────────────────────────────────►│
  │◄─────────────────────────────────────│
  │ {retcode: "0 Done",                  │
  │  cli_rand_answer: "...",             │
  │  version_trade: "1290"}              │
  │                                      │
  │ 验证 cli_rand_answer 确认服务器身份     │
  │ ✅ 连接建立，后续使用此连接发送所有请求   │
```

#### MD5 双向认证算法

```python
import hashlib

def compute_srv_rand_answer(password: str, srv_rand_hex: str) -> str:
    """计算发送给 MT5 的 srv_rand_answer"""
    # 步骤 1: MD5(密码的 UTF-16-LE 编码)
    pass_utf16 = password.encode('utf-16-le')
    pass_md5 = hashlib.md5(pass_utf16).digest()

    # 步骤 2: MD5(步骤1结果 + 'WebAPI' 的 ASCII 编码)
    password_hash = hashlib.md5(pass_md5 + b'WebAPI').digest()

    # 步骤 3: MD5(步骤2结果 + srv_rand 的字节形式)
    srv_rand_bytes = bytes.fromhex(srv_rand_hex)
    answer = hashlib.md5(password_hash + srv_rand_bytes).hexdigest()

    return answer

def verify_cli_rand_answer(password: str, cli_rand_bytes: bytes, cli_rand_answer_hex: str) -> bool:
    """验证 MT5 服务器返回的 cli_rand_answer，确认服务器身份"""
    pass_utf16 = password.encode('utf-16-le')
    pass_md5 = hashlib.md5(pass_utf16).digest()
    password_hash = hashlib.md5(pass_md5 + b'WebAPI').digest()

    expected = hashlib.md5(password_hash + cli_rand_bytes).hexdigest()
    return expected == cli_rand_answer_hex
```

> [!IMPORTANT]
> - auth/start 和 auth/answer 之间的间隔**不能超过 10 秒**，否则认证失败
> - 此逻辑完全在 Gateway 内部完成，客户端无需知晓

---

### 3.4 行情模块

| 接口 | 方法 | 说明 | MT5 对应接口 |
|---|---|---|---|
| `/api/v1/market/symbols` | GET | 获取可用品种列表 | `/api/symbol/list` |
| `/api/v1/market/quotes` | GET | 获取指定品种当前报价 | `/api/tick_last` |
| `/api/v1/market/tick_stat` | GET | 获取品种统计数据 | `/api/tick_stat` |
| `ws://gateway/v1/market/stream` | WS | 实时行情推送 | 中间件轮询 `/api/tick_last` |

#### WebSocket 行情推送协议

```json
// 客户端订阅
{ "action": "subscribe", "symbols": ["EURUSD", "GBPUSD", "XAUUSD"] }

// 服务端推送 (每 500ms)
{
  "type": "quote",
  "data": {
    "symbol": "EURUSD",
    "bid": "1.08550",
    "ask": "1.08570",
    "last": "1.08560",
    "volume": "1234",
    "datetime": 1710000000000
  }
}

// 客户端取消订阅
{ "action": "unsubscribe", "symbols": ["GBPUSD"] }
```

> [!NOTE]
> MT5 Web API 没有原生 WebSocket 推送，中间件需要**定时轮询** `/api/tick_last` 或 `/api/tick_last_group`（建议 300-500ms），然后通过 WebSocket 广播给客户端。建议使用 `tick_last_group` 批量获取多品种报价以减少请求次数，并实现**差值推送**（价格无变化时不推送）。

---

### 3.5 K 线历史模块

| 接口 | 方法 | 说明 | MT5 对应接口 |
|---|---|---|---|
| `/api/v1/chart/candles` | GET | 获取 K 线数据 | `/api/chart/get` |

#### 请求参数

| 参数 | 类型 | 说明 |
|---|---|---|
| `symbol` | string | 品种名称 |
| `timeframe` | string | 时间周期：M1/M5/M15/M30/H1/H4/D1 |
| `from` | long | 起始时间（Unix 秒） |
| `to` | long | 结束时间（Unix 秒） |
| `count` | int | 蜡烛数量（优先级低于 from/to） |

#### 响应格式

```json
{
  "symbol": "EURUSD",
  "timeframe": "H1",
  "candles": [
    {
      "timestamp": 1710000000,
      "open": "1.08550",
      "high": "1.08620",
      "low": "1.08500",
      "close": "1.08600",
      "volume": "5432"
    }
  ]
}
```

> [!NOTE]
> MT5 `/api/chart/get` 只提供 **M1 (1分钟)** 原始数据。**中间件需要聚合更高周期的 K 线**（M5/M15/M30/H1/H4/D1），按 `data=dohlctv` 请求并本地聚合。建议首次请求时聚合并缓存，后续增量更新。

> [!WARNING]
> MT5 响应上限 16MB，超出时返回 `retcode: 14`（操作未完成），需用最后一条数据的时间作为新请求的 `from` 参数分批拉取。

---

### 3.6 交易模块

| 接口 | 方法 | 说明 | MT5 对应接口 |
|---|---|---|---|
| `/api/v1/trade/open` | POST | 市价开仓 | `/api/dealer/send_request` |
| `/api/v1/trade/close` | POST | 平仓 | `/api/dealer/send_request` |
| `/api/v1/trade/modify` | PUT | 修改止损/止盈 | `/api/dealer/send_request` |
| `/api/v1/trade/check_margin` | GET | 保证金预检 | `/api/trade/check_margin` |
| `/api/v1/trade/calc_profit` | GET | 盈利计算 | `/api/trade/calc_profit` |

#### 开仓请求

```json
// POST /api/v1/trade/open
{
  "symbol": "EURUSD",
  "direction": "BUY",
  "lots": "0.01",
  "stop_loss": "1.08000",
  "take_profit": "1.09000"
}
```

> [!NOTE]
> 客户端无需传 `login`，Gateway 从 JWT Token 中解析 mt5_login。

#### MT5 映射说明

| 客户端字段 | MT5 字段 | 转换逻辑 |
|---|---|---|
| `direction: "BUY"` | `Type: 0` | BUY=0, SELL=1 |
| `lots: "0.01"` | `Volume: 100` | lots × 10000 (VolumeExt: lots × 100000000) |
| `stop_loss` | `PriceSL` | 直传 |
| `take_profit` | `PriceTP` | 直传 |
| — | `Action: 200` | 固定为 Dealer 操作 |
| — | `TypeFill: 2` | IOC (Return) |

#### 交易异步流程

```
Gateway                                    MT5
  │ POST /api/dealer/send_request            │
  │ body: {Action:200, Login:954402, ...}    │
  │─────────────────────────────────────────►│
  │◄─────────────────────────────────────────│
  │ {retcode: "0 Done", answer: {ID: 13992}} │
  │                                          │
  │ 轮询（每 200-500ms，最多 30s）              │
  │ GET /api/dealer/get_request_result        │
  │ ?id=13992                                │
  │─────────────────────────────────────────►│
  │◄─────────────────────────────────────────│
  │ {answer: {ResultRetcode: "0 Done",       │
  │           ResultDeal: 12345,             │
  │           ResultOrder: 67890,            │
  │           ResultPrice: "1.08560"}}       │
```

> [!IMPORTANT]
> - `send_request` 的 retcode=0 仅表示**请求已入队**，不代表已执行
> - 必须轮询 `get_request_result` 获取最终执行结果
> - 事件订阅 3 分钟未拉取会自动删除
> - 同时最多排队 **128 个交易请求**（超限返回 10024）
> - 中间件应封装此异步流程，对客户端暴露同步接口

---

### 3.7 账户与持仓模块

| 接口 | 方法 | 说明 | MT5 对应接口 |
|---|---|---|---|
| `/api/v1/account/info` | GET | 账户信息 | `/api/user/account/get` |
| `/api/v1/positions` | GET | 当前持仓列表 | `/api/position/get_batch` |
| `/api/v1/orders` | GET | 挂单列表 | `/api/order/get_batch` |
| `/api/v1/history/deals` | GET | 历史成交 | `/api/history/get` |
| `/api/v1/history/orders` | GET | 历史订单 | `/api/history/get` |

#### 账户信息响应

```json
{
  "login": 954402,
  "group": "demoforex",
  "balance": "10000.00",
  "credit": "0.00",
  "equity": "10050.00",
  "margin": "108.50",
  "free_margin": "9941.50",
  "margin_level": "9262.67",
  "leverage": 100,
  "currency": "USD"
}
```

---

## 4. 安全要求

| 要求 | 说明 |
|---|---|
| **传输加密** | 全链路 HTTPS / WSS |
| **JWT** | 签发 access_token (15min) + refresh_token (7d) |
| **MT5 凭证隔离** | Manager 账户凭证仅存于服务端环境变量，**绝不暴露给客户端** |
| **密码安全** | 用户密码通过 HTTPS 传输，Gateway 直接调 MT5 check_password 验证，**不在本地存储密码** |
| **速率限制** | 交易接口 10 req/s/user，行情接口 30 req/s/user |
| **IP 白名单** | MT5 服务器可配置仅允许 Gateway IP 访问 |

---

## 5. 技术选型

| 项目 | 选型 | 理由 |
|---|---|---|
| **语言** | Python 3.11+ | AI 编码最成熟，生态丰富 |
| **框架** | FastAPI | 异步原生，自带 OpenAPI 文档，性能优秀 |
| **WebSocket** | FastAPI WebSocket | 内置支持 |
| **HTTP 客户端** | httpx | 支持 HTTP/2、Keep-Alive、异步 |
| **数据库** | SQLite → PostgreSQL | 初期 SQLite 轻量快速，后续可迁移 |
| **ORM** | SQLAlchemy 2.0 + alembic | 异步 ORM + 数据库迁移 |
| **认证** | python-jose / PyJWT | JWT 签发与验证 |
| **K 线聚合** | pandas / 手写聚合 | M1 → M5/M15/H1/D1 本地聚合 |
| **部署** | Docker + VPS | 靠近 MT5 服务器部署降低延迟 |
| **配置管理** | pydantic-settings | 环境变量 + .env 文件 |

---

## 6. MT5 连接管理

### 6.1 Keep-Alive 连接

MT5 Web API 要求使用 HTTPS Keep-Alive 连接，**所有请求必须通过同一个 TCP 连接**发送（参考文档示例中 `maxSockets=1`）。

使用 `httpx.AsyncClient` 时需配置：
```python
client = httpx.AsyncClient(
    base_url="https://mt5-server:443",
    http2=True,
    limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
    verify=False  # 如使用自签名证书
)
```

### 6.2 心跳保活

MT5 Web API 未提供原生 ping 机制，建议每 **60 秒**发送一次轻量请求（如 `/api/tick_last?symbol=EURUSD`）保持连接。

### 6.3 重连策略

| 场景 | 策略 |
|---|---|
| 连接断开 | 指数退避重连（1s → 2s → 4s → max 30s） |
| 认证过期 | 自动重新执行 auth/start + auth/answer |
| MT5 服务器维护 | 标记所有接口为 503，通知客户端 |

---

## 7. MT5 服务器准备清单

> [!CAUTION]
> 以下事项需找同事（MT5 服务器管理员）配合完成，是开发前的**前置条件**。

### 7.1 必须准备

| # | 事项 | 说明 | 负责人 |
|---|---|---|---|
| 1 | **开通 Demo MT5 服务器** | 需要一台可访问的 MT5 Demo 服务器，记录服务器地址和端口 | MT5 管理员 |
| 2 | **创建 Manager 账户** | 在 MT5 Admin 中创建一个 Manager 账户（如 login=1000），记录 login 和密码 | MT5 管理员 |
| 3 | **Manager 权限配置** | Manager 账户需要以下权限：<br>• `RIGHT_ADMIN` — 管理员连接<br>• `RIGHT_USER_ADD / DELETE / EDIT` — 用户增删改<br>• `RIGHT_ACC_MANAGER` — 账户管理<br>• `RIGHT_TRADE_DEALER` — 交易操作<br>• `RIGHT_CHARTS` — K 线数据<br>• `RIGHT_CFG_SYMBOLS` — 品种配置 | MT5 管理员 |
| 4 | **创建 Demo 交易组** | 创建一个名为 `demoforex`（或自定义名称）的交易组，配置：<br>• 可交易品种（如 Forex Major）<br>• 杠杆范围（如 1:100）<br>• 默认初始余额 | MT5 管理员 |
| 5 | **开启 Web API 端口** | 确认 MT5 服务器的 Web API 端口（默认 443）已开放 | MT5 管理员 |
| 6 | **SSL 证书** | 确认是使用正式证书还是自签名证书（自签名需在代码中跳过验证） | MT5 管理员 |

### 7.2 需要记录的信息

开发时需要以下信息，请找同事收集后填入 `.env` 文件：

```env
MT5_SERVER_HOST=mt5-demo.yourbroker.com
MT5_SERVER_PORT=443
MT5_MANAGER_LOGIN=1000
MT5_MANAGER_PASSWORD=YourManagerPassword
MT5_DEMO_GROUP=demoforex
MT5_INITIAL_BALANCE=10000
MT5_USE_SSL_VERIFY=false
```

### 7.3 验证连通性（可在拿到信息后执行）

```bash
# 测试 HTTPS 连通性
curl -k https://mt5-demo.yourbroker.com:443/api/auth/start?version=3470&agent=test&login=1000&type=manager

# 如果返回 JSON 包含 retcode 和 srv_rand，说明连通成功
```

---

## 8. 客户端对接方式

AstralW 客户端已预留标准 Repository 接口，切换仅需：

```kotlin
// DataModule.kt — 一行替换
@Binds @Singleton
abstract fun bindMarketRepository(impl: RemoteMarketRepository): MarketRepository
// 原来是: abstract fun bindMarketRepository(impl: MockMarketRepository): MarketRepository
```

需要新建的客户端类：
- `RemoteAuthRepository` — 注册 + JWT 登录
- `RemoteMarketRepository` — REST + WebSocket 行情
- `RemoteChartRepository` — K 线 REST
- `RemoteTradingRepository` — 交易 REST

---

## 9. Gateway 健康检查

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/v1/health` | GET | 服务健康检查 |

#### 响应格式

```json
{
  "status": "ok",
  "mt5_connected": true,
  "mt5_server": "mt5-demo.yourbroker.com",
  "uptime": 3600,
  "version": "1.0.0"
}
```

---

## 10. 错误码规范

Gateway 统一使用以下 HTTP 状态码和错误格式：

```json
{
  "error": {
    "code": "AUTH_INVALID_PASSWORD",
    "message": "密码不正确",
    "mt5_retcode": 3006
  }
}
```

| HTTP 状态码 | 场景 |
|---|---|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | JWT 无效或过期 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 429 | 速率限制 |
| 500 | Gateway 内部错误 |
| 502 | MT5 服务器返回错误 |
| 503 | MT5 服务器不可用 |

---

## 11. 验收标准

| # | 标准 |
|---|---|
| 1 | 用户可通过 email 注册获取 MT5 Demo 账户和 JWT Token |
| 2 | 用户可通过 email + 密码登录获取 JWT Token |
| 3 | 行情数据实时推送延迟 < 1s（WebSocket） |
| 4 | K 线数据支持 M1 ~ D1 共 7 个周期 |
| 5 | 可执行市价开仓/平仓并返回成交结果 |
| 6 | 账户余额/净值/保证金正确反映 |
| 7 | Docker 一键部署 |
| 8 | `/api/v1/health` 正确报告 MT5 连接状态 |
