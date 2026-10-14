# -*- coding: utf-8 -*-
"""
单日内容自检。子 Agent 提交前必须跑通。

检查项：
  1. JSON 可解析、必需字段齐全
  2. words 数量与任务文件一致、顺序一致
  3. 30 个目标词全部出现在 tts_text 里
  4. sentences 拼起来和 tts_text 逐词一致
  5. sentences 与 sentences_cn 数量相等
  6. 每个词都有 sentence / root / family
  7. 书的字段（ipa/cn/mnemonic/zhenti）没被篡改

用法：
    python build/check_day.py --day 09
    python build/check_day.py --range 09-15
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
SUFFIXES = ("ically", "ation", "ingly", "edly", "ness", "ment",
            "ing", "ies", "ied", "ed", "es", "s", "ly", "e")


def _strip(w: str) -> str:
    """
    剥掉常见后缀得词干。

    ⚠️ 两个容易搞错的地方：

    1. `-y` **不能剥**。英语里 y→i 的变形很常见（apply→applied, reply→replied）。
       如果把 apply 剥成 app、applied 剥成 appl，两边就永远对不上。
       保留 y，让 apply→apply、applied→appli 走下面的 y/i 归一。
    2. `-e` 要剥（revolve→revolv，才能和 revolved→revolv 对上）。
    """
    w = w.lower()
    for s in SUFFIXES:
        if len(w) > len(s) + 2 and w.endswith(s):
            return w[: -len(s)]
    return w


def _fold(s: str) -> str:
    """把 y/i 归一 —— apply/applied、notify/notified 靠这个对上"""
    return s.replace("i", "y")


def norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


def appears(target: str, text_words: set[str]) -> bool:
    """目标词是否以任意变形出现在文章里"""
    n = norm(target)
    if not n:
        return False
    if n in text_words:
        return True
    stem = _strip(n).replace("i", "y")
    for t in text_words:
        if t == n:
            return True
        if _strip(t).replace("i", "y") == stem:
            return True
        a, b = (stem, _strip(t).replace("i", "y"))
        if len(a) >= 4 and (a.startswith(b) or b.startswith(a)) and abs(len(a) - len(b)) <= 3:
            return True
    return False


def check(day: str) -> list[str]:
    errs: list[str] = []
    cf = ROOT / "content" / f"day-{day}" / "words.json"
    tf = ROOT / "_task" / f"day-{day}.words.json"

    if not cf.exists():
        return [f"缺文件 {cf.relative_to(ROOT)}"]
    try:
        d = json.loads(cf.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"JSON 解析失败：{e}"]

    # 必需字段
    for k in ("day", "title", "title_cn", "tts_text", "sentences", "sentences_cn", "words"):
        if k not in d or not d[k]:
            errs.append(f"缺字段或为空：{k}")

    ws = d.get("words", [])
    text = d.get("tts_text", "")

    # 词数（30 为主；个别天会多 1 个，仍算合格）
    if not (30 <= len(ws) <= 31):
        errs.append(f"words 数量 {len(ws)}，应为 30（或 31）")

    # 注：不再检查「目标词互相包含」。
    #
    # 曾经加过这个检查，但它会误伤 normal 情况：书的编排本身就是按词族走的
    # （special / speciality / specialist 同一天出现很正常），
    # 加了之后通过率从 43/45 掉到 14/45 —— 全是假警报。
    # 真正的风险（文章里出现 target 之外的词被误判）已经由 render.py 的
    # match_target 用「最优匹配」处理掉了，不需要在这里拦。

    # 和任务文件对齐
    if tf.exists():
        t = json.loads(tf.read_text(encoding="utf-8"))
        tw = [x["w"] for x in t["words"]]
        cw = [x["w"] for x in ws]
        if cw != tw[: len(cw)]:
            diff = [(i, a, b) for i, (a, b) in enumerate(zip(cw, tw)) if a != b][:5]
            errs.append(f"词表与任务不一致，前 5 处差异：{diff}")
        # 书的字段未被篡改
        for src, mine in zip(t["words"], ws):
            for k in ("ipa", "cn", "mnemonic", "zhenti"):
                if src.get(k) and mine.get(k) != src.get(k):
                    errs.append(f"{src['w']} 的 {k} 被改动了（应原样复制）")
                    break

    # 目标词覆盖
    text_words = {norm(w) for w in re.findall(r"[A-Za-z][A-Za-z'-]*", text)}
    miss = [w["w"] for w in ws if not appears(w["w"], text_words)]
    if miss:
        errs.append(f"未出现在文章里：{miss}")

    # 句子拼接
    sents = d.get("sentences", [])
    cns = d.get("sentences_cn", [])
    if len(sents) != len(cns):
        errs.append(f"sentences {len(sents)} 条 vs sentences_cn {len(cns)} 条，数量不等")
    joined = [norm(x) for x in " ".join(sents).split() if norm(x)]
    orig = [norm(x) for x in text.split() if norm(x)]
    if joined != orig:
        # 找首个差异
        for i in range(max(len(joined), len(orig))):
            a = joined[i] if i < len(joined) else "<缺>"
            b = orig[i] if i < len(orig) else "<多>"
            if a != b:
                errs.append(f"sentences 与 tts_text 不一致 @第{i}词：sentences={a!r} tts={b!r}")
                break

    # 每词必备字段
    for w in ws:
        for k in ("sentence", "root", "family"):
            if not w.get(k):
                errs.append(f"{w['w']} 缺 {k}")
                break

    # sentence 必须真的出现在正文里
    #
    # 这条是子 Agent 反馈后补的：它中途改了正文，但没同步改 sentence，
    # 词卡就会显示一句文章里根本不存在的话。原来的检查项覆盖不到。
    flat = norm(text)
    for w in ws:
        s = w.get("sentence", "")
        if s and norm(s) not in flat:
            errs.append(f"{w['w']} 的 sentence 不在正文里：{s[:50]!r}")

    # 词数合理
    n = len(orig)
    if not (150 <= n <= 320):
        errs.append(f"文章 {n} 词，超出 150-320 范围")

    return errs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day")
    ap.add_argument("--range")
    args = ap.parse_args()

    if args.range:
        a, b = args.range.split("-")
        days = [f"{i:02d}" for i in range(int(a), int(b) + 1)]
    elif args.day:
        days = [args.day]
    else:
        sys.exit("请指定 --day 09 或 --range 09-15")

    ok = 0
    for d in days:
        errs = check(d)
        if errs:
            print(f"✗ Day {d}")
            for e in errs[:8]:
                print(f"    {e}")
        else:
            print(f"✓ Day {d}")
            ok += 1
    print(f"\n通过 {ok}/{len(days)}")
    if ok < len(days):
        sys.exit(1)


if __name__ == "__main__":
    main()
