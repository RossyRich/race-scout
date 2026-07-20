#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
レーススカウト ボートレースモジュール (type="boat", label="ボートレース")

データソース: 公式 boatrace.jp（サーバレンダリングHTML）
  開催一覧: https://www.boatrace.jp/owpc/pc/race/index?hd=YYYYMMDD
  出走表:   https://www.boatrace.jp/owpc/pc/race/racelist?rno=R&jcd=JJ&hd=YYYYMMDD
  結果:     https://www.boatrace.jp/owpc/pc/race/raceresult?rno=R&jcd=JJ&hd=YYYYMMDD

race_id 形式: "B" + YYYYMMDD + "_" + jcd(2桁) + "_" + rno(2桁)
  例 "B20260719_01_12"
    → https://www.boatrace.jp/owpc/pc/race/raceresult?rno=12&jcd=01&hd=20260719
  race_id 文字列だけで結果ページURLを再構築できる。
"""
import re
import sys
import json

import sports_common as sc

TYPE = "boat"
LABEL = "ボートレース"
BASE_URL = "https://www.boatrace.jp/owpc/pc/race"
SLEEP = 0.3

# jcd → 場名（index ページの alt が取れない場合のフォールバック）
JCD_NAMES = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島",
    "05": "多摩川", "06": "浜名湖", "07": "蒲郡", "08": "常滑",
    "09": "津", "10": "三国", "11": "びわこ", "12": "住之江",
    "13": "尼崎", "14": "鳴門", "15": "丸亀", "16": "児島",
    "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村",
}

# 開催一覧のグレードセル class → グレード表記
GRADE_CLASSES = [
    ("is-SG", "SG"), ("is-G1", "G1"), ("is-G2", "G2"), ("is-G3", "G3"),
    ("is-ippan", "一般"),
]
# 開催時間帯セル class → 区分
SLOT_CLASSES = [
    ("is-nighter", "ナイター"), ("is-morning", "モーニング"),
    ("is-midnight", "ミッドナイト"), ("is-summer", "サマータイム"),
]

_Z2H = str.maketrans("０１２３４５６７８９", "0123456789")


def _z2h(s):
    return (s or "").translate(_Z2H)


def _clean_name(s):
    """選手名の全角詰めスペースを除去"""
    return re.sub(r"[\s　]+", "", s or "")


def _f1(s):
    """'22.73' → '22.7'。数値でなければそのまま返す"""
    try:
        return f"{float(s):.1f}".rstrip("0").rstrip(".") if "." in s else s
    except (ValueError, TypeError):
        return s


# ---------------------------------------------------------------- scrape_day

def _parse_index(html, date):
    """開催一覧 → [(jcd, 場名, grade, 時間帯, タイトル), ...]"""
    venues = []
    for block in re.split(r"<tbody>", html):
        m = re.search(r"raceindex\?jcd=(\d{2})&amp;hd=" + date, block)
        if not m:
            continue
        jcd = m.group(1)
        ma = re.search(r'text_place1_\d+\.png"[^>]*alt="([^"]+)"', block)
        name = ma.group(1) if ma else JCD_NAMES.get(jcd, f"場{jcd}")
        cells = re.findall(r'<td rowspan="2" class="([^"]*)"\s*>', block)
        grade, slot = "", ""
        for c in cells:
            for cls, g in GRADE_CLASSES:
                if cls in c:
                    grade = grade or g
            for cls, s in SLOT_CLASSES:
                if cls in c:
                    slot = slot or s
        mt = re.search(r'raceindex\?jcd=\d+&amp;hd=\d+">([^<]+)</a>', block)
        title = (mt.group(1).strip() if mt else "")
        venues.append((jcd, name, grade, slot, title))
    return venues


def _parse_times(html):
    """racelist の締切予定時刻行 → {rno: "HH:MM"}"""
    times = {}
    m = re.search(r"締切予定時刻</td>(.*?)</tr>", html, re.S)
    if m:
        for i, t in enumerate(re.findall(r"<td[^>]*>\s*(\d{1,2}:\d{2})\s*</td>",
                                         m.group(1)), 1):
            times[i] = t
    return times


def _parse_race_count(html):
    """racelist 上部のレース一覧タブから最大レース番号を得る"""
    nos = [int(n) for n in
           re.findall(r'racelist\?rno=(\d+)&amp;jcd=\d+&amp;hd=\d+"', html)]
    return max(nos) if nos else 12


def _parse_race_title(html):
    """h3（例: '一般 1800m'）→ (レース名, 距離)"""
    m = re.search(r'<h3 class="title16_titleDetail__add2020">(.*?)</h3>',
                  html, re.S)
    name, course = "", ""
    if m:
        text = sc.strip_tags(m.group(1))
        mc = re.search(r"(\d+m)", text)
        if mc:
            course = mc.group(1)
            name = text[:mc.start()].strip()
        else:
            name = text.strip()
    ml = re.search(r'<div class="title16_titleLabels__add2020">(.*?)</div>',
                   html, re.S)
    if ml:
        label = sc.strip_tags(ml.group(1))
        if label:
            name = f"{name}({label})" if name else label
    return name, course


def _parse_entries(html):
    """racelist の6艇分の出走情報"""
    entries = []
    for tb in re.findall(r'<tbody class="[^"]*is-fs12[^"]*">(.*?)</tbody>',
                         html, re.S):
        mn = re.search(r'<td class="is-boatColor(\d) is-fs14"[^>]*>\s*([０-９\d]+)',
                       tb)
        if not mn:
            continue
        num = int(_z2h(mn.group(2)) or mn.group(1))

        mname = re.search(r'is-fs18 is-fBold"><a[^>]*>([^<]+)</a>', tb)
        name = _clean_name(mname.group(1)) if mname else ""
        if not name:
            continue  # 欠場等で選手枠が空

        mk = re.search(r'(\d{4})\s*/\s*<span[^>]*>\s*(A1|A2|B1|B2)\s*</span>', tb)
        toban = mk.group(1) if mk else ""
        klass = mk.group(2) if mk else ""

        mb = re.search(r'<div class="is-fs11">\s*([^<>/\s]+)/([^<>\s]+)\s*'
                       r'<br\s*/?>\s*(\d+)歳/([\d.]+)kg', tb)
        branch = mb.group(1) if mb else ""
        age = mb.group(3) if mb else ""
        weight = mb.group(4) if mb else ""

        # is-lineH2 の td 5個: [F/L/ST, 全国, 当地, モーター, ボート]
        stats = [sc.strip_tags(t).split() for t in re.findall(
            r'<td class="[^"]*is-lineH2[^"]*" rowspan="4">(.*?)</td>', tb, re.S)]
        flst = stats[0] if len(stats) > 0 else []
        zenkoku = stats[1] if len(stats) > 1 else []
        touchi = stats[2] if len(stats) > 2 else []
        motor = stats[3] if len(stats) > 3 else []
        boat = stats[4] if len(stats) > 4 else []

        fl = "".join(flst[:2]) if len(flst) >= 2 else ""
        st = flst[2] if len(flst) >= 3 else ""

        # 今節成績: 4行目 (tr class="is-fBold") の着順リンク
        seiseki = ""
        ms = re.search(r'<tr class="is-fBold">(.*?)</tr>', tb, re.S)
        if ms:
            fins = [_z2h(x.strip()) for x in
                    re.findall(r'raceresult[^"]*">([^<]*)</a>', ms.group(1))]
            seiseki = "-".join(f for f in fins if f)

        parts = [f"{klass} {branch}".strip()]
        if age or weight:
            parts.append(f"{age}歳{weight}kg")
        if fl:
            parts.append(fl)
        if st:
            parts.append(f"平均ST{st}")
        if len(zenkoku) >= 2:
            parts.append(f"全国{zenkoku[0]}/2連{_f1(zenkoku[1])}%")
        if len(touchi) >= 2:
            parts.append(f"当地{touchi[0]}/2連{_f1(touchi[1])}%")
        if len(motor) >= 2:
            parts.append(f"M{motor[0]}号2連{_f1(motor[1])}%")
        if len(boat) >= 2:
            parts.append(f"B{boat[0]}号2連{_f1(boat[1])}%")
        if seiseki:
            parts.append(f"今節:{seiseki}")

        entries.append({
            "num": num,
            "name": name,
            "sub": f"{klass} {branch}".strip(),
            "detail": " ".join(parts),
        })
    entries.sort(key=lambda e: e["num"])
    return entries


def scrape_day(date):
    """date="YYYYMMDD" の全開催・全レースの出走表。開催なしなら None。"""
    try:
        html = sc.fetch(f"{BASE_URL}/index?hd={date}", sleep=SLEEP)
    except Exception as e:
        print(f"[boat] index取得失敗: {e}", file=sys.stderr)
        return None
    venue_defs = _parse_index(html, date)
    if not venue_defs:
        return None

    venues = []
    for jcd, vname, grade, slot, title in venue_defs:
        races = []
        race_count = 12
        times = {}
        for rno in range(1, race_count + 1):
            url = f"{BASE_URL}/racelist?rno={rno}&jcd={jcd}&hd={date}"
            try:
                page = sc.fetch(url, sleep=SLEEP)
            except Exception as e:
                print(f"[boat] {vname}{rno}R 取得失敗: {e}", file=sys.stderr)
                continue
            if rno == 1:
                race_count = _parse_race_count(page)
                times = _parse_times(page)
            entries = _parse_entries(page)
            if not entries:
                continue  # 中止等
            rname, course = _parse_race_title(page)
            races.append({
                "race_id": f"B{date}_{jcd}_{rno:02d}",
                "no": rno,
                "name": rname,
                "time": times.get(rno, ""),
                "course": course,
                "grade": "",
                "head": 6,
                "entries": entries,
            })
        if races:
            disp = f"{vname}（{slot}）" if slot else vname
            venues.append({"name": disp, "grade": grade, "races": races})
            print(f"[boat] {disp} {grade} {len(races)}R", file=sys.stderr)
    if not venues:
        return None
    return {"type": TYPE, "label": LABEL, "venues": venues}


# -------------------------------------------------------------- fetch_result

# 払戻表の勝式名 → BET_KEYS のキー
_BET_NAMES = {
    "3連単": "sanrentan",
    "3連複": "sanrenpuku",
    "2連単": "nirentan",
    "2連複": "nirenpuku",
}


def _parse_top3(html):
    """着順表 → [1着艇, 2着艇, 3着艇]"""
    rows = re.findall(
        r'<td class="is-fs14">([^<]*)</td>\s*'
        r'<td class="is-fs14 is-fBold is-boatColor\d">(\d)</td>', html)
    by_rank = {}
    for rank, num in rows:
        r = _z2h(rank.strip())
        if r in ("1", "2", "3") and int(r) not in by_rank:
            by_rank[int(r)] = int(num)
    return [by_rank[r] for r in (1, 2, 3) if r in by_rank]


def _parse_payouts(html):
    payouts = {}
    for tb in re.split(r"<tbody>", html):
        mh = re.search(r'<td rowspan="\d+">\s*(3連単|3連複|2連単|2連複)\s*</td>',
                       tb[:400])
        if not mh:
            continue
        key = _BET_NAMES[mh.group(1)]
        need = sc.BET_DEFS[key][0]
        rows = []
        for tr in re.split(r"<tr[ >]", tb):
            nums = re.findall(r'numberSet1_number[^"]*"[^>]*>\s*(\d)\s*</span>', tr)
            myen = re.search(r"&yen;([\d,]+)", tr)
            if len(nums) == need and myen:
                rows.append([[int(n) for n in nums],
                             int(myen.group(1).replace(",", ""))])
        if rows:
            payouts[key] = rows
    return payouts


def fetch_result(race_id):
    """1レースの確定結果。未確定・中止なら None。"""
    m = re.match(r"^B(\d{8})_(\d{2})_(\d{2})$", race_id)
    if not m:
        return None
    date, jcd, rno = m.group(1), m.group(2), int(m.group(3))
    url = f"{BASE_URL}/raceresult?rno={rno}&jcd={jcd}&hd={date}"
    try:
        html = sc.fetch(url, sleep=SLEEP)
    except Exception as e:
        print(f"[boat] 結果取得失敗 {race_id}: {e}", file=sys.stderr)
        return None
    top3 = _parse_top3(html)
    payouts = _parse_payouts(html)
    if not top3 or not payouts:
        return None  # 未確定・中止・全返還
    return {"top3": top3, "payouts": payouts}


# ------------------------------------------------------------------- CLI

def main():
    if len(sys.argv) < 3:
        print("usage: python3 mod_boat.py scrape YYYYMMDD | result <race_id>")
        return
    cmd, arg = sys.argv[1], sys.argv[2]
    if cmd == "scrape":
        obj = scrape_day(arg)
        if obj is None:
            print("開催なし")
            return
        path = sc.save_data(arg, TYPE, obj)
        total = sum(len(v["races"]) for v in obj["venues"])
        print(f"saved: {path}")
        print(f"{len(obj['venues'])}場 {total}レース")
        for v in obj["venues"]:
            print(f"  {v['name']} [{v['grade']}] {len(v['races'])}R "
                  f"{v['races'][0]['time']}-{v['races'][-1]['time']}")
    elif cmd == "result":
        res = fetch_result(arg)
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        print(f"unknown command: {cmd}")


if __name__ == "__main__":
    main()
