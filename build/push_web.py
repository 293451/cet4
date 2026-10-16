# -*- coding: utf-8 -*-
"""
GitHub Actions 专用的推送脚本。

和 build/push.py 的区别：
  本地版从 .secrets/ 读 token，云端版从环境变量读（GitHub Secrets 注入）。
  其余逻辑一致。

环境变量：
    PUSHPLUS_TOKEN   PushPlus 令牌（GitHub Secret）
    BASE_URL         页面地址前缀，如 https://293451.github.io/cet4

用法：
    python build/push_web.py                  # 自动算今天该推第几天
    python build/push_web.py --day 09         # 指定
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
API = "http://www.pushplus.plus/send"


def today_day() -> int | None:
    """按 progress.json 的 start_date 算今天该学第几天"""
    pf = ROOT / "progress.json"
    if not pf.exists():
        return None
    st = json.loads(pf.read_text(encoding="utf-8"))
    start = date.fromisoformat(st["start_date"])
    n = (date.today() - start).days + 1
    return n if n >= 1 else None


def build_catalog(current: str) -> str:
    """
    生成「总目录」HTML 片段，附在每日推送底部。

    为什么放在同一条消息里（而不是单独推一条）：
      每天收两条消息会让人烦，且总目录单独一条很快就被后面的消息淹没。
      合并成一条 —— 「今天的文章」和「在整本书里的位置」本来是同一件事。

    设计要点：
      1. **必须标出「你在哪里」** —— 69 天的平铺列表只是噪音，
         用户扫一眼要能立刻看到自己的进度，以及前后几天叫什么。
      2. **每 10 天一块折叠** —— 一次列 69 行没人会看。
         当前那块展开（能看到相邻几天的标题），其余块只给一行摘要。

    ⚠️ **不按 `unit` 字段分组**：那个字段实测不可靠 ——
       每天都不一样（'Unit 1'、'Unit 1~2'、'Unit 3'…），
       而且顺序是乱的（Day 03 是 Unit 3，Day 09 却是 Unit 2）。
       按它分组等于每天一组，毫无意义。
       改用「10 天一块」，跟「今天第 N 天」直接对得上，稳定可预测。
    """
    days = sorted(
        p.name.split("-")[1] for p in (ROOT / "content").glob("day-*")
        if (p / "words.json").exists()
    )
    if not days:
        return ""

    cur = int(current)
    # 收集每天的信息
    info = []
    for d in days:
        try:
            x = json.loads(
                (ROOT / "content" / f"day-{d}" / "words.json").read_text(encoding="utf-8")
            )
        except Exception:
            continue
        info.append({
            "day": d,
            "n": int(d),
            "title_cn": x.get("title_cn", ""),
        })
    if not info:
        return ""

    # 每 10 天一块
    BLOCK = 10
    blocks: list[list[dict]] = []
    for it in info:
        bi = (it["n"] - 1) // BLOCK
        while len(blocks) <= bi:
            blocks.append([])
        blocks[bi].append(it)
    blocks = [b for b in blocks if b]

    done = sum(1 for it in info if it["n"] < cur)

    parts = [
        '<div style="margin-top:18px;padding-top:14px;border-top:1px solid #eee">',
        '<p style="font-size:14px;margin:0 0 8px"><b>📖 总目录</b>'
        f'<span style="color:#999;font-size:12.5px">'
        f'　共 {len(info)} 天 · 已学 {done} 天 · 今天第 {cur} 天</span></p>',
    ]

    for b in blocks:
        nums = [it["n"] for it in b]
        has_cur = cur in nums
        label = f'Day {b[0]["day"]}-{b[-1]["day"]}'

        if has_cur:
            # 当前这块：展开，标出今天。已学/未学用颜色区分
            rows = []
            for it in b:
                n = it["n"]
                if n == cur:
                    mark, style = "▶ ", "color:#d97706;font-weight:650"
                elif n < cur:
                    mark, style = "✅ ", "color:#bbb"
                else:
                    mark, style = "　 ", "color:#666"
                rows.append(
                    f'<div style="{style};font-size:13px;line-height:1.75">'
                    f'{mark}Day {it["day"]}　{it["title_cn"]}</div>'
                )
            parts.append(
                f'<p style="font-size:13.5px;margin:10px 0 4px;font-weight:600">'
                f'{label}</p>' + "".join(rows)
            )
        else:
            mark = "✅" if max(nums) < cur else "　"
            parts.append(
                f'<p style="font-size:13px;margin:6px 0;color:#999">'
                f'{mark} {label}</p>'
            )

    parts.append(
        '<p style="margin-top:12px"><a href="__INDEX__" '
        'style="color:#d97706;font-size:14px">查看完整总目录 →</a></p>'
    )
    parts.append("</div>")
    return "\n".join(parts)


def build_msg(day: str) -> tuple[str, str]:
    p = ROOT / "content" / f"day-{day}" / "words.json"
    if not p.exists():
        sys.exit(f"缺 {p.relative_to(ROOT)}")
    d = json.loads(p.read_text(encoding="utf-8"))
    words = [w["w"] for w in d["words"]]
    preview = " · ".join(words[:6]) + (" …" if len(words) > 6 else "")
    n = len(words)

    title = f"Day {day} · {d['title_cn']}"
    content = f"""<div style="font-size:15px;line-height:1.8">
