# -*- coding: utf-8 -*-
"""
滚动复习排期 —— **纯函数，无状态**。

## 为什么不用 progress.json 的 days 记录

`progress.py` 原来的 `due_words()` 依赖 `st["days"]` 里的「何时标记学完」。
但线上环境**永远拿不到这个信号**：

  - 用户不会主动去点「标记学完」（页面上根本没这个入口）
  - 云端跑的是 push_web.py，它**只读不写** progress.json
  - 结果：`review_log` 至今是空的，复习从来没触发过

所以改成**从 `start_date` 纯推算**：
    Day N 在 `start_date + (N-1)` 这天学
    它的复习日 = 学习日 + 1 / 2 / 4 / 7 / 15 天

推导：今天是第 D 天，要复习的是第 `D - gap` 天（gap ∈ 间隔表）。
例如 D=4，gap=1 → Day 03；gap=2 → Day 02；gap=4 → Day 00（无效，跳过）。

## 这样设计的好处

  - **无状态**：不需要任何人写进度文件，云端只读就能算
  - **自愈**：漏推了一天，第二天的排期照样正确（不依赖"上次推到哪"）
  - **可测**：给定 start_date 和 today，结果完全确定，能写单元测试
  - **能补**：想补推历史某天，传 today 就行
"""
from __future__ import annotations

from datetime import date, timedelta

# 间隔重复：学完之后第 N 天复习（艾宾浩斯简化版）
#
# ⚠️ **这是全项目唯一的间隔表** —— progress.py 从本文件 import。
#    错误日志 #13 记过教训：同一张后缀表散在 3 个文件里，改一处漏两处，
#    导致三个工具给出不一致的结论。别再复制这张表。
REVIEW_OFFSETS = (1, 2, 4, 7, 15)

# 一天最多列几组复习，超出的只报数
# （推送消息不能太长，否则重点被淹没）
MAX_SHOWN = 3


def day_of(start: date, on: date) -> int:
    """某天是第几学习日（Day 01 从 1 开始）。早于起始日返回 0。"""
    return (on - start).days + 1


def date_of(start: date, day: int) -> date:
    """第 N 学习日对应的日期"""
    return start + timedelta(days=day - 1)


def due_reviews(
    start: date,
    on: date,
    total_days: int,
    offsets: tuple[int, ...] = REVIEW_OFFSETS,
) -> list[dict]:
    """
    算出 `on` 这天该复习哪些天。

    返回按「复习轮次」排序的列表，每项：
        {"day": "03", "round": 1, "gap": 1, "learned": date(2026,10,15)}

    只返回**已学过且内容存在**的天（day 在 1..total_days 之间）。
    """
    cur = day_of(start, on)
    out = []
    for i, gap in enumerate(offsets):
        n = cur - gap
        if n < 1 or n > total_days:
            continue
        out.append({
            "day": f"{n:02d}",
            "round": i + 1,
            "gap": gap,
            "learned": date_of(start, n),
        })
    # 间隔小的（刚学完的）排前面
    out.sort(key=lambda x: x["gap"])
    return out


def summarize(reviews: list[dict], total_days: int) -> dict:
    """给推送用的汇总：该显示哪几条、一共几组、涉及多少词。"""
    return {
        "shown": reviews[:MAX_SHOWN],
        "total": len(reviews),
        "hidden": max(0, len(reviews) - MAX_SHOWN),
    }
