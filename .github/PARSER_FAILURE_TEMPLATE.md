# パーサー精度低下

ライブANAページの解析に失敗しました。`accuracy` ワークフローが失敗しています。

## 確認手順

1. Actions の `live-accuracy` ログを確認
2. `live_snapshot.html` artifact をダウンロードしてHTML構造を確認
3. ローカルで再現:

```bash
uv run python scripts/fetch_live_validation.py
```

4. 必要に応じて `src/ana_tokutabi_watcher/services/toku_tabi_parser.py` と `src/ana_tokutabi_watcher/utils/dates.py` のセレクタ/正規表現を修正
5. `tests/fixtures/live_ana_20260904.html` を更新し、`tests/test_live_ana_parser.py` の期待値を更新
6. `pytest` と `ruff check` が通ることを確認してPRを作成

## 参考

- ANA公式: https://www.ana.co.jp/ja/jp/guide/amc/award/domestic/toku-tabi/
- `extract_all_campaign_blocks` のログでブロック分割が正しく行われているか確認してください
