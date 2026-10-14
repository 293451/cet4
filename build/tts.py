# -*- coding: utf-8 -*-
"""
MiniMax T2A 配音生成器
输入：content/day-XX/words.json 里的 tts_text
输出：docs/audio/day-XX.mp3 + docs/audio/day-XX.words.json（逐词时间戳）

用法：
    python build/tts.py --day 01
    python build/tts.py --day 01 --speed 0.75    # 慢速版
    python build/tts.py --all
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
API_URL = "https://api.minimaxi.com/v1/t2a_v2"

# ── 已锁定的参数 ─────────────────────────────────────────
MODEL = "speech-2.8-hd"
VOICE = "ttv-voice-2026071823515226-uMMSm1vv"
SAMPLE_RATE = 32000
BITRATE = 128000


def load_key() -> str:
    """优先读 .secrets/minimax.key，其次读环境变量"""
    key_file = ROOT / ".secrets" / "minimax.key"
    if key_file.exists():
        k = key_file.read_text(encoding="utf-8").strip()
        if k:
            return k
    k = os.environ.get("MINIMAX_API_KEY", "").strip()
    if not k:
        sys.exit("找不到 API key：请在 .secrets/minimax.key 里填入，或设置 MINIMAX_API_KEY")
    return k


def synthesize(key: str, text: str, speed: float) -> tuple[bytes, list]:
    """调 MiniMax，返回 (mp3 字节, 音节级时间戳列表)"""
    payload = {
        "model": MODEL,
        "text": text,
        "stream": False,
        "voice_setting": {"voice_id": VOICE, "speed": speed, "vol": 1, "pitch": 0},
        "audio_setting": {
            "sample_rate": SAMPLE_RATE,
            "bitrate": BITRATE,
            "format": "mp3",
            "channel": 1,
        },
        "subtitle_enable": True,
        "subtitle_type": "word",
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            res = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode()[:300]}")

    br = res.get("base_resp", {})
    if br.get("status_code") != 0:
        sys.exit(f"MiniMax 业务失败：{br}")

    audio_hex = (res.get("data") or {}).get("audio") or ""
    if not audio_hex:
        sys.exit("MiniMax 返回音频为空")
    audio = bytes.fromhex(audio_hex)

    # 下载字幕文件拿时间戳
    sub_url = (res.get("data") or {}).get("subtitle_file")
    syllables = []
    if sub_url:
        with urllib.request.urlopen(sub_url, timeout=60) as r:
            sub = json.loads(r.read().decode())
        for seg in sub:
            syllables.extend(seg.get("timestamped_words", []))

    info = res.get("extra_info", {})
    print(f"    音频 {len(audio)/1024:.0f} KB · {info.get('audio_length', 0)/1000:.1f} 秒 "
          f"· 计费 {info.get('usage_characters')} 字符 · 音节条目 {len(syllables)}")
    return audio, syllables


def _is_word_char(c: str) -> bool:
    return c.isalnum() or c in "'’"


def merge_syllables(syllables: list, text: str) -> list[dict]:
    """
    把 MiniMax 的音节级条目还原成原文的词（用于卡拉OK式跟读高亮）。

    实测踩过的坑：
      1. 拆音节：convert -> "con" + "vert"
      2. 标点常单独成条目，还可能粘在词尾（versatile -> "versatile.She"）
      3. word_begin 偏移在长文本里会漂移——实测 476 字符处开始整体错位，
         所以偏移不可信

    改用「保序字符流对齐」：把音节的非空条目按顺序拼成一个字符流，
    再和原文的词流做双指针匹配。两流顺序必然一致，因此稳定可靠。
    每个词的时间取它第一个和最后一个音节的 time_begin / time_end。
    """
    toks = [
        {"text": m.group(), "start": m.start(), "end": m.end()}
        for m in re.finditer(r"\S+", text)
    ]
    if not toks:
        return []

    # 音节流：非空条目按顺序拼接，同时记录每个字符的起止时间
    stream_chars: list[str] = []
    stream_time: list[tuple[float, float]] = []
    for s in syllables:
        t = s.get("word", "")
        if not t.strip():
            continue
        for ch in t:
            stream_chars.append(ch)
            stream_time.append((s["time_begin"], s["time_end"]))
    stream = "".join(stream_chars)

    words: list[dict] = []
    j = 0  # 音节流指针
    for tk in toks:
        want = tk["text"]
        core = [c.lower() for c in want if _is_word_char(c)]
        if not core:
            continue

        k = 0          # 已匹配的 core 下标
        first = None   # 首个匹配字符在音节流中的位置
        last = None    # 最后一个匹配字符的位置
        while j < len(stream) and k < len(core):
            c = stream[j]
            if not _is_word_char(c):
                # 纯标点：若是词内标点（撇号已算词字符），跳过
                j += 1
                continue
            if c.lower() == core[k]:
                if first is None:
                    first = j
                last = j
                k += 1
                j += 1
            else:
                break  # 音节流和原文不同步，交给校验报错

        if k == len(core) and first is not None:
            words.append(
                {
                    "text": want,
                    "start": stream_time[first][0],
                    "end": stream_time[last][1],
                }
            )
        # 匹配失败则不推进指针，continue 到下一个词

    return words



def verify(merged: list[dict], original: str) -> bool:
    """逐词校验：音频还原出的词序列，必须和原文完全一致"""
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    got = [x for x in (norm(w["text"]) for w in merged) if x]
    want = [x for x in (norm(w) for w in original.split()) if x]
    ok = got == want
    tag = "✓ 通过" if ok else "✗ 不匹配"
    print(f"    合并校验：音频 {len(got)} 词 / 原文 {len(want)} 词  {tag}")
    if not ok:
        for i in range(max(len(got), len(want))):
            a = got[i] if i < len(got) else "<无>"
            b = want[i] if i < len(want) else "<无>"
            if a != b:
                print(f"      首个差异 @{i}: 音频={a!r}  原文={b!r}")
                break
    return ok


def run_day(day: str, speed: float, key: str) -> bool:
    src = ROOT / "content" / f"day-{day}" / "words.json"
    if not src.exists():
        print(f"  [跳过] {src} 不存在")
        return False

    data = json.loads(src.read_text(encoding="utf-8"))
    text = data.get("tts_text") or ""
    if not text.strip():
        print(f"  [跳过] day-{day} 没有 tts_text")
        return False

    print(f"  Day {day} · {data.get('title', '')}")
    audio, syllables = synthesize(key, text, speed)

    merged = merge_syllables(syllables, text)
    ok = verify(merged, text)

    out_dir = ROOT / "docs" / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "" if speed == 1.0 else f"-{speed}x"
    (out_dir / f"day-{day}{suffix}.mp3").write_bytes(audio)
    (out_dir / f"day-{day}{suffix}.words.json").write_text(
        json.dumps(
            {
                "day": day,
                "speed": speed,
                "duration_ms": merged[-1]["end"] if merged else 0,
                "sentences": data.get("sentences", []),
                "sentences_cn": data.get("sentences_cn", []),
                "words": merged,
                "target_words": [w["w"] for w in data.get("words", [])],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"    -> docs/audio/day-{day}{suffix}.mp3 + .words.json")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", help="只跑某一天，如 01")
    ap.add_argument("--all", action="store_true", help="跑 content/ 下所有天")
    ap.add_argument("--speed", type=float, default=1.0, help="语速，1.0 为正常")
    args = ap.parse_args()

    key = load_key()
    days = (
        sorted(p.name.split("-")[1] for p in (ROOT / "content").glob("day-*"))
        if args.all
        else [args.day]
    )
    if not days or days == [None]:
        sys.exit("请指定 --day 01 或 --all")

    all_ok = True
    for d in days:
        all_ok &= run_day(d, args.speed, key)
    print("\n完成。" if all_ok else "\n完成，但有校验未通过项。")


if __name__ == "__main__":
    main()
