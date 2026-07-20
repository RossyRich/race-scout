#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""icon.svg と同じ図柄のPNGアイコンを標準ライブラリだけで生成する(初回セットアップ用)"""
import os
import math
import zlib
import struct

BASE = os.path.dirname(os.path.abspath(__file__))
BG = (15, 16, 19)        # #0f1013
RING = (31, 174, 110)    # #1fae6e
DOT = (233, 231, 226)    # #e9e7e2


def clamp01(v):
    return 0.0 if v < 0 else 1.0 if v > 1 else v


def make(size, path, rounded=True):
    s = size / 512.0
    cx = cy = size / 2.0
    corner = 100 * s
    half = size / 2.0
    ring_r, ring_hw = 146 * s, 17 * s
    dot_r = 60 * s

    rows = []
    for y in range(size):
        row = bytearray([0])  # filter type 0
        for x in range(size):
            px, py = x + 0.5, y + 0.5
            # 角丸四角のSDF
            qx = abs(px - cx) - (half - corner)
            qy = abs(py - cy) - (half - corner)
            d_rect = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - corner
            a_rect = clamp01(0.5 - d_rect) if rounded else 1.0
            d = math.hypot(px - cx, py - cy)
            a_ring = clamp01(0.5 + (ring_hw - abs(d - ring_r)))
            a_dot = clamp01(0.5 + (dot_r - d))
            r, g, b = BG
            r = r + (RING[0] - r) * a_ring
            g = g + (RING[1] - g) * a_ring
            b = b + (RING[2] - b) * a_ring
            r = r + (DOT[0] - r) * a_dot
            g = g + (DOT[1] - g) * a_dot
            b = b + (DOT[2] - b) * a_dot
            row += bytes((int(r + 0.5), int(g + 0.5), int(b + 0.5), int(a_rect * 255 + 0.5)))
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
