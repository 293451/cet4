# -*- coding: utf-8 -*-
"""
把 content/day-XX 和 docs/audio/day-XX 渲染成一个自包含的 HTML 页面。

核心体验：
  - 音频播放时，念到的词实时高亮（卡拉OK式跟读）
  - 目标词常亮橙色
  - 点任意单词 -> 音频跳到那个词
  - 语速 1x / 0.75x 切换
  - 手机优先，微信内置浏览器可直接打开

用法：
    python build/render.py --day 01
    python build/render.py --all
"""
from __future__ import annotations

import argparse
import html
import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent


# ── 词形匹配 ──────────────────────────────────────────────
def stem(s: str) -> str:
    """
    粗词干化，用来把「目标词」和「文章里实际出现的变形」对上。

    inform -> informed / notify -> notified / perform -> performed
    revolve -> revolved / involve -> involved

    注意：只去后缀、不加后缀。所以 revolve 和 revolved 都会归到 revolv，
    但 rely 和 relied 会分别归到 rely / reli —— 靠下面的前缀匹配兜住。
    """
    s = s.lower()
    for suf in ("ically", "ation", "ingly", "edly", "ing", "ies", "ied",
                "ed", "es", "s", "ly", "y", "e"):
        if len(s) > len(suf) + 2 and s.endswith(suf):
            s = s[: -len(suf)]
            break
    return s


_SUFFIXES = ("ically", "ation", "ingly", "edly", "ness", "ment",
             "ing", "ies", "ied", "ed", "es", "s", "ly", "e")


def _strip(word: str) -> str:
    """
    剥掉常见后缀，得到词干。只剥一次，避免把词干削得太狠。

    ⚠️ `-ied` 要还原成 `y`，不能直接删：
        buried ← bury，如果删成 'bur' 就和 bury 对不上了。
        同理 -ies → y（carries ← carry）。
    ⚠️ `-y` 本身**不能剥**（apply→applied 这类变形靠 y/i 归一兜，剥了就永远对不上）。
    """
    w = word.lower()
    # 先处理 -ied / -ies：还原成 y
    for suf in ("ied", "ies"):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[: -len(suf)] + "y"
    for suf in _SUFFIXES:
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def match_target(token: str, targets: list[dict]) -> dict | None:
    """
    判断文章里的一个词是否命中某个目标词。

    三步走，顺序很重要：
      ① 完全相同 —— 优先。否则 mass 会被 massive/massage 抢先判定，
         而它自己反而标不中。
      ② 一方剥后缀后等于另一方 —— 兜住 motivating/motivate、informed/inform
      ③ 剥后缀后一方是另一方的前缀 —— 兜住较松的变形

    长度下限取 3：早年设成 4，dry 这种三字母词整批漏标。
    另把 y↔i 归一，兜住 notify→notified。

    踩过的坑：曾用「长度差 ≤ N」判断，但 motivate→motivating 是**变长**，
    motivate 不是 motivating 的前缀，判据根本不成立。必须先剥后缀。
    """
    t = re.sub(r"[^a-z]", "", token.lower())
    if len(t) < 3:
        return None

    # ① 精确
    for w in targets:
        if re.sub(r"[^a-z]", "", w["w"].lower()) == t:
            return w

    t_stem = _strip(t)
    t_fold = t.replace("i", "y")
    t_stem_fold = t_stem.replace("i", "y")

    # ② 剥后缀后相等 / ③ 剥后缀后前缀匹配
    #
    # 这里要选**最接近**的目标词，而不是第一个碰上的。
    # 反例：文章里有 complicate / compound / complex，目标词也有这三个。
    # 如果按顺序第一个命中就返回，complicate 会被 compound 抢走，
    # 结果 complicate 自己反而标不中（实测 Day 31 就是这样）。
    # 所以给每个候选打分，取分最高的。
    best = None
    best_score = -1
    for w in targets:
        base = re.sub(r"[^a-z]", "", w["w"].lower())
        if len(base) < 3:
            continue
        b_fold = base.replace("i", "y")
        b_stem = _strip(base).replace("i", "y")

        score = -1
        if b_stem == t_stem_fold or b_fold == t_stem_fold:
            score = 100 - abs(len(base) - len(t))          # 完全匹配，长度越近越好
        elif b_fold == t_fold:
            score = 95 - abs(len(base) - len(t))
        else:
            a, b = (t_stem_fold, b_stem) if len(t_stem_fold) <= len(b_stem) else (b_stem, t_stem_fold)
            if len(a) >= 4 and b.startswith(a) and len(b) - len(a) <= 4:
                score = 50 - (len(b) - len(a))

        if score > best_score:
            best, best_score = w, score
    return best


