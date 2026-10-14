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
    args = ap.parse_args()

    token = os.environ.get("PUSHPLUS_TOKEN", "").strip()
    base = os.environ.get("BASE_URL", "").strip().rstrip("/")
    if not token:
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
    ok = send(token, title, content.replace("__URL__", url))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
