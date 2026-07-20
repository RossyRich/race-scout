#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""レーススカウト オートレースモジュール (type="auto")

データソース: オッズパーク オートレース (https://www.oddspark.com/autorace/)
  - 開催検出/レース一覧: OneDayRaceList.do?raceDy=<YYYYMMDD>&placeCd=<CD>
  - 出走表(詳細)        : RaceList.do?raceDy=<YYYYMMDD>&placeCd=<CD>&raceNo=<N>
  - 結果・払戻          : RaceResult.do?raceDy=<YYYYMMDD>&placeCd=<CD>&raceNo=<N>
  ※公式 autorace.jp はレースデータがJavaScriptレンダリングのため不採用。

race_id 形式: "A<YYYYMMDD>_<場romaji>_<レース番号2桁>"
  例: "A20260719_kawaguchi_01"
  場romaji → オッズパーク placeCd 対応（VENUES 参照）:
    kawaguchi=02(川口) isesaki=03(伊勢崎) hamamatsu=04(浜松)
    iizuka=05(飯塚) sanyo=06(山陽)
  race_id だけから結果URLを再構築できる:
    https://www.oddspark.com/autorace/RaceResult.do?raceDy=<日付>&placeCd=<CD>&raceNo=<int(番号)>
"""
import re
import sys
import json
import html as htmlmod

import sports_common as sc

TYPE = "auto"
LABEL = "オートレース"

BASE_URL = "https://www.oddspark.com/autorace"

# romaji → (placeCd, 漢字場名)。走路は全国5場（船橋は廃止済みのため除外）
VENUES = {
    "kawaguchi": ("02", "川口"),
    "isesaki": ("03", "伊勢崎"),
    "hamamatsu": ("04", "浜松"),
    "iizuka": ("05", "飯塚"),
    "sanyo": ("06", "山陽"),
}
CD2ROMAJI = {cd: r for r, (cd, _) in VENUES.items()}

BET_MAP = {
    "2連複": "nirenpuku",
    "2連単": "nirentan",
    "3連複": "sanrenpuku",
    "3連単": "sanrentan",
}


def _clean(s):
    """タグ除去+空白正規化（全角スペース・&nbsp;含む）"""
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace(" ", " ").replace("　", " ")
    return re.sub(r"\s+", " ", s).strip()


def _get(url):
    return htmlmod.unescape(sc.fetch(url))


# ---------------------------------------------------------------- scrape

def _parse_entries(h, venue_kanji):
    """RaceList.do のHTMLから entries を作る"""
    rows = re.findall(r"<tr>\s*<td class=\"al-center bg-\d+\">.*?</tr>", h, re.S)
    entries = []
    for row in rows:
        if "PlayerDetail.do" not in row:
            continue  # 競走車成績テーブルの行は除外
        tds = re.findall(r"<td([^>]*)>(.*?)</td>", row, re.S)
        vis = [(a, c) for a, c in tds if "hideElm" not in a]
        num = None
        racer_i = None
        for i, (a, c) in enumerate(vis):
            if num is None and re.search(r"bg-\d", a):
                m = re.search(r"\d+", _clean(c))
                if m:
                    num = int(m.group(0))
            if "racer" in a and "PlayerDetail.do" in c:
                racer_i = i
        if num is None or racer_i is None:
            continue
        c = vis[racer_i][1]
        name_m = re.search(r"<strong[^>]*>(.*?)</strong>", c, re.S)
        name = _clean(name_m.group(1)) if name_m else ""
        rc = _clean(c)
        age = re.search(r"(\d+)歳/(\d+)期", rc)
        vm = re.search(r"V(\d+)/(\d+)回/V(\d+)", rc)
        bike_m = re.search(r"ownerBikeBtn[^>]*>(.*?)</a>", c, re.S)
        bike = _clean(bike_m.group(1)).replace("▼", "").strip() if bike_m else ""

        # racer セル以降: [LG, ハンデ/試走, 現ランク/審査P, 平均T, 近10走+近90日, 近180日, 前走×5]
        rest = [_clean(c2) for _, c2 in vis[racer_i + 1:]]
        lg = rest[0].replace(" ", "") if len(rest) > 0 else ""
        hande = ""
        if len(rest) > 1:
            m = re.search(r"(\d+)m", rest[1])
            hande = m.group(1) + "m" if m else ""
        rank = prev_rank = point = ""
        if len(rest) > 2:
            m = re.search(r"([SAB]-\d+)", rest[2])
            rank = m.group(1) if m else ""
            m = re.search(r"\(([SAB]-\d+)\)", rest[2])
            prev_rank = m.group(1) if m else ""
            m = re.search(r"(\d+\.\d+)\s*$", rest[2])
            point = m.group(1) if m else ""
        avg_trial = avg_race = best_race = ""
        if len(rest) > 3:
            fs = re.findall(r"\d\.\d{2,3}", rest[3])
            if len(fs) >= 3:
                avg_trial, avg_race, best_race = fs[0], fs[1], fs[2]
            elif len(fs) == 2:
                avg_trial, avg_race = fs[0], fs[1]
        k10 = st10 = k90 = ""
        p2 = p3 = []
        if len(rest) > 4:
            ks = re.findall(r"着順：([0-9\-]+)\s*([0-9]\.[0-9]+)?", rest[4])
            if len(ks) > 0:
                k10, st10 = ks[0][0], ks[0][1]
            if len(ks) > 1:
                k90 = ks[1][0]
            p2 = re.findall(r"2連\s*：\s*([0-9.]+%)", rest[4])
            p3 = re.findall(r"3連\s*：\s*([0-9.]+%)", rest[4])
        good2 = wet2 = ""
        if len(rest) > 5:
            m = re.findall(r"良：([0-9.]+%)", rest[5])
            good2 = m[0] if m else ""
            m = re.findall(r"湿：([0-9.]+%)", rest[5])
            wet2 = m[0] if m else ""
        prevs = []  # [(場名, 着), ...] 直近が先頭
        for cell in rest[6:11]:
            m = re.search(r"(\d+/\d+)\s+(\S+?)(\d+)R", cell)
            if not m:
                continue
            pv = m.group(2)
            fin_m = re.search(r"(\d+)着", cell)
            if fin_m:
                fin = fin_m.group(1)
            else:
                fin_m = re.search(r"(失格|落車|欠車|欠場|事故|反則|再走)", cell)
                fin = fin_m.group(1)[0] if fin_m else "?"
            prevs.append((pv, fin))

        # detail: AI予想の判断材料を1行に圧縮
        parts = ["ハンデ" + (hande or "?")]
        r = rank or "?"
        if prev_rank:
            r += "(前" + prev_rank + ")"
        if point:
            r += "点" + point
        parts.append(r)
        prof = lg
        if age:
            prof += age.group(1) + "歳" + age.group(2) + "期"
        if prof:
            parts.append(prof)
        if vm and vm.group(3) != "0":
            parts.append("通算V" + vm.group(3))
        if bike:
            parts.append("車" + bike.split("/")[0])
        if avg_race:
            t = "平均競走T" + avg_race
            ex = []
            if avg_trial:
                ex.append("試" + avg_trial)
            if best_race:
                ex.append("最高" + best_race)
            if ex:
                t += "(" + "/".join(ex) + ")"
            parts.append(t)
        if k10:
            t = "近10走着別" + k10
            if st10:
                t += " ST" + st10
            if len(p2) > 0:
                t += " 2連" + p2[0]
            if len(p3) > 0:
                t += "3連" + p3[0]
            parts.append(t)
        if k90:
            t = "近90日着別" + k90
            if len(p2) > 1:
                t += " 2連" + p2[1]
            if len(p3) > 1:
                t += "3連" + p3[1]
            parts.append(t)
        if good2 or wet2:
            parts.append("良2連" + (good2 or "-") + "湿2連" + (wet2 or "-"))
        if prevs:
            parts.append("前5走:" + "・".join(v + f for v, f in prevs))
            v2 = venue_kanji[:2]
            here = [f for v, f in prevs if v.startswith(v2)]
            if here:
                parts.append("当地近走" + "-".join(here) + "着")

        entries.append({
            "num": num,
            "name": name,
            "sub": ((rank or "?") + " " + (hande or "")).strip(),
            "detail": " ".join(parts)[:250],
        })
    return entries


def scrape_day(date):
    """date="YYYYMMDD" の全開催・全レースの出走表。開催なしなら None。"""
    venues = []
    for romaji, (cd, kanji) in VENUES.items():
        try:
            day = _get("%s/OneDayRaceList.do?raceDy=%s&placeCd=%s" % (BASE_URL, date, cd))
        except Exception:
            continue
        tm = re.search(r"<title>(.*?)</title>", day, re.S)
        title = tm.group(1) if tm else ""
        if kanji not in title or "出走表" not in title:
            continue  # この場は開催なし
        grade = ""
        hm = re.search(r"<h3>(.*?)</h3>", day, re.S)
        if hm:
            gm = re.search(r"alt=\"(SG|GP|G1|G2|G3)\"", hm.group(1))
            if gm:
                grade = gm.group(1)
        # レース一覧（番号・名称・距離・発走時刻）
        race_defs = {}
        pat = re.compile(
            r"RaceList\.do\?raceDy=%s&(?:amp;)?placeCd=%s&(?:amp;)?raceNo=(\d+)\">\s*(\d+)R(.*?)</a>" % (date, cd),
            re.S)
        for m in pat.finditer(day):
            no = int(m.group(2))
            if no in race_defs:
                continue
            txt = _clean(m.group(3))
            cm = re.search(r"([\d,]+m\([^)]*\))\s*$", txt)
            course = cm.group(1) if cm else ""
            name = txt[:cm.start()].strip() if cm else txt
            seg = day[m.end():m.end() + 500]
            t = re.search(r"start-time\">.*?<strong>(\d{1,2}:\d{2})</strong>", seg, re.S)
            race_defs[no] = (name or "一般戦", course, t.group(1) if t else "")
        races = []
        for no in sorted(race_defs):
            name, course, start = race_defs[no]
            try:
                rl = _get("%s/RaceList.do?raceDy=%s&placeCd=%s&raceNo=%d" % (BASE_URL, date, cd, no))
                entries = _parse_entries(rl, kanji)
            except Exception:
                entries = []
            if not entries:
                continue
            races.append({
                "race_id": "A%s_%s_%02d" % (date, romaji, no),
                "no": no,
                "name": name,
                "time": start,
                "course": course,
                "grade": "",
                "head": len(entries),
                "entries": entries,
            })
        if races:
            venues.append({"name": kanji, "grade": grade, "races": races})
    if not venues:
        return None
    return {"type": TYPE, "label": LABEL, "venues": venues}


# ---------------------------------------------------------------- result

def fetch_result(race_id):
    """1レースの確定結果。未確定・未発売・中止なら None。"""
    m = re.match(r"^A(\d{8})_([a-z]+)_(\d{1,2})$", race_id)
    if not m or m.group(2) not in VENUES:
        return None
    date, romaji, no = m.group(1), m.group(2), int(m.group(3))
    cd = VENUES[romaji][0]
    try:
        h = _get("%s/RaceResult.do?raceDy=%s&placeCd=%s&raceNo=%d" % (BASE_URL, date, cd, no))
    except Exception:
        return None
    # 存在しないraceNo指定時にサーバが別レースへフォールバックするためガード
    rm = re.search(r"<span class=\"R\d+\">R(\d+)</span>", h)
    if not rm or int(rm.group(1)) != no:
        return None
    tm = re.search(r"<table[^>]*summary=\"レース結果\"[^>]*>(.*?)</table>", h, re.S)
    if not tm:
        return None  # 未確定・中止
    top = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tm.group(1), re.S):
        cells = [_clean(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        if len(cells) < 3 or not cells[0].isdigit():
            continue
        rank = int(cells[0])
        car = cells[2]
        if rank in (1, 2, 3) and rank not in top and car.isdigit():
            top[rank] = int(car)
    top3 = [top[r] for r in (1, 2, 3) if r in top]
    if not top3:
        return None
    payouts = {}
    cur = None
    pat = re.compile(
        r"<th[^>]*>\s*(単勝|複勝|ワイド|2連複|2連単|3連複|3連単)\s*</th>"
        r"|<td class=\"num\">(.*?)</td>\s*<td class=\"al-right kin\">(.*?)</td>",
        re.S)
    for mm in pat.finditer(h):
        if mm.group(1):
            cur = BET_MAP.get(mm.group(1))
            continue
        if not cur:
            continue
        nums = [int(x) for x in re.findall(r"\d+", _clean(mm.group(2)))]
        am = re.search(r"([\d,]+)円", _clean(mm.group(3)))
        if not nums or not am:
            continue  # 特払い・発売なし等
        payouts.setdefault(cur, []).append([nums, int(am.group(1).replace(",", ""))])
    return {"top3": top3, "payouts": payouts}


# ---------------------------------------------------------------- CLI

def main():
    if len(sys.argv) < 3:
        print("usage: python3 mod_auto.py scrape YYYYMMDD | result <race_id>")
        return
    cmd, arg = sys.argv[1], sys.argv[2]
    if cmd == "scrape":
        obj = scrape_day(arg)
        if obj is None:
            print("開催なし:", arg)
            return
        path = sc.save_data(arg, TYPE, obj)
        n = sum(len(v["races"]) for v in obj["venues"])
        print("saved:", path)
        print("%d場 %dレース" % (len(obj["venues"]), n))
        for v in obj["venues"]:
            rs = v["races"]
            print(" %s%s %dR (%s-%s) 例:%s" % (
                v["name"], "[%s]" % v["grade"] if v["grade"] else "",
                len(rs), rs[0]["time"], rs[-1]["time"], rs[0]["race_id"]))
    elif cmd == "result":
        print(json.dumps(fetch_result(arg), ensure_ascii=False, indent=1))
    else:
        print("unknown command:", cmd)


if __name__ == "__main__":
    main()
