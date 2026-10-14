# -*- coding: utf-8 -*-
"""
学习进度 + 滚动复习排期。

设计目标：让用户在读新文章时，不知不觉复习旧词。

两类复习：
  1. 新文章里「故意塞旧词」—— 我写 content 时按 review_words 输出
  2. 每 5 天一篇「纯复习文章」—— 不加新词，把前 5 天的词换个场景再讲一遍

用法：
    python build/progress.py --status                 # 看当前进度
    python build/progress.py --plan                   # 出下一课的计划（含该复习哪些词）
    python build/progress.py --done 01                # 标记 Day 01 已学完
    python build/progress.py --due                    # 列出到期待复习的词
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "progress.json"

# 间隔重复：学完之后第 N 天复习（艾宾浩斯简化版）
REVIEW_OFFSETS = [1, 2, 4, 7, 15]
# 每几天插入一篇纯复习文章
REVIEW_EVERY = 5
# 每天新词量
WORDS_PER_DAY = 30


def load() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {
        "start_date": str(date.today()),
        "words_per_day": WORDS_PER_DAY,
        "days": {},          # {"01": {"date": "2026-10-13", "range": "1-30", "words": [...]}}
        "review_log": [],    # [{"date": ..., "day": "01", "round": 1}]
    }


def save(st: dict) -> None:
    STATE.write_text(
        json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def next_day_num(st: dict) -> str:
    days = [int(k) for k in st["days"]]
    return f"{(max(days) + 1) if days else 1:02d}"


def due_words(st: dict, on: date | None = None) -> list[dict]:
    """算出某天该复习哪些词"""
    on = on or date.today()
    out = []
    for day, info in st["days"].items():
        learned = date.fromisoformat(info["date"])
        gap = (on - learned).days
        if gap in REVIEW_OFFSETS:
            out.append({
                "day": day,
                "round": REVIEW_OFFSETS.index(gap) + 1,
                "gap_days": gap,
                "words": info["words"],
            })
    return out


def is_review_day(st: dict, day_num: str) -> bool:
    """这一天是不是「纯复习日」（每逢 REVIEW_EVERY 的倍数）"""
    return int(day_num) % REVIEW_EVERY == 0


def cmd_status(st: dict) -> None:
    days = st["days"]
    if not days:
        print("还没开始。")
        print(f"计划：每天 {st['words_per_day']} 词，每 {REVIEW_EVERY} 天一篇纯复习文章。")
        return

    done = sorted(days)
    total = sum(len(days[d]["words"]) for d in done)
    print(f"起始日期：{st['start_date']}")
    print(f"已学：{len(done)} 天 · {total} 词 · 最近 Day {done[-1]}")
    print(f"复习间隔：第 {', '.join(str(x) for x in REVIEW_OFFSETS)} 天")
    print()
    dl = due_words(st)
    if dl:
        print("今天该复习：")
        for d in dl:
            print(f"  Day {d['day']}（学完 {d['gap_days']} 天，第 {d['round']} 轮）："
                  f"{len(d['words'])} 词")
            print(f"    {' '.join(d['words'][:12])}{' ...' if len(d['words']) > 12 else ''}")
    else:
        print("今天没有到期的复习。")


def cmd_plan(st: dict) -> None:
    nxt = next_day_num(st)
    start_idx = sum(len(st["days"][d]["words"]) for d in st["days"])
    end_idx = start_idx + st["words_per_day"]

    dl = due_words(st)
    rev = is_review_day(st, nxt)

    print(f"=== 下一课计划：Day {nxt} ===")
    print(f"类型：{'纯复习文章（不加新词）' if rev else f'新词 {start_idx + 1}-{end_idx}'}")
    if not rev:
        print(f"新词数：{st['words_per_day']}")
    if dl:
        pool = [w for d in dl for w in d["words"]]
        print(f"\n要顺带复习的旧词（从 {len(pool)} 个里挑 3-5 个塞进文章）：")
        for d in dl:
            print(f"  Day {d['day']}：{' '.join(d['words'][:8])} ...")
    else:
        print("\n无需复习旧词（前几天刚学的还没到期）。")


def cmd_done(st: dict, day: str) -> None:
    src = ROOT / "content" / f"day-{day}" / "words.json"
    if not src.exists():
        sys.exit(f"找不到 {src}")
    data = json.loads(src.read_text(encoding="utf-8"))
    st["days"][day] = {
        "date": str(date.today()),
        "unit": data.get("unit", ""),
        "range": data.get("range", ""),
        "words": [w["w"] for w in data["words"]],
    }
    save(st)
    print(f"已标记 Day {day} 学完（{len(data['words'])} 词）。")


def cmd_due(st: dict) -> None:
    dl = due_words(st)
    if not dl:
        print("今天没有到期的复习。")
        return
    for d in dl:
        print(f"Day {d['day']}（第 {d['round']} 轮，间隔 {d['gap_days']} 天）")
        for i in range(0, len(d["words"]), 10):
            print("  " + " ".join(d["words"][i : i + 10]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--due", action="store_true")
    ap.add_argument("--done", metavar="DAY")
    ap.add_argument("--start-date", metavar="YYYY-MM-DD")
    args = ap.parse_args()

    st = load()
    if args.start_date:
        st["start_date"] = args.start_date
        save(st)
        print(f"起始日期已设为 {args.start_date}")

    if args.done:
        cmd_done(st, args.done)
    elif args.plan:
        cmd_plan(st)
    elif args.due:
        cmd_due(st)
    else:
        cmd_status(st)


if __name__ == "__main__":
    main()
