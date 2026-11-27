# Linux 日志排查实战

对应 JD 高频要求："熟练使用 Linux 命令排查线上问题 / 分析日志定位缺陷"。

之前简历只写了"了解 Linux"——空口无凭。这里用 194 行生产风格支付日志，把 14 条排查命令真跑一遍，命令和原始输出全存在 `evidence/session.txt`，面试官可逐条核对，也可现场让你重跑。

## 环境

Windows 上用 Git Bash（自带 GNU 工具链，命令与 Linux 一致）：

```
grep (GNU grep) 3.0
GNU Awk 5.4.0
tail (GNU coreutils) 8.32
```

复现：

```bash
cd "D:/WorkBuddyOutput/payment-api-test/log-analysis"
python scripts/gen_logs.py     # 固定随机种子，每次生成内容一致
bash scripts/run_drill.sh      # 执行 drill_cmds.txt 里的 14 条命令
cat evidence/session.txt       # 看命令 + 真实输出
```

## 日志格式

```
2026-11-25 10:12:07,891 WARN  [callback-worker] [req-b81d4e03] duplicate callback not blocked order_id=ORD20261125001 ...
  ① 日期时间(含毫秒)        ② 级别   ③ 服务模块            ④ trace_id                ⑤ 消息体（key=value）
```

字段位置固定，`awk` 按空格切分：`$1`=日期 `$2`=时间 `$3`=级别 `$4`=服务 `$5`=trace_id。日志里埋了 4 个缺陷痕迹：重复回调重复记账、余额更新静默失败、金额精度丢失、bool 绕过类型校验，另有多行异常堆栈和慢请求。

---

## 14 条实战命令

### 1. 定位"付了钱没到账"——grep 基础 + 行号

场景：用户投诉支付成功但余额为 0。先搜最可疑的关键词。

```bash
grep -n "rowcount=0" logs/payment-service.log
```

实测命中 1 行：

```
175:2026-11-25 11:03:14,091 WARN [account-svc] [req-2a7e91f0] update account rowcount=0 user_id=1002 no exception raised balance_still=0.0
```

结论：`UPDATE accounts` 影响 0 行却**没抛异常、没回滚**，流水已记、余额没动。`-n` 带行号，方便后续 `sed -n '170,180p'` 看上下文。

### 2. 查一个订单的完整链路——精确匹配

场景：用户给了订单号 `ORD20261125001`，要还原它经历了什么。

```bash
grep -n "ORD20261125001" logs/payment-service.log
```

实测 7 行，链路还原：

```
156 下单成功 100.5 元
157 首次回调 status=PAID
158 插入流水 balance_after=100.5
159 第二次回调 WARN duplicate callback not blocked
160 又插流水 balance_after=201.0
161 第三次回调 WARN
162 再插流水 balance_after=301.5
```

结论：用户付 100.5，记了 301.5，**多记 201 元**。这就是 P0 资损缺陷的现场证据。

### 3. 看异常前后的因果——grep -B / -A

场景：光看 WARN 行不够，要看它前后发生了什么。

```bash
grep -n -B 2 -A 4 "duplicate callback not blocked" logs/payment-service.log
```

`-B 2` 取前 2 行，`-A 4` 取后 4 行。实测输出里 WARN 后面紧跟的正是 `insert transaction` 成功行——证明"未拦截"直接导致重复记账，不是日志写错。

**面试点**：只会 `grep 关键词` 是初级；会用 `-B/-A/-C` 还原上下文才是排查。

### 4. 按时间窗口圈定范围

场景：事故发生在 10:12，只看这一分钟。

```bash
grep "2026-11-25 10:12" logs/payment-service.log
```

实测 7 行，正好是订单 001 的完整链路。日志按 `日期 时间` 开头，直接按字符串前缀过滤，比写正则解析快得多。

### 5. 统计 ERROR 总量——grep -c

```bash
grep -c "ERROR" logs/payment-service.log
```

实测输出：`8`。`-c` 只计数不打印内容，适合快速判断影响面。

### 6. 按级别统计分布——awk + sort + uniq

```bash
awk '{print $3}' logs/payment-service.log | sort | uniq -c | sort -rn
```

实测：

```
176 INFO
 10 WARN
  8 ERROR
```

这是 `awk → sort → uniq → sort -rn` 四段管道，面试高频。`sort` 先把相同值排到一起，`uniq -c` 才能正确计数；末尾 `sort -rn` 按数字倒序排。

### 7. 按小时统计错误——awk split

```bash
awk '$3=="ERROR" {split($2,a,":"); print a[1]":00"}' logs/payment-service.log | sort | uniq -c
```

实测：`8 16:00`——8 条 ERROR 全集中在 16 点。

结论：错误扎堆一个时段，优先查那个时间点有没有发布、配置变更或流量突增。这是"缩小排查范围"的标准手法。

### 8. 找最慢的请求——awk 切字段 + sort -nr

