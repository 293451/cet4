# -*- coding: utf-8 -*-
"""
微信推送（PushPlus）—— **本地版**。

和云端版 `push_web.py` 的唯一区别：token 从 `.secrets/` 读，
云端版从环境变量读（GitHub Secrets 注入）。

⚠️ **消息内容一律委托给 push_web.py 构造**，本文件不再自己拼 HTML。

为什么改：这里原来有一份独立的 `build_msg`，和 push_web.py 各写各的。
结果云端推送加了总目录和今日复习、本地这份**一直没有** ——
两条路径行为不一致（错误日志 #13 的同类教训：
同一逻辑实现两遍，必然漂移）。

用法：
    python build/push.py --day 01 --url https://xxx/day-01.html
    python build/push.py --day 01 --url https://xxx --dry-run

token 读取顺序：.secrets/pushplus.token -> 环境变量 PUSHPLUS_TOKEN
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from push_web import build_msg  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
API = "http://www.pushplus.plus/send"


def load_token() -> str:
    f = ROOT / ".secrets" / "pushplus.token"
    if f.exists():
        t = f.read_text(encoding="utf-8").strip()
        if t:
            return t
    t = os.environ.get("PUSHPLUS_TOKEN", "").strip()
    if not t:
        sys.exit("找不到 PushPlus token：请写入 .secrets/pushplus.token")
    return t


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
    ap.add_argument("--url", required=True,
                    help="页面链接前缀，如 https://293451.github.io/cet4")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    base = args.url.rstrip("/")
    # 如果传进来的是完整页面链接（.../day-01.html），取它的前缀
    if base.endswith(".html"):
        base = base.rsplit("/", 1)[0]

    title, content = build_msg(args.day)
    body = (content.replace("__URL__", f"{base}/day-{args.day}.html")
                   .replace("__INDEX__", f"{base}/index.html")
                   .replace("__BASE__", base))

    if args.dry_run:
        print(f"标题：{title}")
        print("正文：")
        print(body)
        return
    send(load_token(), title, body)


if __name__ == "__main__":
    main()

