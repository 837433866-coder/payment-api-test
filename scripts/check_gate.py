#!/usr/bin/env python3
"""CI 质量门禁：读 pytest junitxml，判断构建是否放行。

规则（可用环境变量覆盖）：
  1. 用例总数 >= MIN_TESTS（默认 30），防止有人删用例刷通过率
  2. failures / errors 必须为 0
  3. xfail 数量 <= MAX_XFAIL（默认 7），新增缺陷必须显式登记，不许悄悄混进去
  4. xpass 数量必须为 0（缺陷被修复后要更新用例，不能留着过期标记）
"""
import os
import sys
import xml.etree.ElementTree as ET

JUNIT = os.environ.get("JUNIT_XML", "junit.xml")
MIN_TESTS = int(os.environ.get("MIN_TESTS", "30"))
MAX_XFAIL = int(os.environ.get("MAX_XFAIL", "7"))


def main():
    if not os.path.exists(JUNIT):
        print(f"[GATE FAIL] 找不到 {JUNIT}")
        return 1

    try:
        root = ET.parse(JUNIT).getroot()
    except ET.ParseError as e:
        print(f"[GATE FAIL] junit.xml 解析失败: {e}")
        return 1

    suite = root.find("testsuite")
    if suite is None and root.tag == "testsuite":
        suite = root
    if suite is None:
        print("[GATE FAIL] junit.xml 里没有 testsuite 节点")
        return 1

    total = int(suite.get("tests", 0))
    failures = int(suite.get("failures", 0))
    errors = int(suite.get("errors", 0))
    skipped = int(suite.get("skipped", 0))

    xfail = 0
    xpass = 0
    for case in suite.findall("testcase"):
        for child in case:
            t = child.get("type", "")
            if "xfail" in t:
                xfail += 1
            elif "xpass" in t:
                xpass += 1

    print("=" * 46)
    print("质量门禁检查结果")
    print("=" * 46)
    print(f"  用例总数 : {total:>3}  (要求 >= {MIN_TESTS})")
    print(f"  失败     : {failures:>3}")
    print(f"  错误     : {errors:>3}")
    print(f"  已登记缺陷(xfail): {xfail:>3}  (允许 <= {MAX_XFAIL})")
    print(f"  意外通过(xpass)  : {xpass:>3}  (要求 = 0)")
    print("-" * 46)

    problems = []
    if total < MIN_TESTS:
        problems.append(f"用例数 {total} < {MIN_TESTS}，疑似删用例")
    if failures:
        problems.append(f"存在 {failures} 个失败用例")
    if errors:
        problems.append(f"存在 {errors} 个错误")
    if xfail > MAX_XFAIL:
        problems.append(f"新增缺陷 {xfail - MAX_XFAIL} 个未登记")
    if xpass:
        problems.append(f"有 {xpass} 个已修复缺陷未更新用例标记")

    if problems:
        for p in problems:
            print(f"  [FAIL] {p}")
        print("=" * 46)
        print("GATE: BLOCKED")
        return 1

    print("  [OK] 全部检查通过")
    print("=" * 46)
    print("GATE: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
