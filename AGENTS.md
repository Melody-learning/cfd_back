# AstralW Gateway - Agent 手册

本文档用于指导在本仓库内工作的 AI Agent 与开发协作者。

## 项目概况

- 项目类型：CFD 项目中间件 / MT5 Gateway
- 语言：Python 3.11+
- 框架：FastAPI
- 数据库：SQLite + SQLAlchemy 2.0 Async
- HTTP 客户端：httpx
- 鉴权：JWT
- 依赖管理：`pip` + `requirements.txt`

项目职责：

- 对上向前端或上层 `app` 提供统一的 REST / WebSocket 接口
- 对下维护一条符合 MT5 Web API 要求的长连接会话
- 本地仅保存最小必要状态，目前主要是用户映射和刷新令牌

项目边界：

- 交易、持仓、订单、历史、报价、K 线的真实来源是 MT5
- 本地数据库不是交易账本，只是认证与映射层
- 用户主密码不在本地存储，登录校验依赖 MT5

## 代码结构

```text
app/
├─ main.py              # FastAPI 入口与生命周期管理
├─ config.py            # 环境变量配置
├─ database.py          # SQLAlchemy 异步引擎与会话
├─ routers/             # 对外接口层
├─ services/            # 认证与业务逻辑
├─ schemas/             # 请求/响应模型
├─ models/              # SQLAlchemy ORM 模型
└─ mt5/                 # MT5 认证算法与连接管理

share/
├─ api_spec.md          # 前后端共享接口文档
└─ api_changelog.md     # 接口变更记录
```

当前核心路由：

- `auth`：注册、登录、刷新、登出
- `market`：品种、报价、统计、WebSocket 行情
- `chart`：K 线数据
- `trade`：开仓、平仓、修改、保证金检查、盈亏试算
- `account`：账户、持仓、订单、历史
- `health`：健康检查

## 关键实现事实

### 1. MT5 连接器是系统核心

核心文件：`app/mt5/connector.py`

必须默认相信并复用现有连接器设计：

- 使用全局单例
- 使用单个 `httpx.AsyncClient`
- 强制单连接复用
- 走 `keep-alive`
- 通过 `/api/auth/start` 和 `/api/auth/answer` 完成双向认证
- 通过后台心跳维持连接
- 普通请求通过异步锁串行化

禁止做法：

- 不要绕开 `get_mt5()` 自己新建 MT5 客户端
- 不要把 MT5 当成普通无状态 REST 服务随意并发调用

### 2. 交易接口遵循异步确认模式

交易类接口不能把 `dealer/send_request` 当作最终成功。

必须遵循：

1. 提交 `send_request`
2. 获取 `request_id`
3. 轮询 `get_request_result`
4. 再返回成交或挂单结果

如果改动交易逻辑，优先保护这条链路。

### 3. 精度敏感字段保持字符串风格

当前项目对金额、价格、手数、盈亏等字段，整体风格是以字符串返回。

默认规则：

- 对外响应优先保持字符串
- 不要随意改成浮点数
- 只有在确实需要内部计算时，才在内部转换

### 4. 本地数据库不是交易真相源

本地当前主要表：

- `users`
- `refresh_tokens`

默认认知：

- 平台用户身份和 MT5 账号做映射
- 刷新令牌做本地会话管理
- 账户、持仓、订单、历史、行情等仍以 MT5 为准

补充约束：

- `astralw_gateway.db` 虽然不是交易真相源，但仍然是重要本地状态文件
- 其中保存 `email -> mt5_login` 映射和刷新令牌
- 未经明确批准，不得在清理目录时删除 `.db` 文件

## 开发约定

### 代码风格

- 遵循 PEP 8
- 新增代码应带类型注解
- 优先使用异步接口
- 路由层尽量薄，复杂逻辑下沉到 `services` 或 `mt5`
- 错误返回尽量保持现有结构化风格

### 错误处理

默认约定：

- 本地鉴权失败：`401`
- MT5 业务错误：`502`
- MT5 连接失败或不可用：`503`

