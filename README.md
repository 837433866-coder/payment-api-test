# 支付接口测试项目

对一套 mock 支付服务做接口测试，覆盖**功能、边界、幂等、数据一致性**四类场景。
目标不是"测出功能正常"，而是**验证资金在异常路径下是否一致**。

## 为什么做这个项目

金融系统里最贵的 bug 不是"功能不能用"，是"账记错了"。
支付回调会因网络抖动重复推送，如果接口不幂等，用户付一次钱会被扣多次——
这类问题靠功能测试发现不了，必须专门设计异常用例。

本项目针对这个场景构建了被测系统并完成测试。

## 项目结构

```
payment-api-test/
├── mock_server/
│   └── app.py              # 被测系统（mock 支付服务，含故意保留的缺陷）
├── tests/
│   ├── conftest.py         # pytest fixture：base_url、session、测试数据
│   └── test_pay.py         # 接口自动化用例
├── data/
│   ├── test_cases.md       # 测试用例表（28 条）
│   └── bug_report.md       # 缺陷记录（3 个真实缺陷）
├── scripts/
│   └── verify.sql          # 数据一致性验证 SQL
├── requirements.txt
└── README.md
```

## 被测系统

最简支付链路：**下单 → 支付回调 → 查单**

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/pay/create` | POST | 下单，入参 user_id + amount |
| `/api/pay/callback` | POST | 支付回调，入参 order_id + trade_no + sign |
| `/api/order/<id>` | GET | 查单 |
| `/api/account/<uid>` | GET | 查账户余额 |
| `/api/transactions/<id>` | GET | 查订单流水 |

数据落在 SQLite（`mock_server/pay.db`），便于用 SQL 做一致性验证。

## 怎么跑

```bash
pip install -r requirements.txt

# 1. 启动被测服务
cd mock_server && python app.py
# 服务在 http://127.0.0.1:5000

# 2. 另开一个终端，跑自动化测试
pytest tests/ -v

# 3. 生成 HTML 报告
pytest tests/ --html=report.html --self-contained-html
```

## 实测结论（2026-11-26 真实执行）

```bash
$ pytest tests/ -v --html=report.html --self-contained-html
collected 30 items
23 passed, 7 xfailed in 0.69s
```

**30 条自动化用例全部执行，23 条通过，7 条 XFAIL（已确认缺陷，断言"缺陷存在"），零意外失败。**
XFAIL 不是跳过：用例真实发出请求、真实断言，缺陷存在才标 XFAIL；若缺陷被修复会变 XPASS 提醒更新用例。

| 分类 | 用例数 | 通过 | XFAIL（缺陷） |
|---|---|---|---|
| 下单（功能+边界+类型） | 12 | 10 | 2（BUG-003 / BUG-004） |
| 支付回调（幂等+验签+并发） | 9 | 5 | 4（BUG-001/002） |
| 查询接口 | 4 | 4 | 0 |
| 数据一致性（多表 JOIN） | 5 | 4 | 1（BUG-001/003） |
| **合计** | **30** | **23** | **7** |

**结论：被测系统在资金一致性与幂等性上存在 4 个真实缺陷，不具备上线条件。**

## 发现的缺陷

| 编号 | 标题 | 级别 | 发现方式 |
|---|---|---|---|
| BUG-001 | 支付回调重复推送导致重复记账且资金未实际入账 | **P0 致命** | 手工探索 + 自动化复现 |
| BUG-002 | 支付回调未做幂等，重复请求全部返回成功 | P1 严重 | 手工探索 + 自动化复现 |
| BUG-003 | 下单金额精度丢失，0.001 元订单被创建为 0 元订单 | P2 一般 | 手工探索 + 自动化复现 |
| BUG-004 | 布尔金额绕过类型校验，`amount=True` 被接受 | P2 一般 | **参数化自动化新发现** |

详见 [data/bug_report.md](data/bug_report.md)。完整 HTML 报告见 [report.html](report.html)。

## SQL 一致性验证实测

执行 `scripts/verify.sql` 中的多表 JOIN 查询，在被测库上命中：

| 检查项 | SQL 手法 | 命中 |
|---|---|---|
| PAID 订单流水异常 | `orders LEFT JOIN transactions ... HAVING COUNT<>1` | 3 个订单（流水 2/3/10 条） |
| 账实不符 | `orders JOIN transactions` 分组聚合 + 子查询比余额 | 6 个用户 |
| 孤儿流水 | `transactions LEFT JOIN orders WHERE o.order_id IS NULL` | 0（正常） |
| 0 元订单 | `WHERE amount<=0` | 1 条 |
| 分组聚合 | `GROUP BY status` + COUNT/SUM/AVG | CREATED 18 单 / PAID 6 单 |

### BUG-001 的实测数据

```
重复回调 3 次后：
  流水条数: 3 条 × 100.5 = 301.5 元
  账户余额: 0.0 元
  订单状态: PAID
```

流水与余额完全对不上，是典型的**账实不符**。根因有两层：

1. 回调入口没有幂等判断，订单已 PAID 仍继续处理
2. `UPDATE accounts ... WHERE user_id=?` 在用户记录不存在时**静默更新 0 行**，没校验 `rowcount`

## 技术点

- 接口测试：requests + pytest，fixture 管理 session 与测试数据
- 数据驱动：`pytest.mark.parametrize` 覆盖金额边界
- 数据一致性：用 SQL 交叉验证订单表 / 流水表 / 账户表
- 幂等验证：同一 trade_no 重复提交，断言流水条数不增长
- 缺陷管理：按 P0/P1/P2 分级，附复现步骤、影响分析与修复建议

## 说明

被测系统为本人编写的 mock 服务，用于练习金融场景下的异常路径测试。
不含任何真实支付系统或第三方数据。
