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


# ── 原始响应缓存 ─────────────────────────────────────────
#
# 为什么要有这个：调 merge_syllables 的逻辑时反复踩坑（错误日志 #18），
# 每改一次匹配规则就要重调一次 API 才能拿到原始音节数据 —— 既慢又烧配额，
# 而且 MiniMax 每次返回的条目还会有细微差异，没法做稳定的对照实验。
#
# 所以把每次 synthesize 的原始结果落盘：改 merge 逻辑时用 --from-cache
# 反复跑，零成本、零配额、结果完全可复现。
CACHE_DIR = ROOT / "_cache" / "tts"


def _cache_paths(day: str, speed: float) -> tuple[Path, Path]:
    suffix = "" if speed == 1.0 else f"-{speed}x"
    base = CACHE_DIR / f"day-{day}{suffix}"
    return base.with_suffix(".mp3"), base.with_suffix(".syllables.json")


def load_cache(day: str, speed: float) -> tuple[bytes, list] | None:
    mp3, syl = _cache_paths(day, speed)
    if mp3.exists() and syl.exists():
        return mp3.read_bytes(), json.loads(syl.read_text(encoding="utf-8"))
    return None


def save_cache(day: str, speed: float, audio: bytes, syllables: list) -> None:
    mp3, syl = _cache_paths(day, speed)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    mp3.write_bytes(audio)
    syl.write_text(json.dumps(syllables, ensure_ascii=False, indent=2), encoding="utf-8")


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
    """
    字母数字算词字符。**撇号和连字符不算** —— 这是实测踩出来的：

    MiniMax 把 "Nina's" 拆成 ['N', 'ina', "'", 's']，撇号是**独立条目**。
    如果把它当词内字符，原文的 core（'ninas'）和音节流（"Nina's"）就对不上，
    第一个词就 break，后面全崩 —— 实测 Day 20 只还原出 9/273 词。
    所以匹配时把撇号/连字符当分隔符跳过，双方都不带它们，自然对齐。
    """
    return c.isalnum()


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

    # 音节流：按顺序拼接所有条目，同时记录每个字符的起止时间。
    #
    # ⚠️ **空格条目必须保留** —— 它就是词边界。
    #    MiniMax 把 "Green Harbor was" 拆成：
    #      ['G','re','en', ' ', 'Har','bor', ' ', 'was', ' ']
    #    去掉空格条目后变成 'GreenHarborwas'，词边界信息全丢了，
    #    匹配就会跨词误配（实测 'the' 匹配到 38 字符外某个词内部的 "the"，
    #    指针一跳远，后面全崩 —— Day 11 只还原出 257/258 词）。
    #
    # ⚠️ 同时压掉**连续重复**的条目。MiniMax 对数字会吐重复，次数还不固定：
    #      "in 1960. He"     -> '1960' 重复 2 次
    #      "from 1978. She"  -> '1978' 重复 16 次
    #    在构建阶段压掉最干净 —— 下游逻辑都不需要知道这回事。
    stream_chars: list[str] = []
    stream_time: list[tuple[float, float]] = []
    prev_token = None
    for s in syllables:
        t = s.get("word", "")
        if not t:
            continue
        if t == prev_token:
            continue  # 和上一条完全相同 —— 是 MiniMax 的重复条目，丢掉
        prev_token = t
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

        # 从音节流当前位置起，找一个能容纳这个词的位置。
        #
        # 为什么不直接匹配当前位置：MiniMax 对缩写（Mr. / Mrs. / St.）和
        # 引号的处理和原文不完全一致，一次错位就会让后面**全部**失败
        # （实测 Day 31 只还原出 2/241 词）。
        # 所以给自己留一点回旋：最多向前找 LOOKAHEAD 个字符宽度的窗口。
        LOOKAHEAD = 40
        match = None
        for probe in range(0, LOOKAHEAD + 1):
            p = j + probe
            if p >= len(stream):
                break
            # 跳到词首：跳过空白/标点。流里保留了 MiniMax 的空格条目，
            # 它就是词边界 —— 从这个位置往后读才是完整的一个词。
            while p < len(stream) and not _is_word_char(stream[p]):
                p += 1
            if p >= len(stream):
                break
            k = 0
            first = last = None
            q = p
            while q < len(stream) and k < len(core):
                c = stream[q]
                if c in "'’":
                    # 撇号：MiniMax 把它当独立条目（morning's -> 'morning', "'", 's'），
                    # 而原文的 core 里没有它（'mornings'）。跳过不比对，但**不断词**
                    # —— 它和空格不同，不构成词边界。
                    q += 1
                    continue
                if not _is_word_char(c):
                    # 空格或其他标点 —— 这是词边界，不能再往后读
                    break
                if c.lower() == core[k]:
                    if first is None:
                        first = q
                    last = q
                    k += 1
                    q += 1
                else:
                    break
            if k == len(core) and first is not None:
                match = (first, last, q)
                break

        if match:
            first, last, q = match
            words.append(
                {
                    "text": want,
                    "start": stream_time[first][0],
                    "end": stream_time[last][1],
                }
            )
            # 跳过紧邻的重复出现（可以连续多次）。
            #
            # 注意：这**不是**处理 MiniMax 的重复条目（那已在构建音节流时压掉了），
            # 而是处理"同一个词在原文里连续出现了两次"的情况。
            # 实测 "layout for forty years" 的音节流是 ...'for',' ','for','ty',' ','years'
            # —— 匹配完第一个 'for' 后，指针落在第二个 'for' 上，下一个词 'forty'
            # 就被 'for' 卡住了。
            #
            # ⚠️ 判据必须严格：吃掉的那段要**正好等于本词**，且后面紧跟词边界。
            #    早期版本只看前缀就判重复，把 'for'+'ty' 误判成 'for' 的重复，
            #    连 'ty' 一起吃掉，forty 整词丢失（Day 11/12 因此各差 1 词）。
            j = q
            dup = [c.lower() for c in want if _is_word_char(c)]
            if dup:
                while True:
                    p = j
                    while p < len(stream) and not _is_word_char(stream[p]):
                        p += 1
                    k2 = 0
                    while p < len(stream) and k2 < len(dup):
                        c = stream[p]
                        if not _is_word_char(c):
                            break  # 词内不允许分隔符
                        if c.lower() == dup[k2]:
                            k2 += 1
                            p += 1
                        else:
                            break
                    at_boundary = p >= len(stream) or not _is_word_char(stream[p])
                    if k2 == len(dup) and at_boundary:
                        j = p
                    else:
                        break
        # 找不到就跳过这个词，指针不动 —— 让下一个词还有机会对齐

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


