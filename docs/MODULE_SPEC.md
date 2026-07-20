# レーススカウト 種別モジュール仕様

各公営競技のデータ収集モジュール `mod_<type>.py`（type = keiba / keirin / boat / auto）が守る共通仕様。
共通処理は同ディレクトリの `sports_common.py` を import して使う（fetch, strip_tags, save_data, BET_KEYS など）。
Python3 標準ライブラリのみ使用（pip 不可）。

## 必須関数

```python
def scrape_day(date: str) -> dict | None:
    """date="YYYYMMDD" の全開催・全レースの出走表を返す。開催なしなら None。"""

def fetch_result(race_id: str) -> dict | None:
    """1レースの確定結果を返す。未確定・未発売・中止なら None。"""
```

## scrape_day の返り値

```json
{
 "type": "boat",
 "label": "ボートレース",
 "venues": [
  {
   "name": "住之江",
   "grade": "G1",
   "races": [
    {
     "race_id": "B20260719_12_01",
     "no": 1,
     "name": "予選",
     "time": "10:45",
     "course": "1800m",
     "grade": "",
     "head": 6,
     "entries": [
      {"num": 1, "name": "選手名", "sub": "A1 大阪", "detail": "…予想材料を1行に圧縮…", "odds": 2.4, "pop": 1}
     ]
    }
   ]
  }
 ]
}
```

- `venues[].grade` / `races[].grade`: 分かる場合のみ（SG/G1/G2/G3/F1/F2 など）。不明なら省略か空文字。
- `time`: 発走時刻または締切予定時刻 "HH:MM"。レースの並び順ソートに使う。
- `course`: 距離・コース等の短い文字列。無ければ ""。
- `entries[].num`: 馬番/車番/艇番（int）。
- `entries[].name`: 馬名/選手名。
- `entries[].sub`: 一覧表示用の短い補足（〜12文字。騎手名、級班+支部、級別+支部 など）。
- `entries[].detail`: **AI予想の判断材料**を1行に圧縮した文字列（100〜250文字目安）。
  種別ごとに重要な情報を漏らさず入れる:
  - 地方競馬: 過去5走(着順・クラス・距離・タイム・上がり)、騎手、斤量、脚質、間隔、中央からの転入実績
  - 競輪: 級班、競走得点、脚質(逃/両/追)、府県・期別、直近成績、決まり手(逃/捲/差/マーク回数)、バック数、ライン想定に使える情報
  - ボート: 級別、全国勝率、当地勝率、モーター2連率、ボート2連率、F/L数、平均ST、今節成績
  - オート: ハンデ、級別、平均競走タイム、直近着順、当地成績
- `entries[].odds` / `pop`: 単勝オッズ・人気。取れる場合のみ（無理に取らなくてよい）。
- keiba のみ `entries[].waku`（枠番int）も入れる（枠色表示に使う）。

## race_id の規約

**race_id 文字列だけから結果ページURLを再構築できること**（翌日以降 fetch_result(race_id) だけで結果を取るため）。
形式は種別ごとに自由（例: boat は "B" + 日付 + 場コード + レース番号）。モジュール先頭のコメントに形式を明記する。

## fetch_result の返り値

```json
{
 "top3": [3, 1, 5],
 "payouts": {
  "nirenpuku": [[[1, 3], 540]],
  "nirentan": [[[3, 1], 980]],
  "sanrenpuku": [[[1, 3, 5], 1230]],
  "sanrentan": [[[3, 1, 5], 5670]]
 }
}
```

- `top3`: 1〜3着の番号。同着はどちらか一方でよい。
- `payouts`: 種別の BET_KEYS（sports_common.BET_KEYS[type]）のキーごとに `[[組(番号リスト), 配当円], ...]`。
  同着で複数組あればすべて入れる。発売なし・特払いのキーは省略してよい。
- keiba の tansho は `[[[5], 320]]` の形（1頭でもリスト）。
- レースが未確定（結果ページに払戻がまだ無い）なら None を返す。

## CLI（テスト用）

```
python3 mod_<type>.py scrape 20260719   # scrape_day を実行し data/20260719_<type>.json に保存、概要をprint
python3 mod_<type>.py result <race_id>  # fetch_result を実行し JSON をprint
```

## マナー

- リクエスト間に 0.3〜0.5 秒スリープ（sports_common.fetch が実施）。
- User-Agent は sports_common.UA。
- 1日1回の運用なのでアクセス総数はレース数+α に収める。
