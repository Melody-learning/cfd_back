# AstralW Gateway - 接口文档

> 最后更新：2026-03-23
> Base URL：`http://<server>:8000`
> Swagger：`http://<server>:8000/docs`

---

## 认证

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/v1/auth/register` | POST | 注册 `{email, password, nickname}` -> `{access_token, refresh_token, mt5_login}` |
| `/api/v1/auth/login` | POST | 登录 `{email, password}` -> 同上 |
| `/api/v1/auth/refresh` | POST | 刷新 `{refresh_token}` -> `{access_token}` |
| `/api/v1/auth/logout` | POST | 登出，需要 Bearer Token |

密码要求：

- 8 到 16 位
- 大写 + 小写 + 数字 + 特殊字符

---

## 行情

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/v1/market/symbols` | GET | 品种列表 |
| `/api/v1/market/quotes` | GET | 当前报价，`?symbols=EURUSD,GBPUSD` |
| `/api/v1/market/tick_stat` | GET | 品种统计，`?symbols=EURUSD` |
| `ws://.../api/v1/market/stream` | WS | 实时推送，约 500ms 轮询 |

WebSocket 协议：

```json
{ "action": "subscribe", "symbols": ["EURUSD"] }
```

```json
{ "type": "quote", "data": { "symbol":"EURUSD", "bid":"1.15700", "ask":"1.15703", "datetime":1774020638 } }
```

```json
{ "action": "unsubscribe", "symbols": ["EURUSD"] }
```

---

## K 线

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/v1/chart/candles` | GET | K 线数据 |

参数：

- `symbol`：必填
- `timeframe`：`M1` 到 `D1`，默认 `M1`
- `count`：默认 `100`
- `from` / `to`：可选，Unix 秒

推荐：

```text
/api/v1/chart/candles?symbol=EURUSD&timeframe=H1&count=50
```

响应：

```json
{
  "symbol": "EURUSD",
  "timeframe": "H1",
  "candles": [
    {
      "timestamp": 1774020638,
      "open": "1.15200",
      "high": "1.15300",
      "low": "1.15150",
      "close": "1.15255",
      "volume": "1234"
    }
  ]
}
```

---

## 交易

需要 Bearer Token。

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/v1/trade/open` | POST | 市价开仓 `{symbol, direction, lots, stop_loss?, take_profit?}` |
| `/api/v1/trade/close` | POST | 平仓 `{position, lots}` |
| `/api/v1/trade/modify` | PUT | 修改止损止盈 `{position, stop_loss?, take_profit?}` |
| `/api/v1/trade/check_margin` | GET | 保证金预检 `?symbol&direction&lots` |
| `/api/v1/trade/calc_profit` | GET | 盈亏试算 `?symbol&direction&lots&price_open&price_close` |

交易响应：

```json
{
  "order": 0,
  "deal": 0,
  "price": "1.15255",
  "volume": "100",
  "retcode": "10009",
  "message": "成交成功"
}
```

`retcode` 说明：

| retcode | 含义 | 前端处理 |
|---|---|---|
| `"10009"` | 成交成功 | 显示成交价 |
| `"10008"` | 挂单成功 | 显示挂单 |
| `"0"` | 已提交未确认 | 轮询持仓或历史确认 |
| 其他 | 失败 | 显示错误 |

说明：

- `volume` 是 MT5 内部格式
- `100 = 0.01 手`
- 如需换算手数，前端自行除以 `10000`

---

## 账户与持仓

需要 Bearer Token。

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/v1/account/info` | GET | 账户信息 |
| `/api/v1/positions` | GET | 当前持仓列表 |
| `/api/v1/orders` | GET | 当前挂单列表 |
| `/api/v1/history/deals` | GET | 历史成交 `?from&to` |
| `/api/v1/history/orders` | GET | 历史订单 `?from&to` |

### `/api/v1/history/deals`

查询参数：

- `from`：Unix 秒
- `to`：Unix 秒

响应格式：

```json
{
  "deals": [
    {
      "deal": 12345,
      "order": 12345,
      "symbol": "EURUSD",
      "type": 0,
      "direction": "BUY",
      "volume": "100",
      "price": "1.15255",
      "profit": "25.50",
      "commission": "0",
      "swap": "0",
      "time": 1774020638,
      "comment": ""
    }
  ]
}
```

字段说明：

- `type`：MT5 的原始 `Action`
- `direction`：后端基于 `Action` 映射出的方向，当前仅对 `0/1` 分别映射为 `BUY/SELL`
- `volume`：MT5 内部格式，`100 = 0.01 手`
- `time`：Unix 秒

当前约定：

- 暂不分页
- 如后续历史数据量明显增大，再补分页能力

---

## 系统

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/v1/health` | GET | 健康检查，返回 `{status, mt5_connected}` 等信息 |

---

## 错误格式

```json
{
  "detail": {
    "error": {
      "code": "MT5_UNAVAILABLE",
      "message": "MT5 服务不可用"
    }
  }
}
```

| HTTP | 含义 |
|---|---|
| 400 | 参数错误 |
| 401 | Token 无效或过期 |
| 502 | MT5 业务错误 |
| 503 | MT5 不可用，建议重试 1 到 2 次，间隔 2 秒 |
