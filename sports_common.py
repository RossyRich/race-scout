#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""レーススカウト 共通ユーティリティ（全種別モジュールが import する）"""
import os
import re
import json
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))

# 種別キー → 表示名
TYPES = {
    "keiba": "地方競馬",
    "keirin": "競輪",
    "boat": "ボートレース",
    "auto": "オートレース",
}
TYPE_ORDER = ["keiba", "keirin", "boat", "auto"]

# 種別ごとの券種キー（予想・結果で共通に使う）
BET_KEYS = {
    "keiba": ["tansho", "umaren", "sanrenpuku", "sanrentan"],
    "keirin": ["nirenpuku", "nirentan", "sanrenpuku", "sanrentan"],
    "boat": ["nirenpuku", "nirentan", "sanrenpuku", "sanrentan"],
    "auto": ["nirenpuku", "nirentan", "sanrenpuku", "sanrentan"],
}

# 券種キー → (1組の数, 着順を問うか)
BET_DEFS = {
    "tansho": (1, False),
    "umaren": (2, False),
    "nirenpuku": (2, False),
    "nirentan": (2, True),
    "sanrenpuku": (3, False),
    "sanrentan": (3, True),
}

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def fetch(url, encoding="utf-8", retries=2, sleep=0.4):
    """URLを取得して文字列で返す。失敗時はretries回リトライ。"""
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
            time.sleep(sleep)
            return body.decode(encoding, errors="replace")
        except Exception as e:
            last = e
            time.sleep(1.5)
    raise last


def strip_tags(s):
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    s = (s.replace("&nbsp;", " ").replace("&amp;", "&")
         .replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'"))
    return re.sub(r"\s+", " ", s).strip()


def save_data(date, type_key, obj):
    os.makedirs(os.path.join(BASE, "data"), exist_ok=True)
    path = os.path.join(BASE, "data", f"{date}_{type_key}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    return path
