# -*- coding: utf-8 -*-
"""
把刘晓燕《四级你还在背单词吗》PDF 整本 OCR 成结构化文本。

背景：这 PDF 是扫描件 + 坏掉的 OCR 层，pypdf 提取出来是乱码。
       解法是渲染成图片重新 OCR，用 rapidocr（复用自 26vr 项目）。

流水线：
    1. pymupdf 渲染每页 -> PNG（150 dpi）
    2. rapidocr 识别 -> 文本块 + 坐标 + 置信度
    3. 按坐标还原阅读顺序（**双栏排版，先分左右栏**）
    4. 输出 pages/page-NNN.json + 合并的 book.txt

断点续跑：已处理过的页会跳过（看 pages/ 下有没有对应 json）。

用法：
    python ocr_book.py                 # 全书
    python ocr_book.py --start 1 --end 20
    python ocr_book.py --merge-only    # 只重新合并（改完排版逻辑后不用重跑 OCR）
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PDF = Path(r"E:\english\四级你还在背单词吗txt\四级你还在背单词吗.pdf")
ROOT = Path(r"E:\english\cet4\book")
PAGES = ROOT / "pages"
IMGS = ROOT / "imgs"
DPI = 150


def render(doc, pno: int) -> Path:
    """把某页渲染成 PNG（已存在则跳过）"""
    out = IMGS / f"p{pno + 1:03d}.png"
    if out.exists():
        return out
    page = doc[pno]
    pix = page.get_pixmap(dpi=DPI)
    pix.save(out)
    return out


def order_blocks(items: list[dict]) -> list[str]:
    """
    把 OCR 到的文本块按阅读顺序排好。

    这本书是**双栏排版**，直接按 y 排序会左右串行。
    做法：用所有块的 x 中位数把页面分成左右两栏，各自按 y 排序，再拼接。
    """
    if not items:
        return []

    xs = sorted(it["x"] for it in items)
    # 用中位数当分栏线，比几何中点稳（免得受页边杂质影响）
    mid = xs[len(xs) // 2]

    left = sorted((it for it in items if it["x"] < mid), key=lambda i: i["y"])
    right = sorted((it for it in items if it["x"] >= mid), key=lambda i: i["y"])
    return [it["text"] for it in left + right]


def ocr_page(ocr, img: Path) -> dict:
    t0 = time.time()
    res = ocr(str(img))
    txts = list(res.txts or [])
    scores = list(res.scores or [])
    boxes = res.boxes

    items = []
    for i, t in enumerate(txts):
        box = boxes[i]
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        items.append(
            {
                "text": t,
                "x": float(min(xs)),
                "y": float(min(ys)),
                "score": float(scores[i]),
            }
        )

    lines = order_blocks(items)
    return {
        "lines": lines,
        "blocks": len(items),
        "low_conf": sum(1 for it in items if it["score"] < 0.8),
        "elapsed": round(time.time() - t0, 2),
    }


def merge(out: Path) -> None:
    """把 pages/*.json 合并成一本 txt"""
    files = sorted(PAGES.glob("page-*.json"))
    if not files:
        print("没有可合并的页")
        return
    parts = []
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        pno = d["page"]
        parts.append(f"\n\n{'=' * 60}\n=== 第 {pno} 页 ===\n{'=' * 60}\n")
        parts.extend(d["lines"])
    out.write_text("\n".join(parts), encoding="utf-8")
    kb = out.stat().st_size / 1024
    print(f"合并 {len(files)} 页 -> {out}  ({kb:.0f} KB)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=1, help="起始页（1-based）")
    ap.add_argument("--end", type=int, default=0, help="结束页（含）")
    ap.add_argument("--merge-only", action="store_true")
    args = ap.parse_args()

    ROOT.mkdir(parents=True, exist_ok=True)
    PAGES.mkdir(exist_ok=True)
    IMGS.mkdir(exist_ok=True)
    out_txt = ROOT / "book.txt"

    if args.merge_only:
        merge(out_txt)
        return

    import pymupdf

    doc = pymupdf.open(PDF)
    n = doc.page_count
    start = max(1, args.start)
    end = args.end or n
    print(f"PDF {n} 页，处理 {start}-{end}")

    # 模型加载一次，循环复用
    from rapidocr import RapidOCR

    print("加载 OCR 模型 ...")
    ocr = RapidOCR()

    todo = [p for p in range(start - 1, min(end, n))]
    skipped = 0
    t_all = time.time()

    for i, pno in enumerate(todo, 1):
        jf = PAGES / f"page-{pno + 1:03d}.json"
        if jf.exists():
            skipped += 1
            continue

        img = render(doc, pno)
        d = ocr_page(ocr, img)
        d["page"] = pno + 1
        jf.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")

        flag = f"  ⚠低置信 {d['low_conf']}" if d["low_conf"] else ""
        print(f"[{i}/{len(todo)}] p{pno + 1:03d}  "
              f"{d['blocks']:>3} 块  {d['elapsed']:>5.1f}s{flag}")

    doc.close()
    print(f"\nOCR 完成，总耗时 {(time.time() - t_all) / 60:.1f} 分钟"
          f"（跳过 {skipped} 页已处理）")
    merge(out_txt)


if __name__ == "__main__":
    main()
