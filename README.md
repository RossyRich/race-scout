# レーススカウト◎

Claude が毎朝、**地方競馬・競輪・ボートレース・オートレース**の全レースを予想するスマホ向けサイト。

公開URL: https://rossyrich.github.io/race-scout/

## 仕組み

```
scrape.py（4種別の出走表収集）
  └ mod_keiba.py   … nar.netkeiba.com（地方競馬）
  └ mod_keirin.py  … 競輪
  └ mod_boat.py    … boatrace.jp（ボートレース）
  └ mod_auto.py    … オートレース
      ↓ data/YYYYMMDD_<type>.json
Claude が会場ごとに予想 → predictions/tmp_*.json
      ↓
build.py → predictions/YYYYMMDD.json（サイト表示用）
results.py → results/YYYYMMDD.json（翌朝、的中判定・払戻集計）
      ↓
git push → GitHub Pages
```

- 毎朝7:00のスケジュールタスクが RUNBOOK.md の手順で自動更新
- 自信度 S(鉄板)/A(有力)/B(混戦)/C(荒れ模様)
- 成績は種別ごとに「自信度×券種の勝敗」「回収率」を累計集計

## 手動実行

```
python3 scrape.py 20260720        # 出走表収集
python3 build.py 20260720         # 予想マージ
python3 results.py --auto         # 結果集計
```

詳細は RUNBOOK.md、モジュール仕様は docs/MODULE_SPEC.md を参照。
