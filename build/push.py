# -*- coding: utf-8 -*-
"""
微信推送（PushPlus）。

推送内容：当天课文的标题 + 链接 + 今日词表前几个词。

用法：
    python build/push.py --day 01 --url https://xxx/day-01.html
    python build/push.py --day 01 --dry-run        # 只打印，不发送

token 读取顺序：.secrets/pushplus.token -> 环境变量 PUSHPLUS_TOKEN
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
API = "http://www.pushplus.plus/send"


def load_token() -> str:
    f = ROOT / ".secrets" / "pushplus.token"
    if f.exists():
        t = f.read_text(encoding="utf-8").strip()
        if t:
            return t
    import os

    t = os.environ.get("PUSHPLUS_TOKEN", "").strip()
    if not t:
        sys.exit("找不到 PushPlus token：请写入 .secrets/pushplus.token")
    return t


def build_msg(day: str, url: str) -> tuple[str, str]:
    """返回 (标题, 正文 HTML)"""
    p = ROOT / "content" / f"day-{day}" / "words.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    words = [w["w"] for w in data["words"]]
    preview = " · ".join(words[:6]) + (" …" if len(words) > 6 else "")

    title = f"Day {day} · {data['title_cn']}"
    content = f"""<div style="font-size:15px;line-height:1.8">
<p><b>{data['title']}</b><br>
<span style="color:#888;font-size:13px">{data['title_cn']}</span></p>

<p style="color:#888;font-size:13px">
今日 {len(words)} 词：{preview}</p>

<p><a href="{url}" style="display:inline-block;background:#d97706;color:#fff;
padding:10px 18px;border-radius:8px;text-decoration:none;font-size:15px">
▶ 打开精读页面</a></p>

<p style="color:#aaa;font-size:12px">
页面里可以播放朗读、逐词跟读高亮、点词跳转、切换 0.75x 慢速。</p>
</div>"""
    return title, content


def send(token: str, title: str, content: str) -> None:
    payload = {
        "token": token,
        "title": title,
        "content": content,
        "template": "html",
        "channel": "wechat",
    }
    req = urllib.request.Request(
        API,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            res = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode()[:300]}")

    if res.get("code") == 200:
        print(f"    推送成功：{title}")
    else:
        sys.exit(f"推送失败：{res}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True)
    ap.add_argument("--url", required=True, help="页面链接（手机能访问的）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    title, content = build_msg(args.day, args.url)
    if args.dry_run:
        print(f"标题：{title}")
        print("正文：")
        print(content)
        return
    send(load_token(), title, content)


if __name__ == "__main__":
    main()
