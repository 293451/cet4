# -*- coding: utf-8 -*-
"""
一键流水线：内容 -> 配音 -> 网页。

用法：
    python build/make.py --day 01              # 跑一天
    python build/make.py --day 01 --no-tts     # 只渲染（已有音频时）
    python build/make.py --range 01-07         # 批量

流水线步骤：
    1. 检查 content/day-XX/words.json 存在且字段完整
    2. tts.py       -> docs/audio/day-XX.mp3 + .words.json（1x 和 0.75x）
    3. render.py    -> docs/day-XX.html
    4. 更新 docs/index.html（总目录）
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"

REQUIRED = ("day", "title", "title_cn", "tts_text", "sentences", "sentences_cn", "words")


def check_content(day: str) -> dict | None:
    p = ROOT / "content" / f"day-{day}" / "words.json"
    if not p.exists():
        print(f"  [跳过] 缺 {p.relative_to(ROOT)}")
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        print(f"  [跳过] day-{day} words.json 缺字段: {missing}")
        return None
    n = len(data["words"])
    if n == 0:
        print(f"  [跳过] day-{day} 没有单词")
        return None
    print(f"  Day {day} · {data['title']} · {n} 词")
    return data


def run(cmd: list[str]) -> bool:
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stdout[-1500:] if r.stdout else "")
        print(r.stderr[-1500:] if r.stderr else "")
        return False
    # 透传脚本自己的输出（缩进对齐）
    for line in (r.stdout or "").splitlines():
        if line.strip():
            print("    " + line.strip())
    return True


def build_index() -> None:
    """生成/更新总目录页"""
    days = sorted(
        p.name.split("-")[1] for p in (ROOT / "content").glob("day-*")
        if (p / "words.json").exists()
    )
    items = []
    for d in days:
        data = json.loads(
            (ROOT / "content" / f"day-{d}" / "words.json").read_text(encoding="utf-8")
        )
        has = (ROOT / "docs" / f"day-{d}.html").exists()
        cls = "" if has else ' class="pending"'
        note = "" if has else "（待生成）"
        items.append(
            f'    <a{cls} href="day-{d}.html">'
            f'<span class="n">Day {d}</span>'
            f'<span class="t">{data["title"]}</span>'
            f'<span class="c">{data["title_cn"]}</span>'
            f'<span class="w">{len(data["words"])} 词{note}</span></a>'
        )

    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>四级单词 · 每日精读</title>
<style>
:root {{ --bg:#fbfaf7; --card:#fff; --line:#e8e4dc; --ink:#23201c; --dim:#8a8279; --accent:#d97706; }}
@media (prefers-color-scheme:dark) {{
  :root {{ --bg:#1a1816; --card:#232020; --line:#3a3532; --ink:#ece7e0; --dim:#9a9188; }}
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font:16px/1.7 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif; }}
.wrap {{ max-width:720px; margin:0 auto; padding:20px 16px 60px; }}
h1 {{ font-size:23px; margin:8px 0 4px; }}
.sub {{ color:var(--dim); font-size:13.5px; margin-bottom:22px; }}
a {{ display:block; text-decoration:none; color:inherit; background:var(--card);
  border:1px solid var(--line); border-radius:12px; padding:13px 15px; margin-bottom:9px;
  transition:transform .12s, border-color .12s; }}
a:active {{ transform:scale(.985); }}
a:hover {{ border-color:var(--accent); }}
a.pending {{ opacity:.5; }}
.n {{ font-weight:650; color:var(--accent); font-size:14px; }}
.t {{ display:block; font-weight:600; margin:3px 0 1px; }}
.c {{ display:block; color:var(--dim); font-size:13.5px; }}
.w {{ display:block; color:var(--dim); font-size:12px; margin-top:4px; }}
footer {{ margin-top:26px; color:var(--dim); font-size:12.5px; text-align:center; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>四级单词 · 每日精读</h1>
  <div class="sub">刘晓燕《四级你还在背单词吗》· 每天 30 词 · 双语文章 + 逐词跟读</div>
{chr(10).join(items) if items else '  <p style="color:var(--dim)">还没有内容。</p>'}
  <footer>共 {len(days)} 天</footer>
</div>
</body>
</html>
"""
    out = ROOT / "docs" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day")
    ap.add_argument("--range", help="如 01-07")
    ap.add_argument("--no-tts", action="store_true", help="跳过配音（已有音频时）")
    ap.add_argument("--no-slow", action="store_true", help="不生成慢速版")
    args = ap.parse_args()

    if args.range:
        a, b = args.range.split("-")
        days = [f"{i:02d}" for i in range(int(a), int(b) + 1)]
    elif args.day:
        days = [args.day]
    else:
        sys.exit("请指定 --day 01 或 --range 01-07")

    ok = True
    for d in days:
        print(f"[{d}]")
        if not check_content(d):
            ok = False
            continue
        if not args.no_tts:
            if not run([sys.executable, str(BUILD / "tts.py"), "--day", d]):
                ok = False
                continue
        if not run([sys.executable, str(BUILD / "render.py"), "--day", d]):
            ok = False

    build_index()
    print(f"\n总目录已更新：docs/index.html")
    print("完成。" if ok else "\n完成，但有失败项。")


if __name__ == "__main__":
    main()
