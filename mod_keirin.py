#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mod_keirin.py — レーススカウト 競輪モジュール

データソース: オッズパーク競輪（サーバレンダリングHTML・安定）
  開催一覧   : https://www.oddspark.com/keirin/RaceListInfo.do?kaisaiBi=YYYYMMDD
  場別レース : https://www.oddspark.com/keirin/AllRaceList.do?joCode=XX&kaisaiBi=YYYYMMDD
  出走表     : https://www.oddspark.com/keirin/RaceList.do?joCode=XX&kaisaiBi=YYYYMMDD&raceNo=R
  結果/払戻  : https://www.oddspark.com/keirin/RaceKekka.do?joCode=XX&kaisaiBi=YYYYMMDD&raceNo=R

race_id 形式: "K{YYYYMMDD}_{joCode}_{RR}"
  例 "K20260719_74_01"
  → 結果URL https://www.oddspark.com/keirin/RaceKekka.do?joCode=74&kaisaiBi=20260719&raceNo=1
  （joCode はオッズパークの競輪場コード。race_id だけから結果URLを再構築できる）

race に追加フィールド:
  line    : ライン(並び)予想 例 "1-3 / 2-6 / 7 / 5-4"（取れた場合のみ）
  comment : オッズパーク記者の展開総評（取れた場合のみ）
