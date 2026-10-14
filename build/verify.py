# -*- coding: utf-8 -*-
"""验收：逐天检查目标词高亮覆盖率、句子对、记忆法/真题数量"""
import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent

_SUFFIXES = ("ically", "ation", "ingly", "edly", "ness", "ment",
             "ing", "ies", "ied", "ed", "es", "s", "ly", "y", "e")


def _strip(w: str) -> str:
    w = w.lower()
    for suf in _SUFFIXES:
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def match(token: str, targets: list[dict]):
    t = re.sub(r"[^a-z]", "", token.lower())
    if len(t) < 3:
        return None
    for w in targets:
        if re.sub(r"[^a-z]", "", w["w"].lower()) == t:
            return w
    t_stem = _strip(t).replace("i", "y")
    for w in targets:
        base = re.sub(r"[^a-z]", "", w["w"].lower())
        if len(base) < 3:
            continue
        if _strip(base).replace("i", "y") == t_stem or base.replace("i", "y") == t_stem:
            return w
    for w in targets:
        base = re.sub(r"[^a-z]", "", w["w"].lower())
        if len(base) < 3:
            continue
        b = _strip(base).replace("i", "y")
        a, bb = (t_stem, b) if len(t_stem) <= len(b) else (b, t_stem)
        if len(a) >= 4 and bb.startswith(a) and len(bb) - len(a) <= 4:
            return w
    return None


days = sorted(p.name.split("-")[1] for p in (ROOT / "content").glob("day-*"))
print(f"{'Day':<5}{'句子对':>6}{'词':>6}{'记忆法':>7}{'真题':>6}{'目标词':>10}{'残留':>6}")
print("-" * 50)

tok = tot = 0
bad = []
for d in days:
    hp = ROOT / "docs" / f"day-{d}.html"
    if not hp.exists():
        print(f"{d:<5}  (未渲染)")
        continue
    h = hp.read_text(encoding="utf-8")
    data = json.loads((ROOT / "content" / f"day-{d}" / "words.json").read_text(encoding="utf-8"))

    ws = re.findall(r'class="w(?: target)?"[^>]*>([^<]+)<', h)
    hit = set()
    for x in ws:
        m = match(x, data["words"])
        if m:
            hit.add(m["w"])
    miss = [w["w"] for w in data["words"] if w["w"] not in hit]
    n = len(data["words"])
    tok += n - len(miss)
    tot += n
    if miss:
        bad.append((d, miss))

    print(
        f"{d:<5}{h.count('class=\"pair\"'):>6}{len(ws):>6}"
        f"{h.count('class=\"mnem\"'):>7}{h.count('class=\"zt\"'):>6}"
        f"{f'{n-len(miss)}/{n}':>10}{len(re.findall(r'@@[A-Z_]+@@', h)):>6}"
    )

print("-" * 50)
print(f"目标词覆盖总计：{tok}/{tot} = {tok/tot*100:.1f}%")
if bad:
    for d, miss in bad:
        print(f"  Day {d} 未覆盖: {miss}")
else:
    print("全部覆盖 ✓")
