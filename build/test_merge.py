# -*- coding: utf-8 -*-
"""
逐词时间戳合并逻辑的回归测试 —— **跑缓存，不调 API**。

为什么要有这个：`merge_syllables` 是全项目最容易改坏的地方
（错误日志 #10/#11/#18，前后修了五六轮）。而每次改完想验证都得重调
MiniMax —— 慢、烧配额、而且每次返回的音节数据还有细微差异，
没法做稳定的对照实验。

所以：`tts.py` 每次调完 API 会把原始响应落盘到 `_cache/tts/`，
本脚本直接拿它重跑合并逻辑。零成本、零配额、结果完全可复现。

用法：
    python build/test_merge.py            # 跑所有有缓存的天
    python build/test_merge.py --day 68   # 只跑一天
    python build/test_merge.py --verbose  # 打印失配细节

判据：
  1. 合并出的词序列 == 原文词序列（**这是硬性要求**）
  2. 结果和已落盘的 docs/audio/day-XX.words.json 一致（防止改坏已通过的天）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tts import merge_syllables  # noqa: E402  （它会顺手把 stdout 设成 utf-8）

CACHE = ROOT / "_cache" / "tts"


def norm(s: str) -> str:
    """归一：只留字母数字，小写。标点和大小写不参与比对。"""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def words_of(merged: list[dict]) -> list[str]:
    return [x for x in (norm(w["text"]) for w in merged) if x]


def expected(text: str) -> list[str]:
    return [x for x in (norm(w) for w in text.split()) if x]


def check_day(day: str, verbose: bool) -> tuple[bool, str]:
    """返回 (是否通过, 说明)"""
    cf = CACHE / f"day-{day}.syllables.json"
    src = ROOT / "content" / f"day-{day}" / "words.json"
    if not cf.exists():
        return True, "无缓存，跳过"
    if not src.exists():
        return False, f"缺 {src.relative_to(ROOT)}"

    text = json.loads(src.read_text(encoding="utf-8"))["tts_text"]
    want = expected(text)

    merged = merge_syllables(json.loads(cf.read_text(encoding="utf-8")), text)
    got = words_of(merged)

    # 判据 1：词序列必须和原文一致
    if got != want:
        msg = f"{len(got)}/{len(want)} 词"
        if verbose:
            i = next((i for i in range(max(len(got), len(want)))
                      if (got[i] if i < len(got) else None)
                      != (want[i] if i < len(want) else None)), -1)
            msg += (f"\n      首个差异 @{i}: "
                    f"合并={got[i] if 0 <= i < len(got) else '<无>'!r} "
                    f"原文={want[i] if 0 <= i < len(want) else '<无>'!r}")
        return False, msg

    # 判据 2：不能和已落盘的结果不一致（防止改坏已通过的天）
    wf = ROOT / "docs" / "audio" / f"day-{day}.words.json"
    if wf.exists():
        disk = words_of(json.loads(wf.read_text(encoding="utf-8"))["words"])
        if disk != got:
            return False, "和已落盘的 words.json 不一致（改动影响了原有结果）"
        return True, f"{len(got)} 词 · 落盘一致"

    return True, f"{len(got)} 词 · 未落盘"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    if args.day:
        days = [args.day]
    else:
        days = sorted(p.name.split("-")[1].split(".")[0]
                      for p in CACHE.glob("day-*.syllables.json"))
    if not days:
        sys.exit(f"缓存里没有数据（{CACHE.relative_to(ROOT)}/）。"
                 f"先跑一次 python build/tts.py --day XX 把原始响应存下来。")

    n_ok = n_skip = 0
    for d in days:
        ok, msg = check_day(d, args.verbose)
        if ok:
            n_ok += 1
            if "跳过" in msg:
                n_skip += 1
                continue
        print(f"{'✓' if ok else '✗'} Day {d}  {msg}")

    real = n_ok - n_skip
    print(f"\n通过 {real}/{len(days) - n_skip}"
          + (f"（另有 {n_skip} 天无缓存）" if n_skip else ""))
    if n_ok < len(days):
        sys.exit(1)


if __name__ == "__main__":
    main()
