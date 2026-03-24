# AstralW Gateway — 前端接口适配指南

> 更新时间：2026-03-23
>
> Swagger 文档：`http://<server>:8000/docs`（每次重启自动同步）

---

## 1. 交易接口（v5 重大变更）⚠️

**涉及接口**：`POST /api/v1/trade/open`、`POST /api/v1/trade/close`、`PUT /api/v1/trade/modify`

### 变更说明

交易接口现在**同步返回成交结果**，包含真实成交价格和订单号。

### 响应格式

**成交成功**（retcode=`10009`）：
```json
{
  "order": 0,
  "deal": 0,
  "price": "1.15255000",
  "volume": "100",
  "retcode": "10009",
  "message": "成交成功"
}
```

**已提交但未即时确认**（retcode=`0`）：
```json
{
  "order": 0,
  "deal": 0,
  "price": "",
  "volume": "0.01",
  "retcode": "0",
  "message": "交易请求已提交，等待执行 (request_id=8)"
}
```

### 前端适配要点

| 字段 | 说明 |
|---|---|
| `retcode` | **`"10009"`** = 成交成功（Done）；**`"0"`** = 已提交但无法确认结果 |
| `price` | 成交价格，字符串格式。retcode=10009 时有值 |
| `volume` | MT5 内部格式（`100` = 0.01 手，`10000` = 1 手）。需要 `÷ 10000` 转回手数 |
| `order` / `deal` | 当前可能为 0（MT5 未返回），后续版本会完善 |

> ⚠️ **关键变更**：`retcode` 不再是 `"0"` 代表成功，改为 **`"10009"` = 成交成功**。前端应适配：
> ```kotlin
> when (result.retcode) {
>     "10009", "10008" -> // 成交成功 / 挂单已挂出
>     "0"              -> // 已提交，轮询持仓确认
>     else             -> // 失败
> }
> ```

### 响应时间

| 场景 | 耗时 |
|---|---|
| 成交成功 | ~900ms |
| 超时无确认 | ~15s |

---

## 2. K 线接口参数变更

**接口**：`GET /api/v1/chart/candles`

`from`、`to` 改为可选，新增 `count` 参数。

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `symbol` | string | ✅ | - | 品种名称 |
| `timeframe` | string | 否 | M1 | M1/M5/M15/M30/H1/H4/D1 |
| `from` | int | 否 | 自动计算 | 起始时间 Unix 秒 |
| `to` | int | 否 | 当前时间 | 结束时间 Unix 秒 |
| `count` | int | 否 | 100 | 返回蜡烛数量（不指定 from/to 时生效） |

**推荐用法**：
```
GET /api/v1/chart/candles?symbol=EURUSD&timeframe=H1&count=50
```

---

## 3. tick_stat 字段变更

**接口**：`GET /api/v1/market/tick_stat`

新增字段（不破坏现有字段）：

```diff
 {
   "symbol": "EURUSD",
+  "bid": "1.15700",
+  "ask": "1.15703",
   "last": "0",
   "high": "1.15800",
   "low": "1.15500",
   "volume": "0",
+  "price_change": "0.15",
+  "datetime": 1774020638
 }
```

---

## 4. HTTP 错误码

| HTTP 状态码 | 含义 | error.code |
|---|---|---|
| 200 | 成功 | - |
| 400 | 请求参数错误 | `INVALID_DIRECTION` 等 |
| 401 | 未认证 / Token 过期 | - |
| 502 | MT5 返回业务错误 | `MT5_API_ERROR` / `TRADE_FAILED` |
| 503 | MT5 服务不可用 | `MT5_UNAVAILABLE` |
| 504 | 交易执行超时 | `TRADE_TIMEOUT`（极少触发） |

错误响应格式：
```json
{
  "detail": {
    "error": {
      "code": "MT5_UNAVAILABLE",
      "message": "MT5 服务器不可用"
    }
  }
}
```

---

## 5. Volume 单位换算

MT5 内部 Volume 和前端手数的换算：

| 前端手数 | MT5 Volume | MT5 VolumeExt |
|---|---|---|
| 0.01 | 100 | 1,000,000 |
| 0.1 | 1,000 | 10,000,000 |
| 1.0 | 10,000 | 100,000,000 |

**公式**：`手数 = Volume ÷ 10000` 或 `手数 = VolumeExt ÷ 100000000`

> 返回的 `volume` 字段是 MT5 内部格式，前端显示时需要换算。

---

## 6. 连接稳定性提升

v5 修复了之前频繁出现的 503 错误。如果仍偶尔出现 503：
- 属于 MT5 连接重建（~5s 自动恢复）
- 前端建议对 503 做 **1-2 次自动重试**（间隔 2s）
