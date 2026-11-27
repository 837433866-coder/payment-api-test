#!/bin/bash
# JMeter 梯度压测：30 / 60 / 120 并发，压 /api/pay/create
# 用法：在 perf-test 目录执行 bash run_load_test.sh <jmeter的bin目录绝对路径>
set -e

JMETER_BIN="$1"
if [ -z "$JMETER_BIN" ]; then
  echo "用法: bash run_load_test.sh <jmeter的bin目录绝对路径>"
  exit 1
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

# 确认服务在线
echo "=== 检查被测服务 ==="
curl -s -m 5 http://127.0.0.1:5000/health || { echo "服务未运行，请先启动 mock_server/app.py"; exit 1; }
echo ""

mkdir -p results

for T in 30 60 120; do
  echo "=== 压测：${T} 并发 × 20 轮 ==="
  "$JMETER_BIN/jmeter" -n -t pay_create_load.jmx \
    -Jthreads=$T -Jramp=10 -Jloops=20 \
    -Jjmeter.save.saveservice.output_format=csv \
    -l "results/result_${T}.jtl" \
    -e -o "results/report_${T}" 2>&1 | tail -8
  echo ""
done

echo "=== 生成完毕 ==="
ls -la results/
