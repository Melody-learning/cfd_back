# AstralW Gateway 接口地图

本文档用于后端开发与后续维护，不替代 FastAPI 自带接口文档。

区别：

- FastAPI 文档重点是“对外接口长什么样”
- 本文档重点是“接口内部怎么走、调哪个 MT5 端点、有哪些实现约束和风险”

## 1. 项目定位

AstralW Gateway 是 CFD 项目的中间件，负责：

- 对上提供统一 REST / WebSocket 接口给前端或上层 `app`
- 对下维护一条符合 MT5 Web API 要求的长连接会话
- 在本地保存最小必要状态，目前主要是用户映射和刷新令牌

当前真实状态源：

- 账户、持仓、订单、历史、报价、K 线、交易执行结果：以 MT5 为准
- 本地数据库：只保存 `email -> mt5_login` 映射和 `refresh_token` 哈希

## 2. 全局调用链

### 2.1 启动链路

入口文件：[app/main.py](/E:/ai-coding-study/astralw_back/app/main.py)

启动时执行：

1. 初始化本地数据库表
2. 获取全局 MT5 单例连接器
3. 最多重试 3 次连接 MT5
4. 挂载所有路由

关闭时执行：

1. 主动断开 MT5 连接

### 2.2 MT5 访问总原则

核心文件：[app/mt5/connector.py](/E:/ai-coding-study/astralw_back/app/mt5/connector.py)

关键约束：

- 全局单例
- 单个 `httpx.AsyncClient`
- 单连接复用：`max_connections=1`
- 显式 `Connection: keep-alive`
- 普通请求通过异步锁串行化
- 启动认证流程：`/api/auth/start` -> `/api/auth/answer`
- 连接成功后每 20 秒 `ping`
- 请求失败时自动重连并重试一次

结论：

- 新增 MT5 调用必须优先复用 `get_mt5()`
- 不要绕开连接器自己新建 HTTP 客户端

## 3. 本地数据模型

模型文件：[app/models/user.py](/E:/ai-coding-study/astralw_back/app/models/user.py)

### 3.1 users

字段：

- `id`
- `email`
- `mt5_login`
- `nickname`
- `created_at`

作用：

- 保存平台用户和 MT5 账户的映射关系

### 3.2 refresh_tokens

字段：

- `id`
- `user_id`
- `token_hash`
- `expires_at`
- `created_at`

作用：

- 保存刷新令牌的哈希值，不保存明文

## 4. 接口总览

### 4.1 认证模块

路由文件：[app/routers/auth.py](/E:/ai-coding-study/astralw_back/app/routers/auth.py)

业务文件：[app/services/auth_service.py](/E:/ai-coding-study/astralw_back/app/services/auth_service.py)

令牌文件：[app/services/jwt_service.py](/E:/ai-coding-study/astralw_back/app/services/jwt_service.py)

#### POST `/api/v1/auth/register`

用途：

- 注册平台用户
- 创建 MT5 Demo 账户
- 签发本地 JWT

请求体：

- `email`
- `password`
- `nickname`

对下游 MT5 调用：

1. `GET /api/user/add`
2. `GET /api/trade/balance`

本地调用链：

1. 检查邮箱是否已存在
2. 创建 MT5 Demo 账户
3. 充值初始资金
4. 本地写入 `users`
5. 签发 `access_token`
6. 签发 `refresh_token`
7. 本地写入 `refresh_tokens`

返回字段：

- `access_token`
- `refresh_token`
- `token_type`
- `mt5_login`
- `expires_in`

注意点：

- MT5 建户成功但本地落库失败时，可能出现“MT5 已有账户，本地没有映射”的半成功状态

#### POST `/api/v1/auth/login`

用途：

- 使用平台邮箱登录
- 实际密码由 MT5 校验

请求体：

- `email`
- `password`

对下游 MT5 调用：

1. `GET /api/user/check_password`

本地调用链：

1. 按邮箱查询本地 `users`
2. 取 `mt5_login`
3. 调 MT5 校验密码
4. 签发新 `access_token`
5. 签发新 `refresh_token`
6. 保存刷新令牌哈希

返回字段：

