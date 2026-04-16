# AstralW Gateway - 接口变更记录

> 维护方：后端
> 最后更新：2026-04-10

---

## [2026-04-10] 挂单功能支持

涉及接口：`POST /api/v1/trade/open`、`GET /api/v1/orders`、`DELETE /api/v1/orders/{ticket}`

### `POST /api/v1/trade/open` — 扩展支持挂单（非 Breaking Change）

新增 3 个可选字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `order_type` | String | 默认 `"MARKET"`。可选: `BUY_LIMIT` / `SELL_LIMIT` / `BUY_STOP` / `SELL_STOP` |
| `price` | String | 挂单触发价格，挂单类型时必填 |
| `expiration` | Integer | 到期时间 (Unix 秒)，0=不限期 |

向后兼容：不传 `order_type` 时行为与此前完全一致。

挂单成功时 `retcode` 返回 `"10008"`。

### `GET /api/v1/orders` — **Breaking Change**

| 变更项 | 旧字段 | 新字段 |
|--------|--------|--------|
| 订单标识 | `order` (int) | `ticket` (int) |
| 订单类型 | `type` (int) | `type` (string: `BUY_LIMIT` 等) |
| 手数 | `lots` (string) | `volume` (string, MT5 内部格式) |
| 触发价 | `price_order` (string) | `price_open` (string) |
| 状态 | `state` (int) | 移除 |
| 新增 | — | `price_current`、`expiration`、`comment` |

前端适配：按新字段名和类型调整解析逻辑。

### `DELETE /api/v1/orders/{ticket}` — 新增端点

取消挂单，路径参数为 MT5 订单 ticket。响应复用 `TradeResult` 格式。

---

## [2026-04-10] Bugfix: K 线时间坐标修正

涉及接口：`GET /api/v1/chart/candles`

**类型：Bugfix（非 Breaking Change）**

问题：蜡烛数据实际返回的是 8 小时前的历史数据，导致 M1 最后一根蜡烛异常巨大（100+ pips）。

修复：后端请求 MT5 时的时间参数已从 UTC 校正为 MT5 服务器时间。

前端影响：
- **无需修改任何代码**
- 接口路径、请求参数、返回格式均不变
- 蜡烛 `timestamp` 坐标系不变（仍为 MT5 服务器时间，与行情 `datetime` 一致）
- 修复后蜡烛 `close` 将与实时 `bid` 保持一致（差距 <20 pips）
- 如前端有针对"巨大蜡烛"的本地 workaround，现在可以移除

---

## [2026-03-23] 历史成交接口补充

涉及接口：`GET /api/v1/history/deals`

本次变更：

- 后端不再原样透传 MT5 历史成交结构
- 统一返回前端可直接消费的 `deals[]` 字段
- 明确补充以下响应字段：
  - `deal`
  - `order`
  - `symbol`
  - `type`
  - `direction`
  - `volume`
  - `price`
  - `profit`
  - `commission`
  - `swap`
  - `time`
  - `comment`

字段说明：

- `type` 为 MT5 原始 `Action`
- `direction` 为后端基于 `Action` 映射出的方向
- `volume` 仍为 MT5 内部格式，`100 = 0.01 手`
- `from` / `to` 使用 Unix 秒
- 当前暂不分页

对前端影响：

- 历史成交列表现在可以直接按统一字段渲染
- 如果前端展示手数，需要自行将 `volume / 10000`

---

## [2026-03-23] v5 重大更新

### 交易接口 Breaking Changes

涉及接口：`POST /api/v1/trade/open`、`POST /api/v1/trade/close`、`PUT /api/v1/trade/modify`

| 变更项 | 旧行为 | 新行为 |
|---|---|---|
| 返回方式 | 异步，`retcode=0` 表示成功 | 同步返回成交结果 |
| 成功判断 | `retcode == "0"` | `retcode == "10009"` 或 `"10008"` |
| 新增字段 | 无 | `price`、`volume` |
| 响应耗时 | ~100ms | 成功约 ~900ms，超时约 ~15s |

前端适配：

```kotlin
when (result.retcode) {
    "10009", "10008" -> { /* 成交成功 / 挂单成功 */ }
    "0" -> { /* 已提交，继续确认 */ }
    else -> { /* 失败 */ }
}
```

### K 线接口参数变更

涉及接口：`GET /api/v1/chart/candles`

- `from`、`to` 改为可选
- 新增 `count` 参数，默认 `100`
- 推荐用法：`?symbol=EURUSD&timeframe=H1&count=50`

### tick_stat 新增字段

涉及接口：`GET /api/v1/market/tick_stat`

新增：

- `bid`
- `ask`
- `price_change`
- `datetime`

### 连接稳定性

- 修复频繁 `503` 问题
- 前端建议对 `503` 做 1 到 2 次自动重试，间隔 2 秒

---

## [2026-03-19] 初始版本

- 认证模块：注册、登录、Token 刷新
- 行情模块：品种列表、报价、WebSocket 推送
- K 线模块：M1 到 D1 历史 K 线
- 交易模块：开仓、平仓、修改止损止盈
- 账户模块：账户信息、持仓列表、历史成交

---

新的变更记录添加在文件顶部，保持时间倒序。
