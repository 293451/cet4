# -*- coding: utf-8 -*-
"""
还原被篡改的书本字段。

背景：子 Agent 反复自作主张给 ipa/pos/cn/mnemonic/zhenti "补全"释义，
违反了「书的字段原样复制」的规范。实测已发生 8 次。

这个脚本按 _task/ 里的原文批量还原，一条命令搞定。

用法：
    python build/restore_fields.py                # 全量还原
    python build/restore_fields.py --dry-run      # 只报告，不改
    python build/restore_fields.py --range 40-55  # 只处理某段
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
BOOK_FIELDS = ("ipa", "pos", "cn", "mnemonic", "zhenti")


def restore(days: list[str], dry: bool) -> int:
    total = 0
    for ds in days:
        cf = ROOT / "content" / f"day-{ds}" / "words.json"
        tf = ROOT / "_task" / f"day-{ds}.words.json"
        if not cf.exists() or not tf.exists():
            continue
        try:
            c = json.loads(cf.read_text(encoding="utf-8"))
            t = json.loads(tf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  Day {ds}: 读取失败 {e}")
            continue

        src = {x["w"]: x for x in t["words"]}
        changed = []
        for w in c["words"]:
            s = src.get(w["w"])
            if not s:
                continue
            for k in BOOK_FIELDS:
                if s.get(k) and w.get(k) != s.get(k):
                    changed.append(f"{w['w']}.{k}")
                    if not dry:
                        w[k] = s[k]

        if changed:
            print(f"  Day {ds}: {'；'.join(changed)}")
            total += len(changed)
            if not dry:
                cf.write_text(
                    json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8"
                )
    return total


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--range", help="如 01-55")
    args = ap.parse_args()

    if args.range:
        a, b = args.range.split("-")
        days = [f"{i:02d}" for i in range(int(a), int(b) + 1)]
    else:
        days = sorted(
            p.name.split("-")[1] for p in (ROOT / "content").glob("day-*")
        )

    print(f"检查 {len(days)} 天 ...")
    n = restore(days, args.dry_run)

    if n == 0:
        print("\n全部干净，无需还原 ✓")
    elif args.dry_run:
        print(f"\n发现 {n} 处改动（未修改，加 --dry-run 去掉即可执行）")
    else:
        print(f"\n已还原 {n} 处")


if __name__ == "__main__":
    main()
