"""
Mock 支付服务 —— 被测系统（SUT）

这是你接下来要测的对象。它模拟了一个最简的支付链路：
    下单 → 支付回调 → 查单

注意：本服务**故意保留了几个真实世界里常见的缺陷**。
你的任务不是看代码找 bug，是**把它当黑盒测出来**，写进缺陷记录表。

启动：
    python app.py
默认监听 http://127.0.0.1:5000

清空数据：
    删除同目录下的 pay.db 后重启
"""
import os
import time
import uuid
import sqlite3

from flask import Flask, request, jsonify

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'pay.db')

# 演示用的"支付网关签名"，真实系统里是 HMAC，这里简化
GATEWAY_SECRET = 'demo-secret-2026'

app = Flask(__name__)


# ---------------------------------------------------------------- 数据层
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS accounts (
        user_id   TEXT PRIMARY KEY,
        balance   REAL NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS orders (
        order_id  TEXT PRIMARY KEY,
        user_id   TEXT NOT NULL,
        amount    REAL NOT NULL,
        status    TEXT NOT NULL,          -- CREATED / PAID / CLOSED
        created_at INTEGER NOT NULL,
        paid_at   INTEGER
    );
    CREATE TABLE IF NOT EXISTS transactions (
        tx_id     TEXT PRIMARY KEY,
        order_id  TEXT NOT NULL,
        amount    REAL NOT NULL,
        created_at INTEGER NOT NULL
    );
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------- 接口
@app.post('/api/pay/create')
def create_order():
    """下单。入参: {user_id, amount}。返回: {order_id, status, amount}"""
    body = request.get_json(silent=True) or {}
    user_id = body.get('user_id')
    amount = body.get('amount')

    if not user_id:
        return jsonify(code=400, msg='user_id 不能为空'), 400
    if amount is None:
        return jsonify(code=400, msg='amount 不能为空'), 400
    if not isinstance(amount, (int, float)):
        return jsonify(code=400, msg='amount 必须是数字'), 400
    if amount <= 0:
        return jsonify(code=400, msg='amount 必须大于 0'), 400

    # 金额精度处理 —— 这里就是第一个坑，你自己测
    amount = round(amount, 2)

    conn = get_db()
    order_id = 'OD' + uuid.uuid4().hex[:16].upper()
    conn.execute(
        'INSERT INTO orders(order_id, user_id, amount, status, created_at) VALUES (?,?,?,?,?)',
        (order_id, user_id, amount, 'CREATED', int(time.time())),
    )
    conn.commit()
    row = conn.execute('SELECT * FROM orders WHERE order_id=?', (order_id,)).fetchone()
    conn.close()

    return jsonify(code=0, data={
        'order_id': row['order_id'],
        'user_id': row['user_id'],
        'amount': row['amount'],
        'status': row['status'],
    })


@app.post('/api/pay/callback')
def pay_callback():
    """支付回调。入参: {order_id, trade_no, sign}。返回: {code, msg}"""
    body = request.get_json(silent=True) or {}
    order_id = body.get('order_id')
    trade_no = body.get('trade_no')
    sign = body.get('sign')

    if not order_id or not trade_no or not sign:
        return jsonify(code=400, msg='参数缺失'), 400

    # 验签（简化版：md5(order_id + trade_no + secret)）
    import hashlib
    expect = hashlib.md5(
        f'{order_id}{trade_no}{GATEWAY_SECRET}'.encode()
    ).hexdigest()
    if sign != expect:
        return jsonify(code=401, msg='验签失败'), 401

    conn = get_db()
    order = conn.execute('SELECT * FROM orders WHERE order_id=?', (order_id,)).fetchone()
    if not order:
        conn.close()
        return jsonify(code=404, msg='订单不存在'), 404

    if order['status'] == 'PAID':
        # 这里就是第二个坑
        pass

    now = int(time.time())
    conn.execute('UPDATE orders SET status=?, paid_at=? WHERE order_id=?',
                 ('PAID', now, order_id))
    conn.execute('INSERT INTO transactions(tx_id, order_id, amount, created_at) VALUES (?,?,?,?)',
                 ('TX' + uuid.uuid4().hex[:16].upper(), order_id, order['amount'], now))
    conn.execute('UPDATE accounts SET balance = balance + ? WHERE user_id = ?',
                 (order['amount'], order['user_id']))
    conn.commit()
    conn.close()

    return jsonify(code=0, msg='ok')


@app.get('/api/order/<order_id>')
def get_order(order_id):
    """查单。返回订单状态、金额、支付时间"""
    conn = get_db()
    row = conn.execute('SELECT * FROM orders WHERE order_id=?', (order_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify(code=404, msg='订单不存在'), 404
    return jsonify(code=0, data=dict(row))


@app.get('/api/account/<user_id>')
def get_account(user_id):
    """查账户余额（用于验证资金一致性）"""
    conn = get_db()
    row = conn.execute('SELECT * FROM accounts WHERE user_id=?', (user_id,)).fetchone()
    if not row:
        # 首次访问自动开户，方便测试
        conn.execute('INSERT INTO accounts(user_id, balance) VALUES (?, 0)', (user_id,))
        conn.commit()
        row = conn.execute('SELECT * FROM accounts WHERE user_id=?', (user_id,)).fetchone()
    conn.close()
    return jsonify(code=0, data=dict(row))


@app.get('/api/transactions/<order_id>')
def get_transactions(order_id):
    """查某订单的所有流水（用于验证幂等：重复回调会产生多条）"""
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM transactions WHERE order_id=? ORDER BY created_at', (order_id,)
    ).fetchall()
    conn.close()
    return jsonify(code=0, data=[dict(r) for r in rows], count=len(rows))


@app.get('/health')
def health():
    return jsonify(status='up', ts=int(time.time()))


if __name__ == '__main__':
    init_db()
    print('Mock 支付服务已启动: http://127.0.0.1:5000')
    print('接口清单：')
    print('  POST /api/pay/create       下单')
    print('  POST /api/pay/callback     支付回调')
    print('  GET  /api/order/<id>       查单')
    print('  GET  /api/account/<uid>    查账户余额')
    print('  GET  /api/transactions/<id> 查订单流水')
    app.run(host='127.0.0.1', port=5000, debug=False)
