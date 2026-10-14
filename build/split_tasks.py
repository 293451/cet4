# -*- coding: utf-8 -*-
"""
把剩余词表按天分段，供子 Agent 领取。

输出 _task/day-XX.words.json：每天的 30 个词 + 书里的释义/记忆法/真题。
子 Agent 只需读自己那天的文件，不用碰全书。

用法：
    python build/split_tasks.py --start-day 09
"""
from __future__ import annotations

import argparse
import io
import json
import math
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(r"E:\english\四级你还在背单词吗txt")
ENTRIES = ROOT / "book" / "entries.json"
OUT = ROOT / "_task"
PER_DAY = 30


def load_words() -> list[str]:
    out: list[str] = []
    for i in range(1, 11):
        for cand in (SRC / f"Unit {i}.txt", SRC / f"unit {i}.txt"):
            if not cand.exists():
                continue
            for ln in cand.read_text(encoding="utf-8-sig", errors="replace").split("\n"):
                w = ln.strip()
                if w and re.fullmatch(r"[a-zA-Z][a-zA-Z\-' ]*", w):
                    out.append(w.lower())
            break
    return out


def norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


def lookup(word: str, idx: dict) -> dict:
    n = norm(word)
    if n in idx:
        return idx[n]
    for k, v in idx.items():
        if k.startswith(n) and len(k) - len(n) <= 3:
            return v
    return {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-day", type=int, default=9)
    ap.add_argument("--unit", default="Unit 2~9")
    args = ap.parse_args()

    words = load_words()
    entries = {norm(k): v for k, v in json.loads(ENTRIES.read_text(encoding="utf-8")).items()}

    done = (args.start_day - 1) * PER_DAY
    rest = words[done:]
    n_days = math.ceil(len(rest) / PER_DAY)
    OUT.mkdir(exist_ok=True)

    print(f"词表 {len(words)} 词，已完成 {done} 词，剩余 {len(rest)} 词 → {n_days} 天")

    idx_lines = []
    for i in range(n_days):
        day = args.start_day + i
        chunk = rest[i * PER_DAY : (i + 1) * PER_DAY]
        if not chunk:
            break
        items = []
        for w in chunk:
            e = lookup(w, entries)
            items.append({
                "w": w,
                "ipa": e.get("ipa", ""),
                "pos": e.get("pos", ""),
                "cn": e.get("cn", ""),
                "mnemonic": e.get("mnemonic", ""),
                "zhenti": e.get("zhenti", ""),
            })
        f = OUT / f"day-{day:02d}.words.json"
        f.write_text(
            json.dumps({"day": day, "words": items}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        idx_lines.append(f"day-{day:02d}: {chunk[0]} … {chunk[-1]}  ({len(chunk)} 词)")

    (OUT / "INDEX.txt").write_text("\n".join(idx_lines), encoding="utf-8")
    print(f"\n已生成 {len(idx_lines)} 个任务文件到 {OUT}")
    print("\n".join(idx_lines))
    print(f"\n最后一天: day-{args.start_day + n_days - 1:02d}")


if __name__ == "__main__":
    main()