- `access_token`
- `refresh_token`
- `token_type`
- `mt5_login`
- `expires_in`

#### POST `/api/v1/auth/refresh`

用途：

- 使用刷新令牌换新访问令牌

请求体：

- `refresh_token`

本地调用链：

1. 解 JWT
2. 检查 `type=refresh`
3. 计算令牌哈希
4. 查本地 `refresh_tokens`
5. 取回 `user_id`
6. 查询本地 `users`
7. 重发新的 `access_token`

返回字段：

- `access_token`
- `token_type`
- `expires_in`

注意点：

- 当前实现不会轮换 `refresh_token`

#### POST `/api/v1/auth/logout`

用途：

- 注销当前登录会话

鉴权：

- Bearer `access_token`

本地调用链：

1. 解析访问令牌
2. 获取当前用户
3. 删除该用户所有刷新令牌

返回：

- `204 No Content`

注意点：

- 当前实现是“全设备登出”

### 4.2 健康检查

路由文件：[app/routers/health.py](/E:/ai-coding-study/astralw_back/app/routers/health.py)

#### GET `/api/v1/health`

用途：

- 返回服务和 MT5 连接状态

返回字段：

- `status`
- `mt5_connected`
- `mt5_server`
- `uptime`
- `version`

对下游 MT5 调用：

- 无直接调用

### 4.3 行情模块

路由文件：[app/routers/market.py](/E:/ai-coding-study/astralw_back/app/routers/market.py)

#### GET `/api/v1/market/symbols`

用途：

- 获取可用品种列表

鉴权：

- Bearer `access_token`

对下游 MT5 调用：

1. `GET /api/symbol/list`

返回字段：

- `symbols[].symbol`

注意点：

- 当前只返回极简 `symbol`
- `schemas` 中更丰富的字段目前没有真正填满

#### GET `/api/v1/market/quotes`

用途：

- 获取一个或多个品种的最新报价

鉴权：

- Bearer `access_token`

查询参数：

- `symbols`，逗号分隔，例如 `EURUSD,XAUUSD`

对下游 MT5 调用：

1. `GET /api/tick/last`

返回字段：

- `quotes[].symbol`
- `quotes[].bid`
- `quotes[].ask`
- `quotes[].last`
- `quotes[].volume`
- `quotes[].datetime`

#### GET `/api/v1/market/tick_stat`

用途：

- 获取品种统计数据

鉴权：

- Bearer `access_token`

查询参数：

- `symbols`

对下游 MT5 调用：

1. `GET /api/tick/stat`

返回字段：

- `stats[].symbol`
- `stats[].bid`
- `stats[].ask`
- `stats[].last`
- `stats[].high`
- `stats[].low`
- `stats[].volume`
- `stats[].price_change`
- `stats[].datetime`

注意点：

- 当前返回字段比 `schemas` 定义更宽，接口文档和真实实现存在偏差

#### WebSocket `/api/v1/market/stream`

用途：

- 订阅实时行情

当前实现：

- 客户端建立 WebSocket
- 发送 `subscribe` 或 `unsubscribe`
- 服务端维护每个连接的订阅品种集合
- 后台全局轮询任务每 500ms 汇总所有订阅品种
- 调一次 MT5 `/api/tick/last`
- 对发生变化的品种广播

客户端消息：

```json
{"action":"subscribe","symbols":["EURUSD","XAUUSD"]}
```

```json
{"action":"unsubscribe","symbols":["XAUUSD"]}
```

服务端消息：

```json
{"type":"subscribed","symbols":["EURUSD","XAUUSD"]}
```

```json
{"type":"quote","data":{"symbol":"EURUSD","bid":"1.1","ask":"1.2","last":"1.15","volume":"0","datetime":0}}
```

对下游 MT5 调用：

1. 周期性 `GET /api/tick/last`

注意点：

- 当前未做 WebSocket 鉴权
- 当前只比较 `bid/ask` 去重
- 全局轮询任务会常驻

### 4.4 图表模块

路由文件：[app/routers/chart.py](/E:/ai-coding-study/astralw_back/app/routers/chart.py)

#### GET `/api/v1/chart/candles`

用途：

- 获取 K 线数据

鉴权：

- Bearer `access_token`

