# -*- coding: utf-8 -*-
"""
按顺序取词，生成 content/day-XX 的骨架 words.json。
文章正文（article.md 和 tts_text）由我手写，这个脚本只搭数据骨架。

顺序：Unit 1 → Unit 10，每 30 词一天，跨单元自然衔接。
书里的释义/记忆法/真题从 book/entries.json 取。

用法：
    python build/gen_skeleton.py --day 02 --start 31
    python build/gen_skeleton.py --day 02-08 --start 31
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(r"E:\english\四级你还在背单词吗txt")
ENTRIES = ROOT / "book" / "entries.json"
PER_DAY = 30


def load_words() -> list[str]:
    """按 Unit 1..10 的原始顺序拼出全部词（保持书的编排）"""
    files = [SRC / "Unit 1.txt"] + [SRC / f"Unit {i}.txt" for i in range(2, 11)]
    # 实际文件名大小写不一致，逐个试
    out: list[str] = []
    for i in range(1, 11):
        for cand in (SRC / f"Unit {i}.txt", SRC / f"unit {i}.txt"):
            if cand.exists():
                for ln in cand.read_text(encoding="utf-8-sig", errors="replace").split("\n"):
                    w = ln.strip()
                    if w and re.fullmatch(r"[a-zA-Z][a-zA-Z\-' ]*", w):
                        out.append(w.lower())
                break
    return out


def norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


def lookup(word: str, idx: dict) -> dict | None:
    n = norm(word)
    if n in idx:
        return idx[n]
    for k, v in idx.items():
        if k.startswith(n) and len(k) - len(n) <= 3:
            return v
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True, help="如 02 或 02-08")
    ap.add_argument("--start", type=int, required=True, help="起始词序号（1-based）")
    ap.add_argument("--unit", default="Unit 1")
    args = ap.parse_args()

    words = load_words()
    print(f"词表共 {len(words)} 词")

    entries = {}
    if ENTRIES.exists():
        e = json.loads(ENTRIES.read_text(encoding="utf-8"))
        entries = {norm(k): v for k, v in e.items()}
        print(f"词条库 {len(entries)} 条")

    if "-" in args.day:
        a, b = args.day.split("-")
        days = [f"{i:02d}" for i in range(int(a), int(b) + 1)]
    else:
        days = [args.day]

    pos = args.start - 1
    for d in days:
        chunk = words[pos : pos + PER_DAY]
        pos += PER_DAY
        if not chunk:
            print(f"Day {d}: 超出词表范围，跳过")
            continue

        out_words = []
        for w in chunk:
            e = lookup(w, entries) or {}
            out_words.append({
                "w": w,
                "ipa": e.get("ipa", ""),
                "pos": e.get("pos", ""),
                "cn": e.get("cn", ""),
                "mnemonic": e.get("mnemonic", ""),
                "zhenti": e.get("zhenti", ""),
                "sentence": "",          # 我填：文章里的原句
                "root": "",              # 我填：词根拆解
                "family": "",            # 我填：同族词
            })

        d_dir = ROOT / "content" / f"day-{d}"
        d_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "day": int(d),
            "unit": args.unit,
            "range": f"{args.start + (int(d) - int(days[0])) * PER_DAY}-"
                     f"{args.start + (int(d) - int(days[0])) * PER_DAY + len(chunk) - 1}",
            "source": "刘晓燕《四级你还在背单词吗》",
            "title": "",
            "title_cn": "",
            "tts_text": "",
            "sentences": [],
            "sentences_cn": [],
            "words": out_words,
        }
        (d_dir / "words.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  Day {d}: {len(out_words)} 词  ({chunk[0]} … {chunk[-1]})")

    print("\n骨架已生成。接下来填 title / tts_text / sentences / sentence / root")


if __name__ == "__main__":
    main()
