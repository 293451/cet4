# -*- coding: utf-8 -*-
"""
把 book.txt（整本 OCR 结果）解析成结构化词条。

书里每个词条长这样：
    region /'ri:dʒən/                     <- 词 + 音标
    n. 地区;(身体)部位                     <- 词性 + 中文
    真题 There are lots of ... (2018)      <- 真题例句 + 年份
    千方百计记单词 单词发音类似"瑞金"……      <- 刘晓燕的记忆法
    【派生】regional /'ri:dʒənl/ adj. 地区的;区域的
    【短语】derive from 来自，源自

输出 book/entries.json：
    { "region": {ipa, pos, cn, zhenti, mnemonic, derived, phrase, page}, ... }

用法：
    python parse_book.py
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
BOOK = ROOT / "book" / "book.txt"
OUT = ROOT / "book" / "entries.json"

# 词条头：英文单词 + 音标（音标里可能含各种 IPA 字符）
WORD_RE = re.compile(r"^([a-zA-Z][a-zA-Z'\- ]{0,28}?)\s*/([^/]{2,45})/\s*$")

# 词性行：标准写法 + OCR 误认的形近字
#
# OCR 会把 n. 认成 11. / η. / 1. / n1. / 77. / 7. / 71.（实测统计）
# 这是形近字识别问题，不是解析逻辑问题 —— 所以要在正则层面兼容。
POS_RE = re.compile(
    r"^(n|v|vt|vi|adj|adv|prep|conj|pron|num|art|int|"
    r"11|1|77|7|71|η|n1|n1\.|1l|ll)\.\s*(.+)$"
)
# 误认形态 -> 正确词性
POS_FIX = {
    "11": "n.", "1": "n.", "77": "n.", "7": "n.", "71": "n.",
    "η": "n.", "n1": "n.", "1l": "n.", "ll": "n.",
}

# 这些是页面噪声，不是词条
NOISE = ("英语四级你还在背单词吗",)


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def split_example(cn: str) -> tuple[str, str]:
    """
    释义里常混着「例」引导的例句，把它们分开。

    形如：多才多艺的；多功能的 例 As a versatile actor, he can... 作为一名多才多艺的演员...
    分不出英文/中文哪段是例句时，整段当作释义保留（宁可多留，不要丢）。
    """
    m = re.search(r"(?:^|\s)例\s*", cn)
    if not m:
        return cn, ""
    return cn[: m.start()].strip(), cn[m.end() :].strip()


def parse() -> dict[str, dict]:
    raw = BOOK.read_text(encoding="utf-8")
    # 去掉页分隔线
    lines = []
    for ln in raw.split("\n"):
        if ln.startswith("===") or set(ln.strip()) == {"="}:
            continue
        lines.append(ln)

    entries: dict[str, dict] = {}
    cur: dict | None = None
    mode: str | None = None  # 当前在收集哪个字段

    def flush():
        nonlocal cur
        if cur and cur.get("w"):
            # 释义里混进的「例」例句拆出来
            if cur.get("cn"):
                pure, ex = split_example(cur["cn"])
                cur["cn"] = pure
                if ex and not cur.get("example"):
                    cur["example"] = ex
            w = cur["w"]
            # 重复词条：保留信息更全的那个
            old = entries.get(w)
            if old is None or len(str(cur)) > len(str(old)):
                entries[w] = cur
        cur = None

    for ln in lines:
        t = ln.strip()
        if not t or t in NOISE:
            continue

        # 1) 词条头
        m = WORD_RE.match(t)
        if m:
            w = m.group(1).strip().lower()
            # 过滤掉误匹配（太长、含常见句子词）
            if 1 < len(w) <= 24 and " " not in w.rstrip():
                flush()
                cur = {"w": w, "ipa": "/" + m.group(2).strip() + "/"}
                mode = None
                continue

        if cur is None:
            continue

        # 2) 词性 + 中文释义
        pm = POS_RE.match(t)
        if pm:
            if "pos" not in cur:
                cur["pos"] = POS_FIX.get(pm.group(1), pm.group(1) + ".")
                cur["cn"] = clean(pm.group(2))
            else:
                cur["cn"] = clean(cur.get("cn", "") + " " + t)
            mode = "cn"
            continue

        # 3) 真题例句
        if t.startswith("真题"):
            cur["zhenti"] = clean(t[2:])
            mode = "zhenti"
            continue

        # 4) 千方百计记单词（刘晓燕的记忆法）
        if t.startswith("千方百计记单词"):
            cur["mnemonic"] = clean(t.replace("千方百计记单词", "", 1))
            mode = "mnemonic"
            continue

        # 5) 【派生】
        if t.startswith("【派生】"):
            cur["derived"] = clean(t.replace("【派生】", "", 1))
            mode = "derived"
            continue

        # 6) 【短语】
        if t.startswith("【短语】"):
            cur["phrase"] = clean(t.replace("【短语】", "", 1))
            mode = "phrase"
            continue

        # 7) 续行：接到当前字段后面
        if mode in ("zhenti", "mnemonic", "derived", "phrase", "cn"):
            key = "cn" if mode == "cn" else mode
            cur[key] = clean(cur.get(key, "") + " " + t)

    flush()
    return entries


def main() -> None:
    if not BOOK.exists():
        sys.exit(f"缺 {BOOK}，先跑 ocr_book.py")

    entries = parse()
    print(f"解析出 {len(entries)} 个词条")

    # 统计字段覆盖
    for k in ("ipa", "cn", "zhenti", "mnemonic", "derived", "phrase"):
        n = sum(1 for e in entries.values() if e.get(k))
        pct = n / len(entries) * 100
        print(f"  有 {k:10s}: {n:>5}  ({pct:.0f}%)")

    OUT.write_text(
        json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"\n-> {OUT}  ({OUT.stat().st_size // 1024} KB)")

    # 抽样看几个
    print("\n=== 抽样 ===")
    for w in ("region", "derive", "versatile", "toast", "convert"):
        e = entries.get(w)
        if e:
            print(f"\n[{w}] {e.get('ipa','')} {e.get('pos','')} {e.get('cn','')}")
            if e.get("zhenti"):
                print(f"  真题: {e['zhenti'][:90]}")
            if e.get("mnemonic"):
                print(f"  记忆法: {e['mnemonic'][:90]}")


if __name__ == "__main__":
    main()