# ── HTML 片段 ─────────────────────────────────────────────
def render_article(
    merged: list[dict], targets: list[dict], sentences: list[str], cns: list[str]
) -> str:
    """
    逐句渲染：英文句 + 中文句紧跟其后。

    为什么这么改：原来英文和中文分成两大块，英文有 14000+ 字符、
    中文才 400 多字符挤成一坨。读英文时译文在很远的下方，边听边对照根本对不上。
    改成逐句对照后，听到哪句、译文就在眼皮底下。

    按 sentences 的词数把 merged（逐词时间戳）切分成一句一组。
    """
    groups: list[list[dict]] = []
    pos = 0
    for sent in sentences:
        n = len(sent.split())
        groups.append(merged[pos : pos + n])
        pos += n
    # 多出来的词（理论上不该有）并到最后一句，避免丢词
    if pos < len(merged):
        if groups:
            groups[-1].extend(merged[pos:])
        else:
            groups.append(merged[pos:])

    out: list[str] = []
    for gi, group in enumerate(groups):
        if not group:
            continue
        spans = []
        for w in group:
            t = html.escape(w["text"])
            info = match_target(w["text"], targets)
            cls = "w target" if info else "w"
            title = f' title="{html.escape(info["cn"])}"' if info else ""
            spans.append(
                f'<span class="{cls}" data-s="{w["start"]:.0f}" '
                f'data-e="{w["end"]:.0f}"{title}>{t}</span>'
            )
        s0 = group[0]["start"]
        s1 = group[-1]["end"]
        zh = html.escape(cns[gi]) if gi < len(cns) else ""
        out.append(
            f'<div class="pair" data-s0="{s0:.0f}" data-s1="{s1:.0f}">'
            f'<p class="en">{" ".join(spans)}</p>'
            f'<p class="zh">{zh}</p>'
            f"</div>"
        )
    return "\n".join(out)


def render_wordlist(words: list[dict]) -> str:
    rows = []
    for i, w in enumerate(words, 1):
        blocks = []
        # ① 课文原句 —— 先看它在你今天读的文章里长什么样
        if w.get("sentence"):
            blocks.append(
                f'<div class="sent"><span class="lbl">课文</span>'
                f'{html.escape(w["sentence"])}</div>'
            )
        # ② 刘晓燕的记忆法 —— 书里的原文，最有价值
        if w.get("mnemonic"):
            blocks.append(
                f'<div class="mnem"><span class="lbl">记</span>'
                f'{html.escape(w["mnemonic"])}</div>'
            )
        # ③ 词根拆解（我补的）
        if w.get("root"):
            blocks.append(
                f'<div class="root"><span class="lbl">根</span>'
                f'{html.escape(w["root"])}</div>'
            )
        # ④ 真题例句 —— 书里的原句，考试就考这个难度
        if w.get("zhenti"):
            blocks.append(
                f'<div class="zt"><span class="lbl">真题</span>'
                f'{html.escape(w["zhenti"])}</div>'
            )
        if w.get("collocation"):
            blocks.append(
                f'<div class="colloc"><span class="lbl">搭</span>'
                f'{html.escape(w["collocation"])}</div>'
            )
        if w.get("family"):
            blocks.append(
                f'<div class="fam"><span class="lbl">族</span>'
                f'{html.escape(w["family"])}</div>'
            )

        rows.append(f"""      <details class="card">
        <summary>
          <span class="idx">{i:02d}</span>
          <span class="word">{html.escape(w['w'])}</span>
          <span class="ipa">{html.escape(w.get('ipa',''))}</span>
          <span class="pos">{html.escape(w.get('pos',''))}</span>
          <span class="cn">{html.escape(w['cn'])}</span>
        </summary>
        <div class="body">
          {chr(10) + "          ".join(blocks)}
        </div>
      </details>""")
    return "\n".join(rows)


TEMPLATE = (Path(__file__).resolve().parent / "templates" / "page.html").read_text(encoding="utf-8")


def run_day(day: str) -> bool:
    cdir = ROOT / "content" / f"day-{day}"
    src = cdir / "words.json"
    wjson = ROOT / "docs" / "audio" / f"day-{day}.words.json"

    if not src.exists():
        print(f"  [跳过] {src} 不存在")
        return False
    if not wjson.exists():
        print(f"  [跳过] 先跑 tts.py 生成 {wjson.name}")
        return False

    data = json.loads(src.read_text(encoding="utf-8"))
    ts = json.loads(wjson.read_text(encoding="utf-8"))

    # Day 01 对应起始日，之后逐日累加
    from datetime import date, timedelta

    start = date.today()
    prog = ROOT / "progress.json"
    if prog.exists():
        try:
            start = date.fromisoformat(
                json.loads(prog.read_text(encoding="utf-8"))["start_date"]
            )
        except Exception:
            pass
    day_date = start + timedelta(days=int(day) - 1)
    date_label = f"{day_date.month}/{day_date.day}"

    page = TEMPLATE
    for k, v in {
        "DAY": day,
        "DATE": date_label,
        "TITLE": html.escape(data["title"]),
        "TITLE_CN": html.escape(data["title_cn"]),
        "UNIT": data.get("unit", ""),
        "RANGE": data.get("range", ""),
        "ARTICLE": render_article(
            ts["words"], data["words"],
            data.get("sentences", []), data.get("sentences_cn", []),
        ),
        "NWORDS": str(len(data["words"])),
        "WORDLIST": render_wordlist(data["words"]),
    }.items():
        page = page.replace(f"@@{k}@@", v)

    out = ROOT / "docs" / f"day-{day}.html"
    out.write_text(page, encoding="utf-8")
    kb = len(page.encode()) / 1024
    print(f"  -> docs/day-{day}.html  ({kb:.0f} KB, {len(ts['words'])} 词)")
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    days = (
        sorted(p.name.split("-")[1] for p in (ROOT / "content").glob("day-*"))
        if args.all
        else [args.day]
    )
    if not days or days == [None]:
        sys.exit("请指定 --day 01 或 --all")

    for d in days:
        run_day(d)
    print("\n完成。")


if __name__ == "__main__":
    main()