查询参数：

- `symbol`
- `timeframe`，支持 `M1/M5/M15/M30/H1/H4/D1`
- `from`
- `to`
- `count`

对下游 MT5 调用：

1. `GET /api/chart/get`

实现逻辑：

1. 统一从 MT5 拉取 M1 原始数据
2. 如未显式指定 `from/to`，根据 `count` 反推时间窗口
3. 如果 MT5 返回 `retcode` 以 `14` 开头，则继续分页拉取
4. 对高周期在服务端本地聚合

返回字段：

- `symbol`
- `timeframe`
- `candles[].timestamp`
- `candles[].open`
- `candles[].high`
- `candles[].low`
- `candles[].close`
- `candles[].volume`

注意点：

- 高周期 K 线不是 MT5 直接返回，而是应用内聚合
- 数据量大时，这里容易成为性能热点

### 4.5 交易模块

路由文件：[app/routers/trade.py](/E:/ai-coding-study/astralw_back/app/routers/trade.py)

#### 交易执行共性

当前交易接口的核心模式不是“请求即成交”，而是：

1. 先调用 `POST /api/dealer/send_request`
2. 获取 `request_id`
3. 再轮询 `GET /api/dealer/get_request_result`
4. 识别成交状态并整形返回

关键 MT5 返回码：

- `10006`：处理中
- `10008`：挂单已挂出
- `10009`：成交完成

#### POST `/api/v1/trade/open`

用途：

- 市价开仓

鉴权：

- Bearer `access_token`

请求体：

- `symbol`
- `direction`
- `lots`
- `stop_loss`
- `take_profit`

对下游 MT5 调用：

1. `POST /api/dealer/send_request`
2. `GET /api/dealer/get_request_result`

核心转换：

- `direction: BUY -> Type=0`
- `direction: SELL -> Type=1`
- `lots -> Volume`
- `lots -> VolumeExt`

返回字段：

- `order`
- `deal`
- `price`
- `volume`
- `retcode`
- `message`

#### POST `/api/v1/trade/close`

用途：

- 平仓

鉴权：

- Bearer `access_token`

请求体：

- `position`
- `lots`

对下游 MT5 调用：

1. `POST /api/dealer/send_request`
2. `GET /api/dealer/get_request_result`

返回字段：

- `order`
- `deal`
- `price`
- `volume`
- `retcode`
- `message`

注意点：

- 当前实现里平仓 `Type` 被写死，理论上应该根据持仓方向决定反向类型

#### PUT `/api/v1/trade/modify`

用途：

- 修改止损止盈

鉴权：

- Bearer `access_token`

请求体：

- `position`
- `stop_loss`
- `take_profit`

对下游 MT5 调用：

1. `POST /api/dealer/send_request`
2. `GET /api/dealer/get_request_result`

返回字段：

- `order`
- `deal`
- `price`
- `retcode`
- `message`

注意点：

- 当前实现没有像开仓和平仓那样严格检查 `request_id` 是否为空

#### GET `/api/v1/trade/check_margin`

用途：

- 保证金预检

鉴权：

- Bearer `access_token`

查询参数：

- `symbol`
- `direction`
- `lots`

对下游 MT5 调用：

1. `GET /api/trade/check_margin`

返回字段：

- `margin`
- `free_margin`
- `margin_level`

#### GET `/api/v1/trade/calc_profit`

用途：

- 盈亏试算

鉴权：

- Bearer `access_token`

查询参数：

- `symbol`
- `direction`
- `lots`
- `price_open`
- `price_close`

对下游 MT5 调用：

1. `GET /api/user/get`
2. `GET /api/trade/calc_profit`

实现说明：

- 先读取用户 `Group`
- 再据此计算盈亏

返回字段：

- `profit`
- `profit_rate`

### 4.6 账户与历史模块

路由文件：[app/routers/account.py](/E:/ai-coding-study/astralw_back/app/routers/account.py)

#### GET `/api/v1/account/info`

用途：

- 获取账户信息

鉴权：

- Bearer `access_token`

对下游 MT5 调用：

1. `GET /api/user/account/get`

返回字段：

