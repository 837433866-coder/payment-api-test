# 测试用例表

> 目标：覆盖支付链路的正常流程 + 异常流程 + 边界 + 一致性
> 状态：`PASS` 通过 / `FAIL` 失败（对应缺陷编号）/ `待测` 未执行
>
> **你的作业：把「待测」的部分补完，至少补到 25 条。**

## 一、下单接口 POST /api/pay/create

| # | 场景 | 前置条件 | 输入 | 预期结果 | 优先级 | 状态 |
|---|---|---|---|---|---|---|
| TC-01 | 正常下单 | 无 | user_id=U001, amount=100.5 | 返回 200，order_id 非空，status=CREATED，amount=100.5 | P0 | PASS |
| TC-02 | 缺 user_id | 无 | amount=100 | 400，提示 user_id 不能为空 | P1 | 待测 |
| TC-03 | 缺 amount | 无 | user_id=U001 | 400，提示 amount 不能为空 | P1 | 待测 |
| TC-04 | amount 为字符串 | 无 | amount="100" | 400，提示必须是数字 | P2 | 待测 |
| TC-05 | amount 为 0 | 无 | amount=0 | 400，必须大于 0 | P1 | 待测 |
| TC-06 | amount 为负数 | 无 | amount=-5 | 400，必须大于 0 | P1 | PASS |
| TC-07 | amount 小于最小单位 | 无 | amount=0.001 | 400 拒绝，或明确按分处理 | P1 | **FAIL → BUG-003** |
| TC-08 | amount 超大 | 无 | amount=999999999 | 400 或按业务上限拒绝 | P2 | 待测 |
| TC-09 | amount 小数位超 2 位 | 无 | amount=10.999 | 拒绝或按规则四舍五入，需明确 | P2 | 待测 |
| TC-10 | amount 为 null | 无 | amount=null | 400 | P2 | 待测 |
| TC-11 | 同一用户并发下 10 单 | 无 | 10 个并发请求 | 10 个订单全部创建成功，order_id 互不重复 | P1 | 待测 |

## 二、支付回调 POST /api/pay/callback

| # | 场景 | 前置条件 | 输入 | 预期结果 | 优先级 | 状态 |
|---|---|---|---|---|---|---|
| TC-12 | 正常回调 | 有 CREATED 订单 | 正确 sign | 200，订单变 PAID，流水 +1，余额 +amount | P0 | PASS（但余额异常，见 BUG-001） |
| TC-13 | 重复回调 3 次 | 同上 | 相同参数 ×3 | 订单 PAID，流水仅 1 条，余额仅 +1 次 | P0 | **FAIL → BUG-001/002** |
| TC-14 | sign 错误 | 有订单 | 错 sign | 401 验签失败，订单状态不变 | P0 | 待测 |
| TC-15 | sign 缺失 | 有订单 | 无 sign | 400 | P1 | 待测 |
| TC-16 | order_id 不存在 | 无 | 随机 order_id | 404 订单不存在 | P1 | 待测 |
| TC-17 | 回调已 PAID 的订单（不同 trade_no） | 订单已支付 | 新 trade_no + 正确 sign | 应拒绝或幂等返回，不得重复记账 | P0 | 待测 |
| TC-18 | 回调 CLOSED 状态的订单 | 订单已关闭 | 正确 sign | 应拒绝，不得改状态 | P1 | 待测 |
| TC-19 | trade_no 超长 | 有订单 | 1000 字符的 trade_no | 应拒绝或截断告警 | P2 | 待测 |
| TC-20 | 并发回调同一订单 10 次 | 有 CREATED 订单 | 10 个并发请求 | 只记账 1 次 | P0 | 待测 |

## 三、查询接口

| # | 场景 | 前置条件 | 输入 | 预期结果 | 优先级 | 状态 |
|---|---|---|---|---|---|---|
| TC-21 | 查存在的订单 | 有订单 | 正确 order_id | 200，字段完整 | P1 | PASS |
| TC-22 | 查不存在的订单 | 无 | 随机 order_id | 404 | P1 | 待测 |
| TC-23 | 查账户余额（新用户） | 用户不存在 | 新 user_id | 返回余额 0 并自动开户 | P2 | PASS |
| TC-24 | 查订单流水 | 有已支付订单 | 正确 order_id | 返回该订单所有流水 | P1 | PASS |

## 四、数据一致性（SQL 验证）

| # | 场景 | 验证 SQL | 预期 | 优先级 | 状态 |
|---|---|---|---|---|---|
| TC-25 | 订单状态与流水一致性 | `SELECT o.status, COUNT(t.tx_id) FROM orders o LEFT JOIN transactions t ON o.order_id=t.order_id GROUP BY o.order_id` | PAID 订单必须有且仅有 1 条流水 | P0 | 待测 |
| TC-26 | 流水总额等于余额 | `SELECT (SELECT SUM(amount) FROM transactions WHERE order_id='X'), (SELECT balance FROM accounts WHERE user_id='U001')` | 两者相等 | P0 | **FAIL → BUG-001** |
| TC-27 | 无孤儿流水 | `SELECT * FROM transactions t LEFT JOIN orders o ON t.order_id=o.order_id WHERE o.order_id IS NULL` | 结果为空 | P1 | 待测 |
| TC-28 | 订单金额一致性 | `SELECT order_id, amount FROM orders WHERE amount <= 0` | 结果为空 | P1 | **FAIL → BUG-003** |

---

## 待补充方向（补到 25 条以上时从这里挑）

- 幂等：相同 trade_no 不同 order_id
- 超时：回调接口响应超过 3 秒（用 JMeter 或 sleep 模拟）
- 编码：user_id 含中文/emoji/SQL 注入串
- 越权：A 用户可以查 B 用户的订单吗
- 限流：连续 100 次下单是否被封
- 并发：10 个线程同时回调同一订单，看是否重复记账

## 用例统计

| 分类 | 总数 | 已执行 | 通过 | 失败 | 待测 |
|---|---|---|---|---|---|
| 下单 | 11 | 3 | 2 | 1 | 8 |
| 回调 | 9 | 2 | 1 | 1 | 7 |
| 查询 | 4 | 3 | 3 | 0 | 1 |
| 一致性 | 4 | 2 | 0 | 2 | 2 |
| **合计** | **28** | **10** | **6** | **4** | **18** |

当前用例通过率：**60%**（6/10）
核心链路（P0）通过率：**40%**（2/5）→ **不具备上线条件**