```bash
grep "slow request" logs/payment-service.log | awk -F'cost=|ms' '{print $2}' | sort -nr
```

实测：

```
2105
1842
1320
967
```

`-F'cost=|ms'` 用正则做分隔符，直接从 `cost=2105ms` 里抠出数字。排序后最慢的 2105ms 排第一，对应一条 500 错误——性能问题和错误关联上了。

### 9. 多条件 AND 过滤

```bash
grep "WARN" logs/payment-service.log | grep "account-svc"
```

实测只剩 `rowcount=0` 那一条。两个 `grep` 串联就是"与"关系，比写复杂正则清楚。要"或"关系用 `grep -E "WARN|ERROR"`。

### 10. 排除噪音——grep -v

```bash
grep "status=500" logs/payment-service.log | grep -v "/health"
```

实测 2 条真 500，排掉了健康检查干扰。`grep -v` 反向选择，日志文件里大量 INFO 噪音时必备。

### 11. 统计受影响的订单数——grep -oE + sort -u

```bash
grep "duplicate callback not blocked" logs/payment-service.log | grep -oE 'order_id=[A-Z0-9]+' | sort -u
```

实测输出：`order_id=ORD20261125001`。

`-o` 只输出匹配部分，`-E` 用正则提取 `key=value`，`sort -u` 去重。一句话回答"影响多少用户/订单"——这是写故障报告时的关键数字。

### 12. 提取完整异常堆栈——grep -A

```bash
grep -n -A 8 "unhandled exception" logs/payment-service.log
```

实测拿到 7 行堆栈，最后一行：

```
ZeroDivisionError: division by zero
```

结论：`calc_balance()` 里 `total / count` 没判 `count==0`。**面试可对照**：这就是你逆向时看 Crash StackTrace 的同一套思路——先找第一行异常类型，再往上找自己代码里的调用点。

### 13. 高频用户 TOP10——uniq -c + sort -rn

```bash
grep -oE 'user_id=[0-9]+' logs/payment-service.log | sort | uniq -c | sort -rn | head -10
```

实测输出用户 1004/1002 各 20 次居首。用于判断"是不是某个用户在刷接口"，配合第 10 条的限流告警能串成风控排查链。

### 14. 只看最近窗口——tail + grep

```bash
tail -n 25 logs/payment-service.log | grep "ERROR"
```

实测拿到 8 行（含 7 行堆栈）。线上救火时先 `tail -n 200 | grep ERROR` 看最近发生了什么，比全文件 grep 快。

**实时追踪版**（会持续阻塞，单独跑，不在批量脚本里）：

```bash
tail -f logs/payment-service.log | grep --line-buffered "ERROR"
```

`--line-buffered` 强制逐行刷新，否则管道缓冲会让你看不到实时输出。这个细节很多人不知道。

---

## 面试话术（可直接背）

> 线上反馈"支付成功但余额没变"，我先 `grep -n "rowcount=0"` 定位到 account-svc 的一条 WARN，发现 UPDATE 影响 0 行但没抛异常。再用 `grep -B 2 -A 4` 看上下文，确认流水已插入、余额没更新。然后 `grep -oE 'order_id=[A-Z0-9]+' | sort -u` 统计影响范围，确认只有 1 笔订单。最后 `awk` 按小时统计 ERROR，发现集中在 16:00，关联到一次发布。
>
> 根因是余额 UPDATE 没校验 rowcount，也没回滚事务。修复建议：校验 `cursor.rowcount > 0`，为 0 时抛异常回滚；或对 accounts 表做 upsert；再加定时对账任务比对流水合计与余额。

这段话里 `grep -n`、`-B/-A`、`-oE`、`sort -u`、`awk` 全用上了，而且每步都有明确目的。配套的错误堆栈分析还能接上你逆向看 Crash 栈的经验。

## 常见坑

- **`uniq` 前必须先 `sort`**：`uniq` 只比较相邻行，不排序会漏。
- **`tail -f | grep` 没输出**：管道缓冲，加 `grep --line-buffered`。
- **固定 `sleep(3)` 等日志写入**：跟自动化测试里的 flaky 一个道理，用循环检测文件或关键词出现，别猜时间。
- **别用 `cat 大文件 | grep`**：直接 `grep 关键词 文件`，少一次进程。

## 与项目的关系

这份日志埋的 4 个缺陷，和 `payment-api-test` 接口自动化用例里发现的 BUG-001~004 一一对应。也就是说：**接口测试负责发现缺陷，日志排查负责定位缺陷**，同一个故障两种手段。面试讲这个组合，比单讲"我会 grep"强得多。

简历可写：

> 搭建支付服务日志排查实战场景（194 行生产风格日志 + 14 条排查命令），用 grep -B/-A 还原异常上下文、awk + sort + uniq 按级别/小时统计错误、grep -oE 统计受影响订单，配合接口自动化用例完成"发现→定位→归因"闭环。