- `login`
- `group`
- `balance`
- `credit`
- `equity`
- `margin`
- `free_margin`
- `margin_level`
- `leverage`
- `currency`

#### GET `/api/v1/positions`

用途：

- 获取当前持仓

鉴权：

- Bearer `access_token`

对下游 MT5 调用：

1. `GET /api/position/get_batch`

返回字段：

- `positions[].position`
- `positions[].symbol`
- `positions[].direction`
- `positions[].lots`
- `positions[].price_open`
- `positions[].price_current`
- `positions[].profit`
- `positions[].stop_loss`
- `positions[].take_profit`
- `positions[].time_create`

#### GET `/api/v1/orders`

用途：

- 获取当前挂单

鉴权：

- Bearer `access_token`

对下游 MT5 调用：

1. `GET /api/order/get_batch`

返回字段：

- `orders[].order`
- `orders[].symbol`
- `orders[].type`
- `orders[].lots`
- `orders[].price_order`
- `orders[].stop_loss`
- `orders[].take_profit`
- `orders[].time_setup`
- `orders[].state`

#### GET `/api/v1/history/deals`

用途：

- 获取历史成交

鉴权：

- Bearer `access_token`

查询参数：

- `from`
- `to`

对下游 MT5 调用：

1. `GET /api/history/get`，`type=deal`

返回字段：

- `deals`

说明：

- 当前基本是 MT5 返回的轻量直通

#### GET `/api/v1/history/orders`

用途：

- 获取历史订单

鉴权：

- Bearer `access_token`

查询参数：

- `from`
- `to`

对下游 MT5 调用：

1. `GET /api/history/get`，`type=order`

返回字段：

- `orders`

说明：

- 当前基本是 MT5 返回的轻量直通

## 5. 鉴权规则

当前鉴权入口：[app/services/jwt_service.py](/E:/ai-coding-study/astralw_back/app/services/jwt_service.py)

### 5.1 需要 Bearer Token 的接口

- `/api/v1/auth/logout`
- `/api/v1/market/symbols`
- `/api/v1/market/quotes`
- `/api/v1/market/tick_stat`
- `/api/v1/chart/candles`
- `/api/v1/trade/open`
- `/api/v1/trade/close`
- `/api/v1/trade/modify`
- `/api/v1/trade/check_margin`
- `/api/v1/trade/calc_profit`
- `/api/v1/account/info`
- `/api/v1/positions`
- `/api/v1/orders`
- `/api/v1/history/deals`
- `/api/v1/history/orders`

### 5.2 当前未鉴权接口

- `/api/v1/auth/register`
- `/api/v1/auth/login`
- `/api/v1/auth/refresh`
- `/api/v1/health`
- `WebSocket /api/v1/market/stream`

## 6. 错误风格

当前项目整体错误风格偏统一：

```json
{
  "error": {
    "code": "SOME_CODE",
    "message": "说明信息"
  }
}
```

大致约定：

- `401`：本地鉴权失败或令牌无效
- `502`：MT5 返回业务错误
- `503`：MT5 不可用或连接失败

## 7. 已确认的高风险点

### 7.1 交易链路

- 平仓方向当前写死，存在业务错误风险
- 修改止损止盈时 `request_id` 校验不完整
- 交易结果轮询使用 `raw_get()`，与普通请求并发交错时要谨慎

### 7.2 行情链路

- WebSocket 当前未鉴权
- 全局轮询任务常驻
- 当前去重策略只比较 `bid/ask`

### 7.3 认证链路

- `refresh_token` 当前不轮换
- 一个用户可累积多条有效刷新令牌

### 7.4 图表链路

- K 线聚合全在应用层完成
- 数据量大时可能成为性能瓶颈

## 8. 当前工程结论

这个项目已经完成了主接口贯通，但仍处于“已打通主流程、尚未全面治理”的阶段。

更准确地说：

- 它已经可以支持前端联调和后端继续补接口
- 但在交易健壮性、实时链路治理、会话治理、测试体系方面还需要继续加固

后续开发默认原则：

- 优先保护 MT5 连接器
- 不把本地数据库当成交易真相源
- 保持价格、金额、手数等精度敏感字段继续用字符串
- 交易类功能继续围绕 `send_request + polling result` 模式扩展
