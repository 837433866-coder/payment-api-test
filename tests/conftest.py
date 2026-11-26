"""pytest fixture：服务地址、会话、测试数据、数据库直连校验。"""
import os
import sqlite3
import uuid

import pytest
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "mock_server", "pay.db")


@pytest.fixture(scope="session")
def base_url():
    return os.environ.get("BASE_URL", "http://127.0.0.1:5000")


@pytest.fixture
def api(base_url):
    """统一请求入口：带超时、自动拼接 base_url。"""
    class API:
        def __init__(self, base):
            self.base = base
            self.s = requests.Session()

        def post(self, path, json=None, timeout=5):
            return self.s.post(self.base + path, json=json, timeout=timeout)

        def get(self, path, timeout=5):
            return self.s.get(self.base + path, timeout=timeout)

    return API(base_url)


@pytest.fixture
def new_user_id():
    """每个用例独立用户，避免相互污染。"""
    return "U_" + uuid.uuid4().hex[:8]


@pytest.fixture
def create_order(api, new_user_id):
    """创建一个 CREATED 订单，返回 (order_id, user_id, amount)。"""
    def _create(amount=100.5, user_id=None):
        uid = user_id or new_user_id
        r = api.post("/api/pay/create", json={"user_id": uid, "amount": amount})
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        return data["order_id"], uid, data["amount"]
    return _create


@pytest.fixture
def db():
    """直连 SQLite，做数据一致性校验。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def make_sign(order_id, trade_no, secret="demo-secret-2026"):
    """按被测服务的验签规则生成 sign（黑盒测试里按接口文档构造）。"""
    import hashlib
    return hashlib.md5(f"{order_id}{trade_no}{secret}".encode()).hexdigest()
