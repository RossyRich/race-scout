#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
レーススカウト ビルドスクリプト
data/YYYYMMDD_<type>.json (出走表) と predictions/tmp_*.json (AI予想) をマージして
predictions/YYYYMMDD.json と predictions/index.json を生成する。

使い方: python3 build.py 20260720
"""
import sys
import os
import json
import glob
import re
from datetime import datetime, timezone, timedelta

from sports_common import BASE, TYPES, TYPE_ORDER


def main():
    date = sys.argv[1]

    # 予想を race_id で引けるように
    preds = {}
    for p in glob.glob(os.path.join(BASE, "predictions", "tmp_*.json")):
        with open(p, encoding="utf-8") as f:
            pj = json.load(f)
        for r in pj.get("races", []):
            preds[r["race_id"]] = r

    jst = timezone(timedelta(hours=9))
    out = {
        "date": date,
        "updated": datetime.now(jst).strftime("%Y-%m-%d %H:%M"),
        "types": [],
    }
    missing = []
    total = 0
    for t in TYPE_ORDER:
        dpath = os.path.join(BASE, "data", f"{date}_{t}.json")
        if not os.path.exists(dpath):
            continue
        with open(dpath, encoding="utf-8") as f:
            data = json.load(f)
        venues = []
        for v in data.get("venues", []):
            races = []
            for r in sorted(v["races"], key=lambda x: x.get("no", 0)):
                p = preds.get(r["race_id"])
                if not p:
                    missing.append(r["race_id"])
                    continue
                entries = []
                for e in r.get("entries", []):
                    o = {"num": e["num"], "name": e.get("name", ""), "sub": e.get("sub", "")}
                    if e.get("waku"):
                        o["waku"] = e["waku"]
                    if e.get("odds") is not None:
                        o["odds"] = e["odds"]
                    if e.get("pop") is not None:
                        o["pop"] = e["pop"]
                    entries.append(o)
                race = {
                    "race_id": r["race_id"],
                    "no": r["no"],
                    "name": r.get("name", f"{r['no']}R"),
                    "time": r.get("time", ""),
                    "course": r.get("course", ""),
                    "grade": r.get("grade", ""),
                    "head": r.get("head", len(entries)),
                    "entries": entries,
                    "marks": p.get("marks", []),
                    "summary": p.get("summary", ""),
                    "confidence": p.get("confidence", "B"),
                    "bets": p.get("bets", {}),
                }
                if r.get("line"):
                    race["line"] = r["line"]
                races.append(race)
            if races:
                vo = {"name": v["name"], "races": races}
                if v.get("grade"):
                    vo["grade"] = v["grade"]
                venues.append(vo)
                total += len(races)
        if venues:
            out["types"].append({"type": t, "label": TYPES[t], "venues": venues})

    os.makedirs(os.path.join(BASE, "predictions"), exist_ok=True)
    path = os.path.join(BASE, "predictions", f"{date}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    # 日付インデックス更新 (新しい順)
    dates = sorted(
        [os.path.basename(p)[:-5] for p in glob.glob(os.path.join(BASE, "predictions", "*.json"))
         if re.fullmatch(r"\d{8}", os.path.basename(p)[:-5])],
        reverse=True,
    )
    with open(os.path.join(BASE, "predictions", "index.json"), "w", encoding="utf-8") as f:
        json.dump({"dates": dates}, f)

    print(f"生成: {path} ({total}レース)")
    if missing:
        print(f"警告: 予想が見つからないレース {len(missing)}件:")
        for rid in missing[:40]:
            print(f"  {rid}")
        if len(missing) > 40:
            print(f"  …ほか{len(missing) - 40}件")
        sys.exit(2)


if __name__ == "__main__":
    main()