新增接口时：

- 需要把 MT5 异常转成明确、结构化的响应
- 不要把底层异常栈直接暴露给前端

### 兼容性原则

没有明确要求时，尽量避免：

- 修改现有接口路径
- 修改既有字段名
- 修改字符串字段为数字字段
- 修改成功/失败判断语义

如果发生 Breaking Change：

- 更新 `share/api_spec.md`
- 在 `share/api_changelog.md` 顶部追加记录

## 环境变量参考

完整的环境变量清单（对应 `app/config.py` 中的 `Settings` 类）：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `MT5_SERVER_HOST` | `43.128.39.163` | MT5 服务器地址 |
| `MT5_SERVER_PORT` | `443` | MT5 Web API 端口 |
| `MT5_MANAGER_LOGIN` | `1015` | Manager 账号 |
| `MT5_MANAGER_PASSWORD` | _(空)_ | Manager 密码 |
| `MT5_WEBAPI_PASSWORD` | _(空)_ | WebAPI 密码（优先使用） |
| `MT5_DEMO_GROUP` | `demo\retail` | 新注册用户的 MT5 交易组 |
| `MT5_INITIAL_BALANCE` | `10000.0` | 新注册用户的初始余额 |
| `MT5_USE_SSL_VERIFY` | `false` | 是否校验 MT5 SSL 证书 |
| `JWT_SECRET_KEY` | `dev-secret-key-...` | JWT 签名密钥（生产环境必须更换） |
| `JWT_ALGORITHM` | `HS256` | JWT 算法 |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | 访问令牌有效期（分钟） |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | 刷新令牌有效期（天） |
| `DATABASE_URL` | `sqlite+aiosqlite:///./astralw_gateway.db` | 数据库连接字符串 |
| `APP_NAME` | `AstralW Gateway` | 应用名称 |
| `APP_VERSION` | `1.0.0` | 版本号 |
| `DEBUG` | `true` | 调试模式（控制 SQL 日志输出） |

## Gateway → MT5 端点映射

| Gateway 接口 | MT5 Web API 端点 |
|---|---|
| `POST /auth/register` | `GET /api/user/add` + `GET /api/trade/balance` |
| `POST /auth/login` | `GET /api/user/check_password` |
| `GET /market/symbols` | `GET /api/symbol/list` |
| `GET /market/quotes` | `GET /api/tick/last` |
| `GET /market/tick_stat` | `GET /api/tick/stat` |
| `WS /market/stream` | `GET /api/tick/last` (500ms 轮询) |
| `GET /chart/candles` | `GET /api/chart/get` (M1 原始数据) |
| `POST /trade/open` | `GET /api/tick/last` + `POST /api/dealer/send_request` + `GET /api/dealer/get_request_result` |
| `POST /trade/close` | `GET /api/position/get_batch` + `POST /api/dealer/send_request` + `GET /api/dealer/get_request_result` |
| `PUT /trade/modify` | `POST /api/dealer/send_request` + `GET /api/dealer/get_request_result` |
| `GET /trade/check_margin` | `GET /api/trade/check_margin` |
| `GET /trade/calc_profit` | `GET /api/user/get` + `GET /api/trade/calc_profit` |
| `GET /account/info` | `GET /api/user/account/get` |
| `GET /positions` | `GET /api/position/get_batch` |
| `GET /orders` | `GET /api/order/get_batch` |
| `GET /history/deals` | `GET /api/history/get` (type=deal) |
| `GET /history/orders` | `GET /api/history/get` (type=order) |
| _(内部) 认证_ | `GET /api/auth/start` + `GET /api/auth/answer` |
| _(内部) 心跳_ | `GET /api/test/access` |
| _(内部) 时间校准_ | `GET /api/common/get` |

## 错误码速查

完整的错误码参考请见 [ERROR_CODES.md](ERROR_CODES.md)。

当前已使用的 `error.code` 值：