<p><b>{d['title']}</b><br>
<span style="color:#888;font-size:13px">{d['title_cn']}</span></p>
<p style="color:#888;font-size:13px">今日 {n} 词：{preview}</p>
<p><a href="__URL__" style="display:inline-block;background:#d97706;color:#fff;
padding:10px 18px;border-radius:8px;text-decoration:none;font-size:15px">
▶ 打开精读页面</a></p>
<p style="color:#aaa;font-size:12px">
可播放朗读、逐词跟读高亮、点词跳转、切换 0.75x 慢速。</p>
{build_catalog(day)}
</div>"""
    return title, content


def send(token: str, title: str, content: str) -> bool:
    payload = {"token": token, "title": title, "content": content,
               "template": "html", "channel": "wechat"}
    req = urllib.request.Request(
        API, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            res = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:200]}")
        return False
    if res.get("code") == 200:
        print(f"推送成功：{title}")
        return True
    print(f"推送失败：{res}")
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day")
    ap.add_argument("--dry-run", action="store_true",
                    help="只打印消息内容，不真发（用来预览排版）")
    args = ap.parse_args()

    token = os.environ.get("PUSHPLUS_TOKEN", "").strip()
    base = os.environ.get("BASE_URL", "").strip().rstrip("/")
    if not token and not args.dry_run:
        sys.exit("缺环境变量 PUSHPLUS_TOKEN")
    if not base:
        sys.exit("缺环境变量 BASE_URL")

    day = args.day or (f"{today_day():02d}" if today_day() else None)
    if not day:
        sys.exit("算不出今天该学第几天，且没指定 --day")

    # 页面还没生成就不推（避免推个死链）
    if not (ROOT / "docs" / f"day-{day}.html").exists():
        print(f"Day {day} 页面不存在，跳过推送")
        return

    title, content = build_msg(day)
    url = f"{base}/day-{day}.html"
    index_url = f"{base}/index.html"
    body = content.replace("__URL__", url).replace("__INDEX__", index_url)

    if args.dry_run:
        print(f"标题：{title}\n")
        # 把 HTML 里的标签去掉，终端里看个大概。
        # div/p 都要换行 —— 漏了 div 的话每行会连成一坨，看不出真实排版。
        import re
        plain = re.sub(r"<br\s*/?>|</div>|</p>", "\n", body)
        plain = re.sub(r"<[^>]+>", "", plain)
        plain = re.sub(r"\n{3,}", "\n\n", plain)
        print(plain.strip()[:3000])
        return

    ok = send(token, title, body)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
