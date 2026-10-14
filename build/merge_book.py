# -*- coding: utf-8 -*-
"""
把书里的词条数据合并进 content/day-XX/words.json。

为什么要这一步：我之前手写的 words.json 里，音标/释义/词根讲解都是我自己生成的，
和书里（刘晓燕原文）有出入。现在有了 OCR 出来的 entries.json，应该用书里的原文。

合并规则（书里优先，我写的兜底）：
    ipa       <- 书的音标
    cn        <- 书的释义（去「例」）
    mnemonic  <- 书的「千方百计记单词」（新增字段）
    zhenti    <- 书的真题例句（新增字段）
    其余字段（sentence / root / family / collocation）保留我写的

用法：
    python merge_book.py --day 01              # 就地更新 words.json
    python merge_book.py --day 01 --dry-run    # 只报告差异
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
ENTRIES = ROOT / "book" / "entries.json"


def norm(w: str) -> str:
    return re.sub(r"[^a-z]", "", w.lower())


def build_index(entries: dict) -> dict[str, dict]:
    """建立归一化索引，容忍词形差异"""
    idx = {}
    for k, v in entries.items():
        idx[norm(k)] = v
    return idx


def lookup(word: str, idx: dict[str, dict]) -> dict | None:
    """先精确，再前缀模糊（长词优先，避免短词误配）"""
    n = norm(word)
    if n in idx:
        return idx[n]
    cands = [(k, v) for k, v in idx.items() if k.startswith(n) and len(k) - len(n) <= 3]
    if cands:
        cands.sort(key=lambda kv: len(kv[0]))
        return cands[0][1]
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not ENTRIES.exists():
        sys.exit(f"缺 {ENTRIES}，先跑 parse_book.py")

    entries = json.loads(ENTRIES.read_text(encoding="utf-8"))
    idx = build_index(entries)

    src = ROOT / "content" / f"day-{args.day}" / "words.json"
    data = json.loads(src.read_text(encoding="utf-8"))

    hit = miss = 0
    diffs = []

    for w in data["words"]:
        e = lookup(w["w"], idx)
        if not e:
            miss += 1
            continue
        hit += 1

        old_ipa, old_cn = w.get("ipa", ""), w.get("cn", "")
        if e.get("ipa"):
            w["ipa"] = e["ipa"]
        if e.get("cn"):
            w["cn"] = e["cn"]
        if e.get("mnemonic"):
            w["mnemonic"] = e["mnemonic"]
        if e.get("zhenti"):
            w["zhenti"] = e["zhenti"]
        if e.get("derived"):
            w["derived"] = e["derived"]

        if old_cn != w.get("cn") or old_ipa != w.get("ipa"):
            diffs.append((w["w"], old_cn, w.get("cn", "")))

    print(f"命中书里词条: {hit}/{len(data['words'])}")
    if miss:
        print(f"书中未找到: {[w['w'] for w in data['words'] if not lookup(w['w'], idx)]}")

    if diffs and args.dry_run:
        print(f"\n释义/音标有差异的 {len(diffs)} 个（书里为准）：")
        for w, old, new in diffs[:12]:
            print(f"  {w}")
            print(f"    原: {old[:60]}")
            print(f"    书: {new[:60]}")
        return

    if args.dry_run:
        return

    src.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"已更新 {src.relative_to(ROOT)}")
    n_mn = sum(1 for w in data["words"] if w.get("mnemonic"))
    n_zt = sum(1 for w in data["words"] if w.get("zhenti"))
    print(f"  含记忆法: {n_mn}  含真题: {n_zt}")


if __name__ == "__main__":
    main()
