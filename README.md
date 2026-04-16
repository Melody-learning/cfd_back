# AstralW Gateway

**CFD 差价合约交易中间件** — 连接 Android 客户端与 MT5 交易服务器的 Web API Gateway。

```
┌─────────────┐    REST / WebSocket    ┌──────────────────┐    HTTPS (keep-alive)    ┌─────────────┐
│  Android 端  │ ◄────────────────────► │  AstralW Gateway │ ◄─────────────────────► │  MT5 Server  │
│  (Kotlin)    │      JWT 鉴权          │  (FastAPI)       │   单连接 + 20s 心跳      │  :443        │
└─────────────┘                        └──────────────────┘                          └─────────────┘
```

Gateway 职责：
- 对上提供统一的 REST / WebSocket 接口给 Android 客户端
- 对下维护一条符合 MT5 Web API 要求的长连接会话
- 在本地保存最小必要状态（用户映射 + 刷新令牌）

---

## 快速启动

### 前置条件

- Python 3.11+
- MT5 服务器地址和 Manager 账户凭证

### 1. 创建虚拟环境

```powershell
cd D:\cfd_back
python -m venv .venv
.\.venv\Scripts\activate
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

复制并编辑 `.env` 文件（已在 `.gitignore` 中排除）：

```env
# === 必填 ===
MT5_SERVER_HOST=43.128.39.163
MT5_SERVER_PORT=443
MT5_MANAGER_LOGIN=1015
MT5_MANAGER_PASSWORD=你的Manager密码      # ⚠️ 必须填写
MT5_WEBAPI_PASSWORD=你的WebAPI密码         # ⚠️ 必须填写（优先使用）

# === 可选（有默认值） ===
MT5_DEMO_GROUP=demo\retail
MT5_INITIAL_BALANCE=10000.0
MT5_USE_SSL_VERIFY=false
JWT_SECRET_KEY=dev-secret-key-change-in-production
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
DATABASE_URL=sqlite+aiosqlite:///./astralw_gateway.db
DEBUG=true
```

> **注意**：`MT5_MANAGER_PASSWORD` 或 `MT5_WEBAPI_PASSWORD` 至少需要配置一个才能连接 MT5 服务器。请向 MT5 管理员获取。

### 4. 启动开发服务

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. 访问接口文档

启动成功后，打开浏览器访问 Swagger 文档：

```
http://127.0.0.1:8000/docs
```

---

## 技术栈

| 项目 | 选型 | 版本要求 |
|------|------|---------|
| **语言** | Python | 3.11+ |
| **Web 框架** | FastAPI | >= 0.109.0 |
| **ASGI 服务器** | Uvicorn | >= 0.27.0 |
| **HTTP 客户端** | httpx | >= 0.27.0 |
| **数据库** | SQLite + SQLAlchemy 2.0 Async | >= 2.0.25 |
| **异步驱动** | aiosqlite | >= 0.19.0 |
| **鉴权** | JWT (python-jose) | >= 3.3.0 |
| **配置管理** | pydantic-settings | >= 2.1.0 |
| **依赖管理** | pip + requirements.txt | — |

---

## 目录结构

```
d:\cfd_back\
├── app/                          # 核心应用代码
│   ├── main.py                   # FastAPI 入口、生命周期管理、全局异常处理
│   ├── config.py                 # 环境变量配置（pydantic-settings）
│   ├── database.py               # SQLAlchemy 异步引擎与会话工厂
│   ├── mt5/                      # MT5 连接核心
│   │   ├── connector.py          # 单例连接器、认证、心跳、重连（系统核心）
│   │   └── auth.py               # MD5 双向认证算法实现
│   ├── routers/                  # 路由层（对外接口）
│   │   ├── auth.py               # 注册、登录、刷新、登出
│   │   ├── market.py             # 品种列表、报价、统计、WebSocket 行情推送
│   │   ├── chart.py              # K 线历史数据（含本地聚合）
│   │   ├── trade.py              # 交易：开仓、平仓、修改、保证金检查、盈亏试算
│   │   ├── account.py            # 账户信息、持仓列表、挂单、历史成交
│   │   └── health.py             # 服务健康检查
│   ├── services/                 # 业务逻辑层
│   │   ├── auth_service.py       # 注册与登录业务流程
│   │   └── jwt_service.py        # JWT 签发、验证、用户解析
│   ├── schemas/                  # Pydantic 请求/响应模型
│   └── models/                   # SQLAlchemy ORM 模型（User + RefreshToken）
│
├── share/                        # 前后端共享文档
│   ├── api_spec.md               # 接口契约文档（前后端共同维护）
│   └── api_changelog.md          # 接口变更日志
│
├── scripts/                      # 调试与诊断脚本
│   ├── export_mt5_recent_logs.py # 导出 MT5 近期日志
│   ├── mt5_tls_probe.py          # MT5 TLS 连通性探测
│   ├── probe_mt5_local.ps1       # 本地 MT5 探测
│   └── probe_mt5_server.ps1      # 远程 MT5 服务器探测
│
├── MT5_web_api_docs/             # MT5 Web API 中文翻译文档（7 章 + 补充）
│
├── .env                          # 环境变量配置（不入库）
├── requirements.txt              # Python 依赖
├── AGENTS.md                     # AI Agent 与开发者工作手册
├── ARCHITECTURE.md               # 系统架构设计文档
├── ERROR_CODES.md                # 错误码参考文档
├── backend_interface_map.md      # 后端内部接口地图（详尽版）
└── middleware_requirements.md    # 原始需求文档
```

---

## 文档导航

| 文档 | 说明 | 面向 |
|------|------|------|
| [AGENTS.md](AGENTS.md) | AI Agent 与开发者工作手册，包含项目规则、开发约定、风险点 | Agent / 开发者 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 系统架构设计、数据流图、设计决策记录 | 开发者 |
| [ERROR_CODES.md](ERROR_CODES.md) | 完整的错误码枚举与处理建议 | 前后端 |
| [share/api_spec.md](share/api_spec.md) | 前后端共享接口契约 | 前后端 |
| [share/api_changelog.md](share/api_changelog.md) | 接口变更日志 | 前后端 |
| [backend_interface_map.md](backend_interface_map.md) | 后端内部接口地图，含每个接口的 MT5 调用链 | 后端 |
| [MT5_web_api_docs/](MT5_web_api_docs/) | MT5 Web API 中文翻译文档（7 章） | 后端 |

---

## 许可证

内部项目，仅限授权人员使用。