def run_day(day: str, speed: float, key: str, from_cache: bool = False) -> bool:
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

    # 重试：MiniMax 偶尔会返回截断的音频（实测 Day 31 只出了 0.5 秒 / 2 个词）。
    # 校验不通过就重来，最多 3 次 —— 一条坏数据不该废掉一整天。
    n_words = len(text.split())
    audio = syllables = merged = None
    ok = False
    for attempt in range(1, 4):
        cached = load_cache(day, speed) if from_cache else None
        if cached:
            audio, syllables = cached
            print("    用缓存（不调 API）")
        elif from_cache:
            print(f"    [跳过] 缓存里没有 day-{day}，先不带 --from-cache 跑一次")
            return False
        else:
            audio, syllables = synthesize(key, text, speed)
            save_cache(day, speed, audio, syllables)
        merged = merge_syllables(syllables, text)
        ok = verify(merged, text)
        if ok:
            break
        if from_cache:
            break  # 缓存模式下重试没意义，数据是同一份
        got = len([w for w in merged if w["text"].strip()])
        print(f"    [重试 {attempt}/3] 只还原出 {got}/{n_words} 词，重来 ...")
    if not ok:
        print(f"    [放弃] 三次都没通过，跳过 day-{day}")
        return False

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
    ap.add_argument(
        "--from-cache",
        action="store_true",
        help="用 _cache/tts 里的原始响应重跑合并（不调 API，改 merge 逻辑时用）",
    )
    args = ap.parse_args()

    if args.from_cache:
        # 缓存模式不需要 key —— 这正是它的价值：配额耗尽时也能调逻辑
        key = ""
    else:
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
        all_ok &= run_day(d, args.speed, key, from_cache=args.from_cache)
    print("\n完成。" if all_ok else "\n完成，但有校验未通过项。")


if __name__ == "__main__":
    main()