| error.code | HTTP | 说明 |
|------------|------|------|
| `EMAIL_EXISTS` | 409 | 邮箱已注册 |
| `AUTH_FAILED` | 401 | 邮箱未注册 |
| `AUTH_INVALID_PASSWORD` | 401 | 密码错误 |
| `TOKEN_INVALID` | 401 | Token 无效或过期 |
| `TOKEN_EXPIRED` | 401 | Refresh token 已失效 |
| `USER_NOT_FOUND` | 401 | 用户不存在 |
| `MT5_UNAVAILABLE` | 503 | MT5 连接不可用 |
| `MT5_API_ERROR` | 502 | MT5 API 返回错误 |
| `MT5_USER_ADD_FAILED` | 502 | 创建 MT5 用户失败 |
| `INVALID_DIRECTION` | 400 | 交易方向无效 |
| `QUOTE_UNAVAILABLE` | 502 | 报价不可用 |
| `TRADE_SUBMIT_FAILED` | 502 | 交易提交失败 |
| `TRADE_FAILED` | 502 | 交易执行失败 |
| `POSITION_NOT_FOUND` | 404 | 持仓不存在 |

## 已知风险点

Agent 在改动以下区域时要格外谨慎：

- `app/mt5/connector.py`：连接与会话稳定性的核心
- `app/routers/trade.py`：交易提交与结果轮询链路
- `app/routers/market.py`：WebSocket 行情轮询与广播
- `app/routers/chart.py`：K 线聚合与分页拉取
- `app/services/auth_service.py`：注册与登录链路
- `app/services/jwt_service.py`：访问令牌与刷新令牌策略

## 运行与验证

安装依赖：

```bash
pip install -r requirements.txt
```

启动开发服务：

```powershell
cd D:\cfd_back
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

接口文档：

```text
http://127.0.0.1:8000/docs
```

当前测试现状：

- 仓库内暂时没有完整的正式测试体系
- 不应默认使用 `pytest` 作为主要验证入口

`scripts/` 目录下的可用诊断脚本：

- `scripts/export_mt5_recent_logs.py` — 导出 MT5 近期日志
- `scripts/mt5_tls_probe.py` — MT5 TLS 连通性探测
- `scripts/probe_mt5_local.ps1` — 本地 MT5 探测
- `scripts/probe_mt5_server.ps1` — 远程 MT5 服务器探测

使用这些脚本前，应先确认：

- 本地 `.env` 是否配置正确
- MT5 当前是否可连通

## 文档优先级

面向协作时，文档优先级如下：

1. `share/api_spec.md`
2. `share/api_changelog.md`
3. `backend_interface_map.md`
4. FastAPI `/docs`

解释：

- `share/api_spec.md` 是前后端共享接口契约
- `share/api_changelog.md` 是最近改动通知
- `backend_interface_map.md` 是后端内部开发地图
- FastAPI `/docs` 主要用于运行时查看当前注册接口

## 跨项目协作流程

前端项目路径：`e:\astralw_new`

共享文件：

- 接口文档：`share/api_spec.md`
- 变更记录：`share/api_changelog.md`

协作规则：

1. 前端先对话，完成 UI，并把需要的接口写入 `share/api_spec.md` 的待实现区域
2. 后端读取 `share/api_spec.md` 的待实现部分，完成实现
3. 后端实现完成后，把接口从待实现区移动到正式区，并在 `share/api_changelog.md` 顶部追加变更记录
4. 前端再根据 `share/api_changelog.md` 的最新变更完成对接

字段格式约定：

- 金额、价格使用字符串
- 时间使用 Unix 秒级时间戳
- 字段命名使用 `snake_case`

## Agent 默认行为

Agent 在本项目内工作时，应默认遵守以下行为：

- 先看共享接口文档，再决定是否改代码
- 需要新增或修改接口时，同步维护共享文档
- 不擅自改动已有协作流程
- 不把本地数据库扩展成交易真相源，除非明确有架构决策
- 新增 MT5 调用时优先复用现有连接器能力
- 修改交易逻辑时优先保护结果轮询链路
- 面向前端输出时，优先保持兼容性和字段稳定
