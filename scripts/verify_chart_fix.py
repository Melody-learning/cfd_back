"""验证 K 线时间修正是否生效"""
import httpx
import time

BASE = "http://127.0.0.1:8000"

# 登录
r = httpx.post(f"{BASE}/api/v1/auth/login", json={"email": "cc@gmail.com", "password": "Chj7921041*mt5"})
data = r.json()
if "access_token" not in data:
    print("Login failed:", data)
    exit()
token = data["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# 获取 M1 蜡烛
r2 = httpx.get(f"{BASE}/api/v1/chart/candles?symbol=EURUSD&timeframe=M1&count=5", headers=headers, timeout=10)
candles = r2.json().get("candles", [])

# 获取实时报价
r3 = httpx.get(f"{BASE}/api/v1/market/quotes?symbols=EURUSD", headers=headers, timeout=10)
quotes = r3.json().get("quotes", [])

now_utc = int(time.time())
print(f"UTC now: {now_utc}")
print(f"--- Last 3 candles ---")
for c in candles[-3:]:
    print(f"  ts={c['timestamp']}  C={c['close']}")

if candles and quotes:
    last = candles[-1]
    q = quotes[0]
    bid = float(q["bid"])
    close = float(last["close"])
    pips = abs(bid - close) * 100000
    ts_diff = q["datetime"] - last["timestamp"]
    print(f"--- Comparison ---")
    print(f"  Candle close: {last['close']} (ts={last['timestamp']})")
    print(f"  Quote bid:    {q['bid']} (datetime={q['datetime']})")
    print(f"  Price diff:   {pips:.1f} pips")
    print(f"  Time diff:    {ts_diff}s ({ts_diff/3600:.1f}h)")
    if pips < 50 and abs(ts_diff) < 120:
        print("  ✅ PASS: candle close is close to current price, time aligned")
    elif abs(ts_diff) > 3600:
        print(f"  ❌ FAIL: {ts_diff/3600:.1f}h time gap - likely timezone offset issue")
    else:
        print(f"  ⚠️  Price diff {pips:.0f} pips, time diff {ts_diff}s")
