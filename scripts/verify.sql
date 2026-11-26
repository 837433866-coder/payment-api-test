-- 数据一致性验证 SQL（对应 data/test_cases.md 的 TC-25 ~ TC-28）
-- 用法：sqlite3 mock_server/pay.db < scripts/verify.sql
-- 所有查询预期返回 0 行；有返回即为缺陷。

-- TC-25 PAID 订单必须有且仅有 1 条流水
SELECT 'TC-25 异常订单' AS check_name, o.order_id, o.status, COUNT(t.tx_id) AS tx_count
FROM orders o
LEFT JOIN transactions t ON o.order_id = t.order_id
WHERE o.status = 'PAID'
GROUP BY o.order_id
HAVING COUNT(t.tx_id) <> 1;

-- TC-26 流水合计与账户余额不一致（按用户聚合，多表 JOIN）
SELECT 'TC-26 账实不符' AS check_name,
       o.user_id,
       ROUND(SUM(t.amount), 2) AS tx_total,
       (SELECT balance FROM accounts a WHERE a.user_id = o.user_id) AS balance
FROM orders o
JOIN transactions t ON o.order_id = t.order_id
GROUP BY o.user_id
HAVING ROUND(SUM(t.amount), 2) <> COALESCE(
    (SELECT balance FROM accounts a WHERE a.user_id = o.user_id), 0);

-- TC-27 孤儿流水：流水找不到对应订单
SELECT 'TC-27 孤儿流水' AS check_name, t.*
FROM transactions t
LEFT JOIN orders o ON t.order_id = o.order_id
WHERE o.order_id IS NULL;

-- TC-28 存在 0 元或负金额订单
SELECT 'TC-28 非法金额订单' AS check_name, order_id, amount
FROM orders
WHERE amount <= 0;

-- 附加：分组聚合示例（面试被问"join 过什么表"时的答案）
SELECT '统计' AS check_name,
       o.status,
       COUNT(*) AS order_count,
       ROUND(SUM(o.amount), 2) AS total_amount,
       ROUND(AVG(o.amount), 2) AS avg_amount
FROM orders o
GROUP BY o.status;
