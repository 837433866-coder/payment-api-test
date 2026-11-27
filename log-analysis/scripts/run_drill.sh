#!/usr/bin/env bash
# 逐条执行 drill_cmds.txt 里的排查命令，把命令与真实输出一起写入 evidence/session.txt
cd "$(dirname "$0")/.." || exit 1
mkdir -p evidence
: > evidence/session.txt

i=0
while IFS= read -r cmd; do
    [ -z "$cmd" ] && continue
    i=$((i + 1))
    {
        echo "────────────────────────────────────────────"
        echo "[$i] \$ $cmd"
        echo "────────────────────────────────────────────"
        eval "$cmd"
        echo
    } >> evidence/session.txt 2>&1
done < drill_cmds.txt

echo "执行 $i 条命令 -> evidence/session.txt"
