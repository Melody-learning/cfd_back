"""直接调用 MT5 /api/common/get 看返回原始数据"""
import httpx
import json
import time
import ssl

# 直接连 MT5 太复杂（需要认证），我们通过 connector 的日志或修改代码打印
# 先用一个临时脚本，通过修改 connector 加日志

# 另一个办法: 从 tick datetime 推算 offset
utc_now = int(time.time())
tick_datetime = 1775821809  # 上一个测试的值
offset = tick_datetime - utc_now
print(f"UTC now: {utc_now}")
print(f"Tick datetime: {tick_datetime}")
print(f"Offset: {offset}s ({offset/3600:.1f}h)")
print(f"Expected offset for UTC+8: 28800s (8.0h)")
