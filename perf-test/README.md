# 支付接口性能测试（JMeter 梯度压测）

对 mock 支付服务的下单接口 `/api/pay/create` 做梯度并发压测，定位性能拐点与瓶颈代码。

这是接口自动化的延伸：`pytest` 验证功能对不对，JMeter 验证高并发下还撑不撑得住。

## 环境与复现

- 被测服务：`mock_server/app.py`（Flask + SQLite），`http://127.0.0.1:5000`
- 压测工具：JMeter 5.6.3（免安装，解压即用，JDK 21）
- 场景：50 / 100 / 200 并发，ramp-up 10 秒，每线程 20 轮
- 断言：HTTP 200 + 响应体含 `CREATED`

```bash
# 1. 启动被测服务
cd mock_server && python app.py

# 2. 梯度压测（JMETER_BIN 换成你的 jmeter/bin 路径）
cd perf-test
bash run_load_test.sh "D:/WorkBuddyOutput/_tools/apache-jmeter-5.6.3/bin"
```

`jmx` 里的线程数用 `${__P(threads,50)}` 参数化，命令行 `-Jthreads=200` 可覆盖，一套脚本跑三个梯度。

## 实测结果

| 并发 | 请求数 | 错误率 | 平均响应 | P95 | P99 | 最大 |
|---|---|---|---|---|---|---|
| 50 | 1000 | 0% | 5 ms | 6 ms | 7 ms | 26 ms |
| 100 | 2000 | 0% | 57 ms | 144 ms | 1467 ms | 5651 ms |
| 200 | 4000 | **5.47%** | 475 ms | 5995 ms | 6161 ms | 6272 ms |

完整 HTML 报告：`results/report_50/`、`report_100/`、`report_200/` 的 `index.html`。

## 结论与归因

**性能拐点在 100~200 并发之间。**

- 50 并发：服务轻松，P99 仅 7ms。
- 100 并发：错误率仍为 0，但 P99 飙到 1467ms、最大 5651ms——说明请求开始排队，延迟长尾已经出现。
- 200 并发：错误率 5.47%（218 个 500 + 1 个 BindException），P95 超过 5 秒。

**根因定位（不是猜，是看代码）：**

下单接口 `create_order()` 每次请求都 `get_db()` 新建 SQLite 连接，`INSERT` 后 `commit()`。而 `get_db()` 用 `sqlite3.connect(DB_PATH)` 未设置 `timeout`，默认 5 秒。200 并发同时写库时，后到的请求拿不到写锁，等待超过 5 秒抛 `database is locked`，Flask 返回 500。

 BindException 来自压测机自身——200 并发短连接耗尽了本地临时端口，属于压测客户端侧现象，不是服务端缺陷，报告里如实区分。

**修复建议（面试时可展开）：**

1. 连接加 `timeout=30`，缓解锁等待；
2. 开启 WAL 模式 `PRAGMA journal_mode=WAL`，读写不互斥；
3. 用连接池复用连接，而不是每次新建；
4. 生产环境换 MySQL 等支持并发写的数据库。

## 面试怎么讲

> "我用 JMeter 对支付下单接口做了 50/100/200 梯度压测，发现 100 并发时错误率还是 0 但 P99 已经到 1.4 秒，200 并发错误率 5.47%、P95 超过 5 秒。我回到代码定位到下单接口每次新建 SQLite 连接、没设 timeout，高并发写锁等待超时返回 500，属于数据库连接管理问题。我给了加 timeout、开 WAL、上连接池、换 MySQL 四条修复建议。压测机还出现了一个 BindException，那是本地临时端口耗尽，我把它和服务端缺陷区分开了。"

这段话覆盖 JD 高频词：**JMeter、并发、响应时间 P95/P99、错误率、瓶颈定位、性能调优**。
