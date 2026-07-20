#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
レーススカウト 結果集計スクリプト
各種別の公式結果ページから着順・払戻を取得し、predictions/YYYYMMDD.json の
買い目と突き合わせて results/YYYYMMDD.json に保存する。

使い方:
  python3 results.py 20260720          # 指定日を集計
  python3 results.py 20260720 --force  # 未確定/中止レースを飛ばして集計
  python3 results.py --auto            # 未集計の過去日をまとめて集計
"""
import sys
import os
import re
import json
import glob
import importlib
from datetime import datetime, timezone, timedelta

from sports_common import BASE, BET_KEYS, BET_DEFS

JST = timezone(timedelta(hours=9))


def judge(type_key, bets, payouts):
    """予想の買い目と払戻を突き合わせ。{券種: {points, hit, payout}}"""
    res = {}
    for key in BET_KEYS[type_key]:
        n, ordered = BET_DEFS[key]
        pts = bets.get(key, [])
        entry = {"points": len(pts), "hit": False, "payout": 0}
        for combo, pay in payouts.get(key, []):
            combo = list(combo)
            for p in pts:
                nums = [int(x) for x in re.findall(r"\d+", str(p))]
                if len(nums) != n:
                    continue
                if (nums == combo) if ordered else (set(nums) == set(combo)):
                    entry["hit"] = True
                    entry["payout"] += pay
                    break
        res[key] = entry
    return res


def collect(date, force=False):
    pred_path = os.path.join(BASE, "predictions", f"{date}.json")
    if not os.path.exists(pred_path):
        print(f"予想なし: {date}")
        return False
    pred = json.load(open(pred_path, encoding="utf-8"))

    out_types = []
    for tblock in pred.get("types", []):
        t = tblock["type"]
        mod = importlib.import_module(f"mod_{t}")
        races = []
        for v in tblock["venues"]:
            for r in v["races"]:
                try:
                    res = mod.fetch_result(r["race_id"])
                except Exception as e:
                    print(f"  取得エラー: {r['race_id']} ({e})")
                    res = None
                if not res:
                    if force:
                        print(f"  スキップ(未確定/中止): {v['name']}{r['no']}R")
                        continue
                    print(f"  結果未確定: {tblock['label']} {v['name']}{r['no']}R → この日は保留")
                    return False
                nm = {e["num"]: e["name"] for e in r.get("entries", [])}
                hon = (r.get("marks") or [{}])[0]
                top3 = res["top3"]
                races.append({
                    "race_id": r["race_id"],
                    "venue": v["name"],
                    "no": r["no"],
                    "name": r["name"],
                    "confidence": r.get("confidence", "B"),
                    "top3": [{"num": x, "name": nm.get(x, "")} for x in top3],
                    "honmei": {"num": hon.get("num"), "name": hon.get("name", ""),
                               "win": hon.get("num") == top3[0]},
                    "bets": judge(t, r.get("bets", {}), res.get("payouts", {})),
                })
                hits = [k for k, e in races[-1]["bets"].items() if e["hit"]]
                print(f"  {tblock['label']} {v['name']}{r['no']}R 1着:{top3[0]} {' '.join(hits)}")
        if races:
            out_types.append({"type": t, "label": tblock["label"], "races": races})

    if not out_types:
        print("集計できるレースがありません")
        return False

    out = {"date": date, "types": out_types}
    os.makedirs(os.path.join(BASE, "results"), exist_ok=True)
    with open(os.path.join(BASE, "results", f"{date}.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    dates = sorted(
        [os.path.basename(p)[:-5] for p in glob.glob(os.path.join(BASE, "results", "*.json"))
         if re.fullmatch(r"\d{8}", os.path.basename(p)[:-5])],
        reverse=True,
    )
    with open(os.path.join(BASE, "results", "index.json"), "w", encoding="utf-8") as f:
        json.dump({"dates": dates}, f)
    n = sum(len(t["races"]) for t in out_types)
    print(f"保存: results/{date}.json ({n}レース)")
    return True


def main():
    force = "--force" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--auto" in sys.argv:
        today = datetime.now(JST).strftime("%Y%m%d")
        done = False
        for p in sorted(glob.glob(os.path.join(BASE, "predictions", "*.json"))):
            d = os.path.basename(p)[:-5]
            if not re.fullmatch(r"\d{8}", d):
                continue
            if os.path.exists(os.path.join(BASE, "results", f"{d}.json")):
                continue
            if d >= today:  # ミッドナイト競輪が23時過ぎまであるため当日分は翌朝集計
                continue
            print(f"集計: {d}")
            done = collect(d, force) or done
        if not done:
            print("集計対象なし")
    elif args:
        collect(args[0], force)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
