#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
レーススカウト 地方競馬モジュール (type="keiba", label="地方競馬")

データソース: nar.netkeiba.com（地方競馬版netkeiba）

race_id の形式:
  netkeiba(NAR)ネイティブの12桁をそのまま使う。
  YYYY + 場コード(2桁) + MMDD + レース番号(2桁)
  例: 202646071901 = 2026年 金沢(46) 7月19日 1R
  結果URLは race_id だけで再構築できる:
    https://nar.netkeiba.com/race/result.html?race_id=<race_id>

使用URL:
  レース一覧   https://nar.netkeiba.com/top/race_list_sub.html?kaisai_date=YYYYMMDD
  出馬表(過去5走) https://nar.netkeiba.com/race/shutuba_past.html?race_id=XXXX&rf=shutuba_submenu
  結果+払戻    https://nar.netkeiba.com/race/result.html?race_id=XXXX
  単勝オッズAPI https://nar.netkeiba.com/api/api_get_nar_odds.html?race_id=XXXX&type=1&action=init
    ※中央の api_get_jra_odds.html は narドメインでは404。narは api_get_nar_odds.html で
      {"status":"OK","ary_odds":{"01":{"Odds":"63.4","Ninki":7},...}} 形式。

会場名はレース一覧HTMLの RaceList_DataTitle から直接取得する（地方の場コードは中央と別体系のため）。
帯広ばんえいも含む（コースは「直200m」表記）。
"""
import re
import sys
import json

from sports_common import fetch, strip_tags, save_data

TYPE = "keiba"
LABEL = "地方競馬"

LIST_URL = "https://nar.netkeiba.com/top/race_list_sub.html?kaisai_date={date}"
SHUTUBA_URL = "https://nar.netkeiba.com/race/shutuba_past.html?race_id={rid}&rf=shutuba_submenu"
RESULT_URL = "https://nar.netkeiba.com/race/result.html?race_id={rid}"
ODDS_URL = "https://nar.netkeiba.com/api/api_get_nar_odds.html?race_id={rid}&type=1&action=init"

# Icon_GradeTypeN → グレード表記（テキストが取れない場合の保険）
GRADE_MAP = {"1": "G1", "2": "G2", "3": "G3", "4": "重賞",
             "10": "JpnI", "11": "JpnII", "12": "JpnIII"}


def _no_comment(s):
    """HTMLコメントを除去（netkeiba narはコメント内に旧マークアップが残っている）"""
    return re.sub(r"<!--.*?-->", "", s, flags=re.S)


# ---------------------------------------------------------------- レース一覧

def get_venues(date):
    """[(会場名, [(race_id, grade), ...]), ...] を返す。開催なしなら []"""
    html = fetch(LIST_URL.format(date=date))
    venues = []
    # 会場ごとのブロック <dl class="RaceList_DataList"> で分割
    blocks = re.split(r'<dl class="RaceList_DataList"', html)[1:]
    for blk in blocks:
        m = re.search(r'class="RaceList_DataTitle[^"]*"[^>]*>(.*?)</p>', blk, re.S)
        if not m:
            continue
        title = re.sub(r"<small[^>]*>.*?</small>", " ", m.group(1), flags=re.S)
        name = strip_tags(title)
        races = []
        for item in re.findall(r'<li class="RaceList_DataItem.*?</li>', blk, re.S):
            ids = re.findall(r"race_id=(\d{12})", item)
            if not ids:
                continue
            grade = ""
            g = re.search(r'Icon_GradeType(\d*)[^"]*"[^>]*>([^<]*)<', item)
            if g:
                grade = g.group(2).strip() or GRADE_MAP.get(g.group(1), "")
            races.append((ids[0], grade))
        if name and races:
            # レース番号順・重複除去
            seen = {}
            for rid, gr in races:
                seen.setdefault(rid, gr)
            races = sorted(seen.items(), key=lambda x: x[0])
            venues.append((name, races))
    return venues


# ---------------------------------------------------------------- オッズ

def get_odds(race_id):
    """単勝オッズ {馬番int: (odds float, 人気int)} を返す。取れなければ None"""
    try:
        j = json.loads(fetch(ODDS_URL.format(rid=race_id)))
        ary = j.get("ary_odds") or {}
        out = {}
        for num, v in ary.items():
            try:
                o = float(v["Odds"])
                if o > 0:  # 0.0 は取消馬・発売なし
                    out[int(num)] = (o, int(v["Ninki"]))
            except (ValueError, TypeError, KeyError):
                pass
        return out or None
    except Exception:
        return None


# ---------------------------------------------------------------- 出馬表

def parse_past(cell):
    """過去1走分のPastセルを短い1行に圧縮（日付 場 着順 クラス 距離 タイム 通過 上がり）"""
    cell = _no_comment(cell)

    def pick(cls):
        m = re.search(r'class="' + cls + r'"[^>]*>(.*?)</div>', cell, re.S)
        return strip_tags(m.group(1)) if m else ""

    d1 = pick("Data01")   # 2026.06.22 金沢 6
    if not d1:
        return None
    m = re.match(r"(\d{4})\.(\d{1,2})\.(\d{1,2})\s+(\S+)\s*(\d+)?", d1)
    if m:
        head = f"{m.group(1)[2:]}.{m.group(2)}.{m.group(3)}{m.group(4)}"
        fin = f"{m.group(5)}着" if m.group(5) else "?着"
    else:
        head, fin = d1, ""
    d2 = pick("Data02").replace("　", "")[:10]        # クラス/レース名
    d5 = pick("Data05")                               # ダ1400 1:38.1 不
    d3 = pick("Data03")                               # 9頭 9番 3人 騎手 55.0
    d6 = pick("Data06")                               # 1-2-2-3 (43.7) 394(+8)
    pop = ""
    mp = re.search(r"(\d+)人", d3)
    if mp:
        pop = f"{mp.group(1)}人"
    extra = ""
    mt = re.match(r"([\d]+(?:-[\d]+)+)", d6)          # 通過順（ばんえいは無し）
    if mt:
        extra += f"通{mt.group(1)}"
    ma = re.search(r"\(([\d.]+)\)", d6)               # 上がり
    if ma and float(ma.group(1)) > 0:
        extra += f"上{ma.group(1)}"
    parts = [f"{head}{fin}", d2, d5, pop, extra]
    return " ".join(p for p in parts if p)


def parse_race(race_id, html, grade=""):
    """出馬表(shutuba_past)HTMLを spec のレースdictにする"""
    html = _no_comment(html)
    race = {"race_id": race_id, "no": int(race_id[10:12])}

    m = re.search(r'class="RaceName"[^>]*>\s*([^<\n]+)', html)
    race["name"] = strip_tags(m.group(1)) if m else f"{race['no']}R"

    m = re.search(r'RaceData01">(.*?)</div>', html, re.S)
    rd1 = strip_tags(m.group(1)) if m else ""
    m = re.search(r"(\d{1,2}:\d{2})発走", rd1)
    race["time"] = m.group(1) if m else ""
    m = re.search(r"(芝|ダ|直|障)[^\s/]*\d+m", rd1)
    race["course"] = m.group(0) if m else ""
    race["grade"] = grade

    odds = get_odds(race_id)

    entries = []
    for row in re.findall(r'<tr class="HorseList.*?</tr>', html, re.S):
        info_m = re.search(r'class="Horse_Info"[^>]*>(.*?)</td>', row, re.S)
        if not info_m:
            continue
        info = info_m.group(1)

        e = {}
        m = re.search(r'<td class="Waku(\d+)"', row)
        e["waku"] = int(m.group(1)) if m else None
        m = re.search(r'<td class="Waku"[^>]*data-sort-value="(\d+)"', row)
        if not m:
            m = re.search(r'<td class="Waku"[^>]*>\s*(\d+)', row)
        e["num"] = int(m.group(1)) if m else None
        if not e["num"]:
            continue

        def dt(cls):
            m2 = re.search(r'class="' + cls + r'[^"]*"[^>]*>(.*?)</dt>', info, re.S)
            return strip_tags(m2.group(1)) if m2 else ""

        e["name"] = dt("Horse02")
        stable = dt("Horse05").replace(" ", "")           # 例: 金沢・中川雅之
        h06 = dt("Horse06")                               # 例: 差 中1週
        m2 = re.search(r"(逃|先|差|追|自在)", h06)
        style = m2.group(1) if m2 else ""
        m2 = re.search(r"(中\d+週|連闘)", h06)
        interval = m2.group(1) if m2 else ""
        m2 = re.search(r'class="Weight"[^>]*>(.*?)</div>', info, re.S)
        weight = strip_tags(m2.group(1)).replace(" ", "") if m2 else ""

        # 騎手セル: <span class="Barei">牝3栗</span> ... 騎手名 <br /> <span>55.0</span>
        sexage = jockey = load = ""
        jk = re.search(r'class="Jockey"[^>]*>(.*?)</td>', row, re.S)
        if jk:
            seg = jk.group(1)
            m2 = re.search(r'class="Barei"[^>]*>([^<]+)', seg)
            sexage = m2.group(1).strip() if m2 else ""
            m2 = re.search(r"<span>([\d.]+)</span>", seg)
            load = m2.group(1) if m2 else ""
            seg2 = re.sub(r"<span.*?</span>", " ", seg, flags=re.S)
            jockey = strip_tags(seg2)
        e["sub"] = jockey[:12]

        pasts = []
        for p in re.findall(r'<td[^>]*class="Past"[^>]*>(.*?)</td>', row, re.S):
            t = parse_past(p)
            if t:
                pasts.append(t)

        parts = [sexage]
        if load:
            parts.append(f"{load}kg")
        if jockey:
            parts.append(jockey)
        if style or interval:
            parts.append(f"{style}{interval}")
        if weight:
            parts.append(weight)
        if stable:
            parts.append(stable)
        head_line = " ".join(p for p in parts if p)
        detail = head_line + ("｜" + "／".join(pasts[:5]) if pasts else "｜地方初出走(過去走なし)")
        e["detail"] = detail[:250]

        if odds and e["num"] in odds:
            e["odds"], e["pop"] = odds[e["num"]]
        else:
            # 出馬表ページ内のオッズ欄 (Popularブロック) を保険に使う
            m2 = re.search(r'class="Popular"[^>]*>(.*?)</div>', info, re.S)
            if m2:
                m3 = re.search(r"([\d.]+)\s*\((\d+)人気\)", strip_tags(m2.group(1)))
                if m3 and float(m3.group(1)) > 0:
                    e["odds"], e["pop"] = float(m3.group(1)), int(m3.group(2))

        entries.append(e)

    race["head"] = len(entries)
    race["entries"] = entries
    return race


def scrape_day(date):
    """date="YYYYMMDD" の全開催・全レースの出走表を返す。開催なしなら None。"""
    vlist = get_venues(date)
    if not vlist:
        return None
    venues = []
    for vname, rids in vlist:
        races = []
        for rid, grade in rids:
            try:
                html = fetch(SHUTUBA_URL.format(rid=rid))
                race = parse_race(rid, html, grade)
            except Exception as ex:
                print(f"  ! {vname} {rid} 取得失敗: {ex}", file=sys.stderr)
                continue
            races.append(race)
            print(f"  {vname}{race['no']}R {race['name']} {race['head']}頭"
                  f" odds={'あり' if any('odds' in e for e in race['entries']) else 'なし'}")
        races.sort(key=lambda r: r["no"])
        venues.append({"name": vname, "grade": "", "races": races})
    return {"type": TYPE, "label": LABEL, "venues": venues}


# ---------------------------------------------------------------- 結果

# 券種キー → (netkeibaのtrクラス, 1組の頭数)
PAYOUT_ROWS = {
    "tansho": ("Tansho", 1),
    "umaren": ("Umaren", 2),
    "sanrenpuku": ("Fuku3", 3),
    "sanrentan": ("Tan3", 3),
}


def fetch_result(race_id):
    """1レースの確定結果を返す。未確定・未発売・中止なら None。"""
    try:
        html = fetch(RESULT_URL.format(rid=race_id))
    except Exception:
        return None

    payouts = {}
    for key, (cls, n) in PAYOUT_ROWS.items():
        m = re.search(r'<tr class="' + cls + r'">(.*?)</tr>', html, re.S)
        if not m:
            continue
        seg = m.group(1)
        res = re.search(r'class="Result"[^>]*>(.*?)</td>', seg, re.S)
        nums = [int(x) for x in re.findall(r"<span>(\d+)</span>", res.group(1))] if res else []
        pays = [int(p.replace(",", "")) for p in re.findall(r"([\d,]+)円", seg)]
        groups = [nums[i:i + n] for i in range(0, len(nums), n)]
        combos = [[g, p] for g, p in zip(groups, pays) if len(g) == n]
        if combos:
            payouts[key] = combos

    if "tansho" not in payouts:
        return None  # 未確定・中止（払戻表なし）

    # 着順表(All_Result_Table)から1〜3着の馬番。取れなければ3連単の組で代用
    top3 = []
    m = re.search(r'All_Result_Table.*?<tbody>(.*?)</tbody>', html, re.S)
    if m:
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S):
            rk = re.search(r'class="Rank">(\d+)</div>', tr)
            nm = re.search(r'class="Num Waku"[^>]*>\s*<div>(\d+)</div>', tr)
            if rk and nm and int(rk.group(1)) <= 3:
                top3.append((int(rk.group(1)), int(nm.group(1))))
        top3 = [n for _, n in sorted(top3)][:3]
    if len(top3) < 3 and payouts.get("sanrentan"):
        top3 = payouts["sanrentan"][0][0]
    if len(top3) < 3:
        return None

    return {"top3": top3, "payouts": payouts}


# ---------------------------------------------------------------- CLI

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("scrape", "result"):
        print("使い方: python3 mod_keiba.py scrape YYYYMMDD | result <race_id>")
        sys.exit(1)
    if sys.argv[1] == "scrape":
        import time as _t
        date = sys.argv[2] if len(sys.argv) > 2 else _t.strftime("%Y%m%d")
        data = scrape_day(date)
        if not data:
            print(f"開催なし: {date}")
            sys.exit(1)
        path = save_data(date, TYPE, data)
        nv = len(data["venues"])
        nr = sum(len(v["races"]) for v in data["venues"])
        print(f"保存: {path} ({nv}会場 {nr}レース: "
              + " ".join(v["name"] for v in data["venues"]) + ")")
    else:
        res = fetch_result(sys.argv[2])
        print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