"""
import re
import sys
import json

from sports_common import fetch, strip_tags, save_data

BASE_URL = "https://www.oddspark.com/keirin"

# 全角英数字・記号 → 半角
_Z2H = {i: i - 0xFEE0 for i in range(0xFF01, 0xFF5F)}
_Z2H[0x3000] = 0x20  # 全角スペース

GRADE_MAP = {"gp": "GP", "g1": "G1", "g2": "G2", "g3": "G3", "f1": "F1", "f2": "F2"}


def _z2h(s):
    return s.translate(_Z2H)


def _clean(s):
    """タグ除去+全角正規化+空白圧縮"""
    return re.sub(r"\s+", " ", _z2h(strip_tags(s))).strip()


# ---------------------------------------------------------------- scrape_day

def scrape_day(date):
    """date="YYYYMMDD" の全開催・全レースの出走表を返す。開催なしなら None。"""
    idx_html = fetch(f"{BASE_URL}/RaceListInfo.do?kaisaiBi={date}")
    vmeta = _parse_day_index(idx_html, date)
    if not vmeta:
        return None
    venues = []
    for vm in vmeta:
        jo = vm["jo"]
        try:
            all_html = fetch(f"{BASE_URL}/AllRaceList.do?joCode={jo}&kaisaiBi={date}")
        except Exception:
            continue
        race_nos = sorted({int(n) for n in re.findall(
            r'raceNo=(\d+)"[^>]*>第\d+R&nbsp;', all_html)})
        races = []
        for no in race_nos:
            try:
                rhtml = fetch(f"{BASE_URL}/RaceList.do?joCode={jo}&kaisaiBi={date}&raceNo={no}")
                race = _parse_race(rhtml, date, jo, no)
            except Exception:
                race = None
            if race and race["entries"]:
                races.append(race)
        if races:
            venues.append({"name": vm["name"], "grade": vm["grade"], "races": races})
    if not venues:
        return None
    return {"type": "keirin", "label": "競輪", "venues": venues}


def _parse_day_index(html, date):
    """RaceListInfo.do から当日開催の場一覧 [{name, grade, jo}] を得る"""
    out = []
    for block in re.split(r'<ul class="bank">', html)[1:]:
        jo = re.search(r"AllRaceList\.do\?joCode=(\d+)", block)
        name = re.search(r"<li>\s*([^<\s][^<]*?)\s*</li>", block)
        if not jo or not name:
            continue
        grade = ""
        gm = re.search(r'<ul class="grade">(.*?)</ul>', block, re.S)
        if gm:
            for cls in re.findall(r'class="(\w+)"', gm.group(1)):
                if cls.lower() in GRADE_MAP:
                    grade = GRADE_MAP[cls.lower()]
                    break
        out.append({"name": _clean(name.group(1)), "grade": grade, "jo": jo.group(1)})
    return out


def _parse_race(html, date, jo, no):
    """RaceList.do 1ページ → race dict"""
    m = re.search(r"第(\d+)レース&nbsp;\(([^)]+)\)", html)
    rname = _clean(m.group(2)) if m else ""
    tm = re.search(r"発走時間</span>\s*<strong>(\d{1,2}):(\d{2})</strong>", html)
    time_s = "%02d:%s" % (int(tm.group(1)), tm.group(2)) if tm else ""
    dm = re.search(r"(\d{3,4})m&nbsp;", html)
    course = dm.group(1) + "m" if dm else ""
    entries = _parse_entries(html)
    race = {
        "race_id": "K%s_%s_%02d" % (date, jo, no),
        "no": no,
        "name": rname,
        "time": time_s,
        "course": course,
        "grade": "",
        "head": len(entries),
        "entries": entries,
    }
    line = _parse_line(html)
    if line:
        race["line"] = line
    cm = re.search(r'class="keirinRyosousouhyo">([^<]+)<', html)
    if cm:
        race["comment"] = _clean(cm.group(1))
    return race


def _parse_entries(html):
    entries = []
    for chunk in re.split(r'<tr class="bg-\d+-pl">', html)[1:]:
        chunk = chunk.split("</tr>")[0]
        tds = re.findall(r"<td\b[^>]*>.*?</td>", chunk, re.S)
        # 車番セル(class="noN")の位置を基準に後続セルを読む
        base = None
        num = 0
        for i, td in enumerate(tds):
            mm = re.match(r'<td class="no(\d+)">', td)
            if mm:
                base = i
                num = int(mm.group(1))
                break
        if base is None:
            continue

        def td_at(k):
            return tds[base + k] if base + k < len(tds) else ""

        name_td = td_at(2)
        nm = re.search(r'PlayerDetail\.do\?playerCd=\d+"\s*>([^<]+)</a>', name_td)
        if not nm:
            continue  # 欠車など
        name = re.sub(r"[\s　]+", "", nm.group(1))
        ag = re.search(r"(\d+)歳／(\d+)期", name_td)
        age, ki = (ag.group(1), ag.group(2)) if ag else ("", "")
        pref = _clean(td_at(3))
        klass = _clean(td_at(4)).replace(" ", "")  # 級班 (SS/S1/S2/A1/A2/A3/L1)
        gear_cell = _clean(td_at(5))
        gears = re.findall(r"\d\.\d+", gear_cell)
        gear = gears[-1] if gears else ""
        kyaku = re.findall(r"[逃両追]", gear_cell)
        kyaku = kyaku[-1] if kyaku else ""
        stat_cell = _clean(td_at(6))
        pt = re.search(r"競走得点\s*[:：]\s*([\d.]+)", stat_cell)
        chaku = re.search(r"着\s*順\s*[:：]\s*(\d+)-\s*(\d+)-\s*(\d+)-\s*(\d+)", stat_cell)
        kimari = re.search(r"決まり手\s*[:：]\s*(\d+)-\s*(\d+)-\s*(\d+)-\s*(\d+)", stat_cell)

        parts = []
        parts.append((klass + " " + pref).strip())
        if ki:
            parts.append("%s期%s歳" % (ki, age))
        if kyaku or gear:
            parts.append((kyaku + gear).strip())
        if pt:
            parts.append("得点" + pt.group(1))
        if chaku:
            parts.append("着%s-%s-%s-%s" % chaku.groups())
        if kimari:
            parts.append("決逃%s捲%s差%sマ%s" % kimari.groups())
        for label, k in (("今:", 7), ("前:", 8), ("前々:", 9)):
            s = _fmt_basho(td_at(k))
            if s:
                parts.append(label + s)

        entries.append({
            "num": num,
            "name": name,
            "sub": (klass + " " + pref).strip(),
            "detail": " ".join(parts),
        })
    entries.sort(key=lambda e: e["num"])
    return entries


_RESULT_LINE = re.compile(r"^(\d+/ ?\d+)\s+(.+)$")


def _fmt_basho(td):
    """今場所/前場所/前々場所セル → '別府F2ミ(7/4チ予選3着11.4/…)' 形式。
    今場所は場名行が無く成績行のみ → '7/19チ予選3着' 形式になる。"""
    if not td:
        return ""
    suffix = ""
    if "midnight" in td:
        suffix = "ミ"
    elif "morning" in td:
        suffix = "モ"
    lines = [_clean(x) for x in re.split(r"<br\s*/?>", td)]
    lines = [x for x in lines if x]
    if not lines:
        return ""
    venue = ""
    if not _RESULT_LINE.match(lines[0]):
        venue = lines[0].replace(" ", "") + suffix
        lines = lines[1:]
    res = []
    for ln in lines:
        mm = _RESULT_LINE.match(ln)
        if mm:
            res.append(mm.group(1).replace(" ", "") + mm.group(2).replace(" ", ""))
    if not res:
        return venue
    if not venue:
        return "/".join(res)
    return "%s(%s)" % (venue, "/".join(res))


def _parse_line(html):
    """ライン(並び)予想 → '1-3 / 2-6 / 7 / 5-4' 形式。無ければ None"""
    m = re.search(r'<ul class="keirinRyosouline">(.*?)</ul>', html, re.S)
    if not m:
        return None
    groups, cur = [], []
    for n in re.findall(r'<span class="no(\d+)">', m.group(1)):
        n = int(n)
        if n == 0:
            if cur:
                groups.append(cur)
            cur = []
        else:
            cur.append(str(n))
    if cur:
        groups.append(cur)
    if not groups:
        return None
    return " / ".join("-".join(g) for g in groups)


# -------------------------------------------------------------- fetch_result

# RaceKekka.do 内のコメントマーカー → 券種キー
_PAYOUT_KEYS = {"2車複": "nirenpuku", "2車単": "nirentan",
                "3連複": "sanrenpuku", "3連単": "sanrentan"}


def fetch_result(race_id):
    """1レースの確定結果。未確定・未発売・中止なら None。"""
    m = re.match(r"^K(\d{8})_(\d+)_(\d+)$", race_id)
    if not m:
        return None
    date, jo, no = m.group(1), m.group(2), int(m.group(3))
    html = fetch(f"{BASE_URL}/RaceKekka.do?joCode={jo}&kaisaiBi={date}&raceNo={no}")

    rows = re.findall(r'<td rowspan="\d+">(\d+)</td>\s*<td class="no(\d+)">', html)
    rows = sorted(((int(r), int(c)) for r, c in rows))
    if len(rows) < 3:
        return None
    top3 = [c for r, c in rows[:3]]

    payouts = {}
    i = html.find("払戻結果")
    seg = html[i:] if i >= 0 else html
    parts = re.split(r"<!-- (2枠複|2車複|ワイド|3連複|2枠単|2車単|3連単) -->", seg)
    for k in range(1, len(parts) - 1, 2):
        key = _PAYOUT_KEYS.get(parts[k])
        if not key:
            continue
        body = parts[k + 1]
        combos = [[int(n) for n in re.findall(r'class="n(\d+)"', u)]
                  for u in re.findall(
                      r'<ul class="(?:bracket|exacta|trio)">(.*?)</ul>', body, re.S)]
        amounts = [int(a.replace(",", "")) for a in re.findall(r"([\d,]+)円", body)]
        pairs = [[c, a] for c, a in zip(combos, amounts) if c and a > 0]
        if pairs:
            payouts[key] = pairs
    if not payouts:
        return None
    return {"top3": top3, "payouts": payouts}


# ------------------------------------------------------------------- CLI

def main():
    if len(sys.argv) < 3:
        print("usage: python3 mod_keirin.py scrape YYYYMMDD | result <race_id>")
        return
    cmd, arg = sys.argv[1], sys.argv[2]
    if cmd == "scrape":
        obj = scrape_day(arg)
        if obj is None:
            print("開催なし:", arg)
            return
        path = save_data(arg, "keirin", obj)
        n_races = sum(len(v["races"]) for v in obj["venues"])
        print("保存:", path)
        print("場数: %d / レース数: %d" % (len(obj["venues"]), n_races))
        for v in obj["venues"]:
            r0, r1 = v["races"][0], v["races"][-1]
            print(" %s %s %dR (%s-%s) 例:%s" % (
                v["name"], v["grade"] or "-", len(v["races"]),
                r0["time"], r1["time"], r0["race_id"]))
    elif cmd == "result":
        print(json.dumps(fetch_result(arg), ensure_ascii=False, indent=1))
    else:
        print("unknown command:", cmd)


if __name__ == "__main__":
    main()
