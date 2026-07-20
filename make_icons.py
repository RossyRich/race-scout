#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""icon.svg と同じ図柄(スピードライン+◎)のPNGアイコンを標準ライブラリだけで生成する"""
import os
import math
import zlib
import struct

BASE = os.path.dirname(os.path.abspath(__file__))
BG = (15, 16, 19)        # #0f1013
LINE_DIM = (47, 79, 66)  # #2f4f42
LINE_MID = (26, 125, 82)  # #1a7d52
RING = (31, 174, 110)    # #1fae6e
DOT = (233, 231, 226)    # #e9e7e2

# icon.svg と同じ座標系(512基準): (x, y, w, h, color)
BARS = [
    (72, 176, 150, 24, LINE_DIM),
    (72, 244, 178, 24, LINE_MID),  # 先端は輪のストローク(237〜257)の下に隠れる
    (72, 312, 150, 24, LINE_DIM),
]
RING_C, RING_R, RING_HW = (344, 256), 94, 13  # stroke-width 26 の半分
DOT_R = 42


def clamp01(v):
    return 0.0 if v < 0 else 1.0 if v > 1 else v


def rrect_sd(px, py, cx, cy, hw, hh, r):
    """角丸四角の符号付き距離(負が内側)"""
    qx = abs(px - cx) - (hw - r)
    qy = abs(py - cy) - (hh - r)
    return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r


def over(base, color, a):
    return tuple(b + (c - b) * a for b, c in zip(base, color))


def make(size, path, rounded=True):
    s = size / 512.0
    half = size / 2.0
    corner = 100 * s
    rc = (RING_C[0] * s, RING_C[1] * s)
    ring_r, ring_hw, dot_r = RING_R * s, RING_HW * s, DOT_R * s
    bars = [(x * s, y * s, w * s, h * s, col) for x, y, w, h, col in BARS]

    rows = []
    for y in range(size):
        row = bytearray([0])  # filter type 0
        for x in range(size):
            px, py = x + 0.5, y + 0.5
            col = BG
            for bx, by, bw, bh, bcol in bars:
                d = rrect_sd(px, py, bx + bw / 2, by + bh / 2, bw / 2, bh / 2, bh / 2)
                col = over(col, bcol, clamp01(0.5 - d))
            dc = math.hypot(px - rc[0], py - rc[1])
            col = over(col, RING, clamp01(0.5 + (ring_hw - abs(dc - ring_r))))
            col = over(col, DOT, clamp01(0.5 + (dot_r - dc)))
            if rounded:
                d = rrect_sd(px, py, half, half, half, half, corner)
                alpha = clamp01(0.5 - d)
            else:
                alpha = 1.0
            row += bytes((int(col[0] + 0.5), int(col[1] + 0.5), int(col[2] + 0.5),
                          int(alpha * 255 + 0.5)))
        rows.append(bytes(row))

    raw = b"".join(rows)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    with open(os.path.join(BASE, path), "wb") as f:
        f.write(png)
    print(f"{path} ({size}x{size})")


if __name__ == "__main__":
    make(512, "icon-512.png")
    make(192, "icon-192.png")
    make(180, "apple-touch-icon.png", rounded=False)  # iOSが自前で角丸にする
