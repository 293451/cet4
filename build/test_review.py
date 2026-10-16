# -*- coding: utf-8 -*-
"""
复习排期推导的测试 —— **纯函数，不需要任何外部依赖**。

判据：第 D 学习日要复习的是第 (D - gap) 天，gap ∈ {1,2,4,7,15}，
      且被复习的那天必须真实存在（1..total_days）。

为什么值得单独测：这套推导是**算出来的**，不是查表得来的。
一旦间隔表改动、或 date 运算写错（差一天很常见），
表现是「复习提醒悄悄晚一天」—— 不报错、不崩溃，只是不对。
所以要用一堆手算过的边界把它钉死。

用法：
    python build/test_review.py
"""

import sys
from datetime import date
sys.path.insert(0, "build")
from review import due_reviews

START = date(2026, 10, 13)
fails = []
def chk(label, got, want):
    ok = got == want
    if not ok: fails.append(f"{label}  got={got} want={want}")
    print(f"{'✓' if ok else '✗'} {label}")

# D=2 (10/14): gap1→D1. gap2→D0 无效
chk("10/14 Day02 → [01]",        [r["day"] for r in due_reviews(START, date(2026,10,14),69)], ["01"])
# D=3 (10/15): gap1→D2, gap2→D1, gap4→D-1 无效
chk("10/15 Day03 → [02,01]",     [r["day"] for r in due_reviews(START, date(2026,10,15),69)], ["02","01"])
# D=4 (10/16): gap1→D3, gap2→D2, gap4→D0 无效
chk("10/16 Day04 → [03,02]",     [r["day"] for r in due_reviews(START, date(2026,10,16),69)], ["03","02"])
# D=5 (10/17): gap1→D4, gap2→D3, gap4→D1, gap7→D-2
chk("10/17 Day05 → [04,03,01]",  [r["day"] for r in due_reviews(START, date(2026,10,17),69)], ["04","03","01"])
# D=8 (10/20): gap1→D7, gap2→D6, gap4→D4, gap7→D1, gap15→D-7
chk("10/20 Day08 → [07,06,04,01]",[r["day"] for r in due_reviews(START, date(2026,10,20),69)], ["07","06","04","01"])
# D=16 (10/28): 1→15, 2→14, 4→12, 7→9, 15→1
chk("10/28 Day16 → [15,14,12,09,01]",[r["day"] for r in due_reviews(START, date(2026,10,28),69)], ["15","14","12","09","01"])
# D=17 (10/29): 全部前移一天
chk("10/29 Day17 → [16,15,13,10,02]",[r["day"] for r in due_reviews(START, date(2026,10,29),69)], ["16","15","13","10","02"])
# 起始日 / 之前
chk("10/13 起始日 → []",         [r["day"] for r in due_reviews(START, date(2026,10,13),69)], [])
chk("10/12 起始前 → []",         [r["day"] for r in due_reviews(START, date(2026,10,12),69)], [])
# 末尾: Day69 的学习日 = 12/20（10/13 + 68 天）
# 12/20 当天复习的是更早的天：1→68, 2→67, 4→65, 7→62, 15→54
chk("12/20 Day69 → [68,67,65,62,54]",
    [r["day"] for r in due_reviews(START, date(2026,12,20),69)], ["68","67","65","62","54"])
# 12/21 = Day70（已超课程，但 Day69 的 +1 复习日正是这天）
chk("12/21 Day70 → [69,68,66,63,55]",
    [r["day"] for r in due_reviews(START, date(2026,12,21),69)], ["69","68","66","63","55"])
# 12/22 = Day71
chk("12/22 Day71 → [69,67,64,56]",
    [r["day"] for r in due_reviews(START, date(2026,12,22),69)], ["69","67","64","56"])
# 全部窗口过去后
chk("2027-01-05 → []",
    [r["day"] for r in due_reviews(START, date(2027,1,5),69)], [])
# 超出全部窗口
chk("2027-02-01 → []",           [r["day"] for r in due_reviews(START, date(2027,2,1),69)], [])
# 多组: D=15 (10/27): 1→14, 2→13, 4→11, 7→8, 15→0 无效
chk("10/27 Day15 → [14,13,11,08]",[r["day"] for r in due_reviews(START, date(2026,10,27),69)], ["14","13","11","08"])
# 轮次标注正确
rs = due_reviews(START, date(2026,10,27), 69)
chk("10/27 轮次 = [1,2,3,4]",    [r["round"] for r in rs], [1,2,3,4])
chk("10/27 gap  = [1,2,4,7]",    [r["gap"] for r in rs], [1,2,4,7])

print()
print("全部通过 ✓" if not fails else f"失败 {len(fails)}: {fails}")
sys.exit(1 if fails else 0)
