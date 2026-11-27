#!/usr/bin/env python3
"""生成可复现的生产风格支付服务日志（固定随机种子，每次生成内容一致）。"""
import random
from pathlib import Path

random.seed(20261126)
OUT = Path(__file__).resolve().parents[1] / "logs" / "payment-service.log"
OUT.parent.mkdir(parents=True, exist_ok=True)

lines = []


def log(ts, level, svc, trace, msg):
    lines.append(f"{ts} {level:<5} [{svc}] [{trace}] {msg}")


def trace():
    return "req-" + "".join(random.choice("0123456789abcdef") for _ in range(8))


# ---------- 正常流量模板 ----------
USERS = [1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008, 1009, 1010]
AMOUNTS = [10.5, 25.0, 88.0, 100.5, 199.9, 256.0, 320.0, 520.0]
ENDPOINTS = ["/api/pay/create", "/api/pay/callback", "/api/order/query", "/api/order/refund"]


def normal_traffic(day, hour, count):
    for _ in range(count):
        minute = random.randint(0, 59)
        second = random.randint(0, 59)
        ms = random.randint(0, 999)
        ts = f"2026-11-{day:02d} {hour:02d}:{minute:02d}:{second:02d},{ms:03d}"
        t = trace()
        uid = random.choice(USERS)
        amount = random.choice(AMOUNTS)
        cost = random.randint(20, 180)
        ep = random.choice(ENDPOINTS)
        order = f"ORD202611{day:02d}{random.randint(100, 999)}"
        level = "INFO "
        log(ts, level, "payment-api", t, f"{ep} order_id={order} user_id={uid} amount={amount} cost={cost}ms status=200")


# ---------- 三天流量 ----------
for day in (23, 24):
    for hour in (9, 10, 11, 14, 15, 16):
        normal_traffic(day, hour, 12)

# 11-25 上午正常流量
for hour in (9, 10):
    normal_traffic(25, hour, 10)

# ---------- BUG-001：重复回调未拦截，重复记账 ----------
t1 = "req-7f3a9c12"
t2 = "req-b81d4e03"
t3 = "req-c92f1a77"
log("2026-11-25 10:12:03,123", "INFO ", "payment-api", t1, "POST /api/pay/create order_id=ORD20261125001 user_id=1001 amount=100.5 cost=45ms status=200")
log("2026-11-25 10:12:04,456", "INFO ", "callback-worker", t1, "callback received order_id=ORD20261125001 trade_no=TXN20261125001 status=PAID")
log("2026-11-25 10:12:04,501", "INFO ", "account-svc", t1, "insert transaction order_id=ORD20261125001 amount=100.5 balance_after=100.5")
log("2026-11-25 10:12:07,891", "WARN ", "callback-worker", t2, "duplicate callback not blocked order_id=ORD20261125001 trade_no=TXN20261125001")
log("2026-11-25 10:12:07,932", "INFO ", "account-svc", t2, "insert transaction order_id=ORD20261125001 amount=100.5 balance_after=201.0")
log("2026-11-25 10:12:09,214", "WARN ", "callback-worker", t3, "duplicate callback not blocked order_id=ORD20261125001 trade_no=TXN20261125001")
log("2026-11-25 10:12:09,256", "INFO ", "account-svc", t3, "insert transaction order_id=ORD20261125001 amount=100.5 balance_after=301.5")

# ---------- BUG-002：余额更新 rowcount=0 静默失败 ----------
t4 = "req-2a7e91f0"
log("2026-11-25 11:03:12,341", "INFO ", "payment-api", t4, "POST /api/pay/create order_id=ORD20261125044 user_id=1002 amount=88.0 cost=38ms status=200")
log("2026-11-25 11:03:14,002", "INFO ", "callback-worker", t4, "callback received order_id=ORD20261125044 trade_no=TXN20261125044 status=PAID")
log("2026-11-25 11:03:14,088", "INFO ", "account-svc", t4, "insert transaction order_id=ORD20261125044 amount=88.0")
log("2026-11-25 11:03:14,091", "WARN ", "account-svc", t4, "update account rowcount=0 user_id=1002 no exception raised balance_still=0.0")

# ---------- BUG-003：金额精度丢失 ----------
t5 = "req-6d4b20aa"
log("2026-11-25 14:22:31,550", "INFO ", "payment-api", t5, "POST /api/pay/create order_id=ORD20261125132 user_id=1005 amount=0.001 cost=29ms status=200")
log("2026-11-25 14:22:31,571", "WARN ", "payment-api", t5, "amount rounded to 0.0 order_id=ORD20261125132")

# ---------- BUG-004：bool 金额绕过类型校验 ----------
t6 = "req-9e1c33bd"
log("2026-11-25 15:41:09,780", "INFO ", "payment-api", t6, "POST /api/pay/create order_id=ORD20261125188 user_id=1008 amount=True cost=31ms status=200")
log("2026-11-25 15:41:09,812", "WARN ", "payment-api", t6, "type check bypassed bool is int subclass amount=True")

# ---------- 慢请求 ----------
for ts, t, ep, cost, status in [
    ("2026-11-25 16:02:11,201", "req-3f8a102c", "/api/pay/create", 1842, 200),
    ("2026-11-25 16:05:22,610", "req-5b2e7741", "/api/order/query", 1320, 200),
    ("2026-11-25 16:08:03,447", "req-7c1d9950", "/api/pay/callback", 2105, 500),
    ("2026-11-25 16:11:48,932", "req-8d3f001a", "/api/pay/create", 967, 200),
]:
    log(ts, "WARN ", "gateway", t, f"slow request POST {ep} cost={cost}ms status={status}")

# ---------- 5xx 与多行堆栈（测 grep -A/-B） ----------
t7 = "req-a1b2c3d4"
log("2026-11-25 16:15:44,667", "ERROR", "payment-api", t7, "unhandled exception POST /api/pay/callback cost=1203ms status=500")
log("2026-11-25 16:15:44,668", "ERROR", "payment-api", t7, "Traceback (most recent call last):")
log("2026-11-25 16:15:44,669", "ERROR", "payment-api", t7, '  File "app.py", line 88, in callback')
log("2026-11-25 16:15:44,670", "ERROR", "payment-api", t7, "    balance = calc_balance(order_id)")
log("2026-11-25 16:15:44,671", "ERROR", "payment-api", t7, '  File "app.py", line 42, in calc_balance')
log("2026-11-25 16:15:44,672", "ERROR", "payment-api", t7, "    return total / count")
log("2026-11-25 16:15:44,673", "ERROR", "payment-api", t7, "ZeroDivisionError: division by zero")

# ---------- 其他噪音 ----------
log("2026-11-25 16:20:01,110", "WARN ", "gateway", "req-11223344", "rate limit hit client_ip=10.0.0.7 path=/api/pay/create")
log("2026-11-25 16:21:15,884", "ERROR", "callback-worker", "req-55667788", "third-party timeout trade_no=TXN20261125999 retry=1/3")
log("2026-11-25 16:22:09,003", "INFO ", "payment-api", "req-99aabbcc", "GET /health status=200 cost=2ms")
log("2026-11-25 16:23:41,220", "INFO ", "payment-api", "req-ddeeff00", "GET /health status=200 cost=3ms")

# 按时间排序（手工插入的块打乱了顺序）
lines.sort(key=lambda x: x[:23])

OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"生成 {len(lines)} 行 -> {OUT}")
