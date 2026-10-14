# -*- coding: utf-8 -*-
"""
每日自动任务：算出今天该学第几天 -> 生成 -> 推送。

「今天是第几天」= (今天 - start_date).days + 1
所以电脑没开、错过某天也不会乱 —— 下次跑时按真实日期算，
漏掉的会一次性补齐（补跑多天，不会跳错天）。

用法：
    python build/daily.py                # 正常跑（生成 + 推送）
    python build/daily.py --dry-run      # 只报要做什么，不执行
    python build/daily.py --force 05     # 强制跑某天
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
STATE = ROOT / "progress.json"


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}")


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    sys.exit("缺 progress.json，先跑：python build/progress.py --done 01")


def base_url() -> str:
    f = ROOT / ".secrets" / "base_url.txt"
    if f.exists():
        u = f.read_text(encoding="utf-8").strip()
        if u:
            return u.rstrip("/")
    return ""


def content_ready(day: str) -> bool:
    return (ROOT / "content" / f"day-{day}" / "words.json").exists()


def already_built(day: str) -> bool:
    return (ROOT / "docs" / f"day-{day}.html").exists()


def run(cmd: list[str]) -> bool:
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    for line in (r.stdout or "").splitlines():
        if line.strip():
            print("    " + line.strip())
    if r.returncode != 0:
        print("    [stderr] " + (r.stderr or "")[-600:])
    return r.returncode == 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", metavar="DAY")
    args = ap.parse_args()

    st = load_state()
    start = date.fromisoformat(st["start_date"])
    today = date.today()

    # 今天该学第几天
    if args.force:
        target = int(args.force)
    else:
        target = (today - start).days + 1

    if target < 1:
        log(f"还没到开课日期（{start}），今天不用学。")
        return

    # 补跑：找出所有「准备了内容、但还没生成页面」的天
    pending = []
    for n in range(1, target + 1):
        d = f"{n:02d}"
        if content_ready(d) and not already_built(d):
            pending.append(d)

    # 没有待生成的天：说明页面早就做好了（内容+音频都已提交）。
    # 这时**仍然要推送当天的那一页** —— 否则「页面已备好但没推」的场景会静默跳过。
    if not pending:
        today_day = f"{target:02d}"
        page = ROOT / "docs" / f"day-{today_day}.html"
        if not page.exists():
            log(f"今天该学 Day {today_day}，但页面不存在（内容也没准备）。")
            log("（内容需提前准备：把 content/day-XX/words.json 放好）")
            return
        log(f"今天该学 Day {today_day}，页面已就绪，直接推送。")
        if args.dry_run:
            return
        base = base_url()
        if not base:
            log("未配置 .secrets/base_url.txt，跳过推送。")
            return
        run([sys.executable, str(BUILD / "push.py"), "--day", today_day,
             "--url", f"{base}/day-{today_day}.html"])
        return

    log(f"目标 Day {target:02d}；待生成 {len(pending)} 天：{', '.join(pending)}")

    if args.dry_run:
        for d in pending:
            log(f"  将要生成 Day {d}")
        return

    base = base_url()
    built = []
    for d in pending:
        log(f"生成 Day {d} ...")
        if run([sys.executable, str(BUILD / "make.py"), "--day", d, "--no-slow"]):
            built.append(d)
        else:
            log(f"  Day {d} 生成失败，跳过")

    if not built:
        log("没有任何一天生成成功。")
        return

    # 推送：只推最新的一天（补跑多天时不刷屏）
    latest = built[-1]
    if not base:
        log("未配置 .secrets/base_url.txt，跳过推送。")
        log(f"  页面已就绪：docs/day-{latest}.html")
        return

    url = f"{base}/day-{latest}.html"
    log(f"推送 Day {latest} -> {url}")
    run([sys.executable, str(BUILD / "push.py"), "--day", latest, "--url", url])

    # 记录进度
    for d in built:
        run([sys.executable, str(BUILD / "progress.py"), "--done", d])

    log(f"完成。本次生成 {len(built)} 天，推送 Day {latest}。")


if __name__ == "__main__":
    main()
