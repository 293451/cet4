# -*- coding: utf-8 -*-
"""
学习进度 + 滚动复习排期。

⚠️ **排期逻辑已抽出到 `review.py`，本文件从那里 import。**

为什么改（错误日志 #13 的同类教训）：这里原来有一份自己的
`due_words()`，靠 `st["days"]` 里的「何时标记学完」算复习。
但线上环境**永远拿不到那个信号**（用户不标记、云端只读），
所以线上复习从来没触发过。

现在统一以 `review.py` 的**从 start_date 纯推算**为准 ——
一份逻辑、一个间隔表，本地和云端结论必然一致。
`progress.json` 的 `days` 保留，但只用于「记录学了什么」，
不再参与排期计算。

两类复习：
  1. 每天推送里附「今日复习」（已接入，见 push_web.py）
  2. 每 5 天一篇「纯复习文章」—— 尚未实现，见 --plan

用法：
    python build/progress.py --status                 # 看当前进度
    python build/progress.py --plan                   # 出下一课的计划
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from review import REVIEW_OFFSETS, due_reviews, day_of  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "progress.json"

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


def total_days() -> int:
    """content/ 下一共有多少天（排期的上界）"""
    return len([p for p in (ROOT / "content").glob("day-*")
                if (p / "words.json").exists()])


def due_words(st: dict, on: date | None = None) -> list[dict]:
    """
    算出某天该复习哪些词。

    走 `review.py` 的纯推算（从 start_date 起，与 progress 记录无关）。
    读 content/ 拿词表 —— 那才是「该复习什么」的权威来源，
    `st["days"]` 里的 words 只作兜底。
    """
    on = on or date.today()
    start = date.fromisoformat(st["start_date"])
    out = []
    for r in due_reviews(start, on, total_days()):
        ws: list[str] = []
        p = ROOT / "content" / f"day-{r['day']}" / "words.json"
        if p.exists():
            try:
                ws = [w["w"] for w in
                      json.loads(p.read_text(encoding="utf-8"))["words"]]
            except Exception:
                ws = []
        if not ws:
            ws = st.get("days", {}).get(r["day"], {}).get("words", [])
        out.append({
            "day": r["day"],
            "round": r["round"],
            "gap_days": r["gap"],
            "words": ws,
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
    """
    出下一课计划。

    ⚠️ 「下一课」按 **日期** 算，不按 progress.json 的记录 ——
       那个记录只有用户手动 --done 才更新，线上从来不写，
       所以永远停在 Day 01，算出来的"下一课"是错的。
    """
    start = date.fromisoformat(st["start_date"])
    cur = day_of(start, date.today())
    nxt = max(1, cur)

    # 词序号区间直接读 content 里的 `range` 字段。
    #
    # ⚠️ **不要自己累加计数** —— 实测会偏。Day 03 实际有 31 词
    #    （早先补词时整段多带了一个），但它的 range 是 '61-90'。
    #    按计数累加得 91 → 算出 '92-121'，而权威值是 '91-120'。
    #    **书里给的 range 才是事实来源，计数只是推算。**
    rf = ROOT / "content" / f"day-{nxt:02d}" / "words.json"
    rng = ""
    n_new = st["words_per_day"]
    if rf.exists():
        try:
            x = json.loads(rf.read_text(encoding="utf-8"))
            rng = x.get("range", "")
            n_new = len(x["words"])
        except Exception:
            pass

    dl = due_words(st)
    rev = is_review_day(st, f"{nxt:02d}")

    print(f"=== 今天的课：Day {nxt:02d}（{date.today()}）===")
    if rev:
        print("类型：纯复习文章（不加新词）")
    else:
        print(f"类型：新词 {rng or f'约 {n_new} 个'}")
        print(f"新词数：{n_new}")
    if dl:
        pool = [w for d in dl for w in d["words"]]
        print(f"\n要顺带复习的旧词（从 {len(pool)} 个里挑 3-5 个塞进文章）：")
        for d in dl:
            print(f"  Day {d['day']}：{' '.join(d['words'][:8])} ...")
    else:
        print("\n无需复习旧词（前几天刚学的还没到期）。")


def cmd_done(st: dict, day: str) -> None:
    """
    标记某天已学完 —— **只作记录，不参与排期**。

    ⚠️ 排期已改为从 start_date 纯推算（见 review.py），
       所以这份记录即使缺失/过时，复习提醒也照样正确。
       它现在的价值是「留一份学过什么的快照」。
    """
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


def cmd_sync(st: dict) -> None:
    """
    按日期把 progress.json 追平 —— 把「截至今天该学过的天」都补上记录。

    为什么需要：用户从不手动 --done，线上也不写这个文件，
    于是它永远停在 Day 01，看着像"只学了一天"。
    排期虽然不依赖它（改为纯推算），但**留一份过时数据会误导人**
    （错误日志 H14：待做表不更新会让人判断错卡点）。

    用「该学那天」的日期记账，而不是今天 —— 这样补出来的记录是对的。
    """
    start = date.fromisoformat(st["start_date"])
    cur = day_of(start, date.today())
    n = total_days()
    added = 0
    for i in range(1, min(cur, n) + 1):
        d = f"{i:02d}"
        if d in st["days"]:
            continue
        src = ROOT / "content" / f"day-{d}" / "words.json"
        if not src.exists():
            continue
        data = json.loads(src.read_text(encoding="utf-8"))
        st["days"][d] = {
            "date": str(start + timedelta(days=i - 1)),   # 该学那天的日期
            "unit": data.get("unit", ""),
            "range": data.get("range", ""),
            "words": [w["w"] for w in data["words"]],
        }
        added += 1
    save(st)
    print(f"已追平：补了 {added} 天，现共 {len(st['days'])} 天记录"
          f"（截至今天第 {cur} 天）。")


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
    ap.add_argument("--sync", action="store_true",
                    help="按日期把 progress.json 追平（补记截至今天的每一天）")
    ap.add_argument("--start-date", metavar="YYYY-MM-DD")
    args = ap.parse_args()

    st = load()
    if args.start_date:
        st["start_date"] = args.start_date
        save(st)
        print(f"起始日期已设为 {args.start_date}")

    if args.done:
        cmd_done(st, args.done)
    elif args.sync:
        cmd_sync(st)
    elif args.plan:
        cmd_plan(st)
    elif args.due:
        cmd_due(st)
    else:
        cmd_status(st)


if __name__ == "__main__":
    main()
