#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
レーススカウト データ収集ドライバ
4種別（地方競馬・競輪・ボートレース・オートレース）の当日出走表を収集し、
data/YYYYMMDD_<type>.json に保存する。

使い方:
  python3 scrape.py 20260720            # 全種別
  python3 scrape.py 20260720 boat keirin  # 種別指定
"""
import sys
import time
import importlib
from sports_common import TYPES, TYPE_ORDER, save_data


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    date = args[0] if args else time.strftime("%Y%m%d")
    types = args[1:] if len(args) > 1 else TYPE_ORDER

    ok = []
    for t in types:
        if t not in TYPES:
            print(f"不明な種別: {t}")
            continue
        print(f"=== {TYPES[t]} ({t}) ===")
        try:
            mod = importlib.import_module(f"mod_{t}")
        except ImportError as e:
            print(f"  モジュール読み込み失敗: {e}")
            continue
        try:
            day = mod.scrape_day(date)
        except Exception as e:
            print(f"  収集エラー: {e}")
            continue
        if not day or not day.get("venues"):
            print("  開催なし")
            continue
        n = sum(len(v["races"]) for v in day["venues"])
        names = "・".join(v["name"] for v in day["venues"])
        path = save_data(date, t, day)
        print(f"  {len(day['venues'])}場 {n}レース ({names})")
        print(f"  保存: {path}")
        ok.append(t)

    if not ok:
        print("本日の開催はありません")
        sys.exit(1)
    print(f"完了: {' '.join(ok)}")


if __name__ == "__main__":
    main()
