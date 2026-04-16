# AstralW Gateway — 错误码参考

> 本文档列出 Gateway 所有可能的错误码和 HTTP 状态码映射。
>
> 更新时间：2026-04-10

---

## 1. 错误响应格式

所有错误响应遵循统一的 JSON 结构：

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

部分错误可能包含额外字段：

```json
{
  "detail": {
    "error": {
      "code": "TRADE_FAILED",
      "message": "交易执行失败: Retcode=10016",
      "mt5_retcode": "10016"
    }
  }
}
```

### 前端解析示例

```kotlin
// Kotlin (Android)
val errorBody = response.errorBody()?.string()
val json = JSONObject(errorBody)
val error = json.getJSONObject("detail").getJSONObject("error")
val code = error.getString("code")
val message = error.getString("message")
```

---

## 2. HTTP 状态码映射

| HTTP 状态码 | 含义 | 场景 |
|-------------|------|------|
| **200** | 成功 | 正常响应 |
| **204** | 无内容 | 登出成功 |
| **400** | 请求参数错误 | 交易方向无效、参数格式错误 |
| **401** | 未认证 | Token 无效、过期、类型错误、用户不存在 |
| **404** | 资源不存在 | 持仓单号不存在 |
| **409** | 冲突 | 邮箱已注册 |
| **502** | MT5 业务错误 | MT5 API 返回非零 retcode |
| **503** | MT5 不可用 | MT5 连接断开或无法建立 |

---

## 3. 错误码枚举

### 认证相关

| error.code | HTTP | 触发位置 | 说明 | 前端处理建议 |
|------------|------|---------|------|------------|
| `EMAIL_EXISTS` | 409 | `auth_service.py` | 注册时邮箱已被使用 | 提示用户更换邮箱或去登录 |
| `AUTH_FAILED` | 401 | `auth_service.py` | 登录时邮箱未注册 | 提示"邮箱或密码错误" |
| `AUTH_INVALID_PASSWORD` | 401 | `auth_service.py` | 登录时 MT5 密码校验失败 | 提示"邮箱或密码错误" |
| `TOKEN_INVALID` | 401 | `jwt_service.py` | access_token 无效或已过期 | 尝试用 refresh_token 刷新 |
| `TOKEN_EXPIRED` | 401 | `auth.py (router)` | refresh_token 已失效 | 跳转登录页 |
| `USER_NOT_FOUND` | 401 | `jwt_service.py` | Token 中的用户在本地不存在 | 跳转登录页 |

### MT5 连接相关

| error.code | HTTP | 触发位置 | 说明 | 前端处理建议 |
|------------|------|---------|------|------------|
| `MT5_UNAVAILABLE` | 503 | 全局异常处理 / 多处 | MT5 连接断开或无法建立 | 1-2 次自动重试（间隔 2s），仍失败则提示用户 |
| `MT5_API_ERROR` | 502 | 全局异常处理 | MT5 API 返回非零 retcode | 显示错误信息 |
| `MT5_USER_ADD_FAILED` | 502 | `auth_service.py` | 注册时 MT5 创建用户失败 | 提示注册失败，稍后重试 |

### 交易相关

| error.code | HTTP | 触发位置 | 说明 | 前端处理建议 |
|------------|------|---------|------|------------|
| `INVALID_DIRECTION` | 400 | `trade.py` | direction 不是 BUY 或 SELL | 检查参数 |
| `QUOTE_UNAVAILABLE` | 502 | `trade.py` | 无法获取品种当前报价 | 提示行情不可用，稍后重试 |
| `TRADE_SUBMIT_FAILED` | 502 | `trade.py` | 提交交易请求后未获取到 request_id | 提示交易提交失败 |
| `TRADE_FAILED` | 502 | `trade.py` | 交易执行返回非成功 retcode | 显示 MT5 错误信息 |
| `POSITION_NOT_FOUND` | 404 | `trade.py` | 平仓时指定的持仓单号不存在 | 刷新持仓列表后重试 |

---

## 4. MT5 交易 retcode 映射

交易接口（`/trade/open`、`/trade/close`、`/trade/modify`）的响应中 `retcode` 字段含义：

| retcode | 含义 | 说明 | 前端处理 |
|---------|------|------|---------|
| `"10009"` | **成交成功** (Done) | 交易已完全执行 | ✅ 显示成交价和成交量 |
| `"10008"` | **挂单成功** (Placed) | 挂单已放置到市场上 | ✅ 显示挂单信息 |
| `"10006"` | **处理中** (Requote 或排队) | Gateway 内部轮询时遇到 | 继续等待（Gateway 已处理） |
| `"0"` | **已提交未确认** | 请求已提交，但 5 秒内未获得最终结果 | 轮询持仓或历史确认 |
| 其他 | **失败** | 余额不足、品种不可用等 | 显示错误信息 |

### 前端 retcode 处理示例

```kotlin
when (result.retcode) {
    "10009", "10008" -> {
        // 成交成功 / 挂单成功
        showSuccess("${result.message} @ ${result.price}")
    }
    "0" -> {
        // 已提交但未即时确认，可能需要轮询持仓列表
        showPending("交易请求已提交，请检查持仓")
    }
    else -> {
        // 失败
        showError(result.message)
    }
}
```

---

## 5. Volume 单位换算

交易接口中 `volume` 是 MT5 内部格式，需要换算：

| 前端手数 | MT5 Volume | MT5 VolumeExt |
|---------|-----------|---------------|
| 0.01 | 100 | 1,000,000 |
| 0.1 | 1,000 | 10,000,000 |
| 1.0 | 10,000 | 100,000,000 |

**公式**：`手数 = Volume ÷ 10000`

---

## 参考

- [share/api_spec.md](share/api_spec.md) — 接口契约详情
- [ARCHITECTURE.md](ARCHITECTURE.md) — 系统架构概览
