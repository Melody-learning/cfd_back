# AstralW Gateway - 接口变更记录

> 维护方：后端
> 最后更新：2026-03-23

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
