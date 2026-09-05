# Claude Code 引き継ぎ資料 — ANAトクたび監視 (ana-tokutabi-watcher)

**作成日**: 2026-09-05 JST  
**作成者**: Muse Spark (opencode/muse-spark-1.2-contributor-free) → Claude Code へ引き継ぎ  
**リポジトリ**: https://github.com/harkingbee/ana-tokutabi-watcher (public, main: `25f613f` 以降)  
**ローカルパス**: `/Users/harkingbee/opne code/project/ana_tokutabi_watcher`  
**親monorepo**: `/Users/harkingbee/opne code/project` (git管理外のサブプロジェクトとして内包)

---

## 1. プロジェクト要旨

ANA公式「今週のトクたびマイル」ページ (`https://www.ana.co.jp/ja/jp/guide/amc/award/domestic/toku-tabi/`) から大阪発着（ITM/KIX/UKB）の対象路線を毎週検出し、予約発券期間中は毎時00分に空席監視（安全モードではリンク生成）してDiscordへEmbed通知する。

**最重要方針**（`README.md:5-6`, `config.example.yaml:3`）:
- ANA利用規約・robots.txt厳守、CAPTCHA/OTP回避なし、非公開API推測なし
- デフォルト `availability_mode: safe_link_only`（`src/ana_tokutabi_watcher/services/availability_checker.py:36`）。予約代行ではない
- 会員ID/パスワードの保存・ログ出力なし、JST固定

---

## 2. 技術スタックと構成

- **Python 3.12**, 依存管理 `uv` + `pyproject.toml:1-33`
- `httpx` (HTTP) / `beautifulsoup4+lxml` (HTML) / `APScheduler` (Cron) / `pydantic-settings+YAML` / `SQLAlchemy+SQLite` / `tenacity` / `structlog` / `typer` (CLI)
- `pytest` / `ruff` (line-length 120) / `mypy`

### ディレクトリ構成 (spec準拠)

```
ana_tokutabi_watcher/
  pyproject.toml, README.md, .env.example, config.example.yaml, Dockerfile, docker-compose.yml
  src/ana_tokutabi_watcher/
    main.py:1           CLI (fetch-routes/show-routes/check-availability/run-scheduler/test-discord/dry-run)
    config.py:1         AppConfig + EnvSettings (pydantic-settings)
    database.py:1       SQLite engine/session
    models.py:1         CampaignSnapshot/TokuTabiRoute/AvailabilityObservation/NotificationRecord
    repositories.py:1   保存・重複排除
    scheduler.py:1      APScheduler (水曜00:00+リトライ3回、毎時00分)
    clients/ana_public_page_client.py:1  公開ページ取得（指数バックオフ）
    services/toku_tabi_parser.py:1       期間・路線パーサー（精度向上の核心）
    services/route_normalizer.py:1       大阪正規化
    services/availability_checker.py:1   SafeLinkOnly/Browser Protocol
    services/discord_notifier.py:1       Embed生成
    services/notification_deduplicator.py:1 SHA256キー・24h再通知
    utils/dates.py:1                     期間パース（から/〜両対応）
    utils/urls.py:1                      公式URL生成
  tests/fixtures/sample_tokutabi.html / live_ana_20260904.html
  tests/test_*.py
  scripts/fetch_live_validation.py       GitHub精度検証用ライブ取得
  .github/workflows/ci.yml / accuracy.yml
```

### DBテーブル (`src/ana_tokutabi_watcher/models.py:10-50`)

- `campaign_snapshots`: fetched_at, booking_start/end, travel_start/end, raw_hash
- `toku_tabi_routes`: origin, destination, miles, route_text
- `availability_observations` / `notification_records` (キー: SHA256(origin|destination|date|flight|time|miles))

---

## 3. 現状（何ができたか）

### 3.1 初期実装 (spec全要件)

- 全CLIコマンド実装・動作確認済み:
  ```bash
  uv run ana-tokutabi fetch-routes --dry-run
  uv run ana-tokutabi fetch-routes
  uv run ana-tokutabi show-routes
  uv run ana-tokutabi check-availability --dry-run  # 予約期間外はskip、期間内はEmbed出力、2回目は重複排除で0件
  uv run ana-tokutabi test-discord --dry-run
  uv run ana-tokutabi dry-run
  uv run ana-tokutabi run-scheduler
  ```
- `pytest 20 passed`, `ruff check` / `ruff format --check` 合格（CIでも確認済み）
- Docker/Docker Compose、GitHub Actions CI (`ci.yml`) 完備

### 3.2 GitHub活用による精度向上 (今回の追加)

**背景**: 初期パーサーは `sample_tokutabi.html` では動作したが、ライブページでは以下が判明:
- 期間表記が「2026年8月26日（水）0:00から9月1日（火）23:59まで」「2026年9月2日（水）から9月8日（火）搭乗分」と「から」区切り
- 2週間分（9/2-9/8 と 9/9-9/15）が同居し、旧ロジックは全路線をマージして誤った搭乗期間に紐付け
- ルート行以外に「発着を表します」「変更可能です」など `⇔` を含むノイズ

**改善内容**:

1. **ライブ取得と分析** (`/tmp/ana_live.html` 675KB を `curl` + `webfetch` で取得、類似リポジトリ `harkingbee/ana-award-discord-reminder`, `solaseed-award-seat-watcher` を `gh api` で参照)
2. **`utils/dates.py:13-19`** に `RE_PERIOD_KARA` / `RE_PERIOD_TILDE` 追加、`parse_period` で「から」優先、年省略補完、年跨ぎ対応、`extract_all_periods` 追加
3. **`services/toku_tabi_parser.py:34-94`** `_parse_periods` を空行除去＋見出し以降のみのwindowに修正、キーワードを `予約発券期間` / `対象搭乗期間` に厳格化、誤検出を防止
4. **`extract_all_campaign_blocks:101-160`** 新規: `予約発券期間` を起点にブロック分割し、各ブロックの `booking/travel` と `routes_by_miles` を分離
5. **HTML優先抽出**: `p`タグのみを対象、`⇔` が1つかつ40文字未満、ブラックリストでノイズ除外、ブロック一致時は該当ブロックの路線で上書き（`parse_campaign_html:314-341`）
6. **実データfixture**: `tests/fixtures/live_ana_20260904.html`（フルページ）と `tests/test_live_ana_parser.py`（4 tests）追加。検証で `booking 2026-08-26 / travel 2026-09-02 / osaka 7件 / ブロック2件` が安定
7. **GitHub精度運用**:
   - 新規リポジトリ `harkingbee/ana-tokutabi-watcher` 作成・`git push`（`gh repo create`）
   - `.github/workflows/accuracy.yml` 毎日00:30 JSTにライブ検証、`scripts/fetch_live_validation.py` で `live_snapshot.json/html` をartifact保存、失敗時Issue自動作成
   - `.github/dependabot.yml`, `ISSUE_TEMPLATE`, `PARSER_FAILURE_TEMPLATE.md`, READMEバッジ追加
   - CIは `line-length 120` に変更し `ruff format` で全ファイル整形、push後に `CI success` / `Accuracy success` を確認

**現在のライブ検証結果** (`uv run python scripts/fetch_live_validation.py`):

```
booking=2026-08-26 travel=2026-09-02 routes=30 osaka=7 normalized=7
blocks: [3500,5500,6500] / [3500,5500,6500,7500]
```

---

## 4. GitHub運用の詳細

- **リポジトリ**: https://github.com/harkingbee/ana-tokutabi-watcher
- **ブランチ**: `main`、最新 `25f613f` (style: ruff format)
- **Actions**:
  - `CI` (.github/workflows/ci.yml:1): `uv pip install -e ".[dev]"` → `ruff check` → `ruff format --check` → `pytest -v`
  - `Accuracy Check (Live Page)` (.github/workflows/accuracy.yml:1): `cron: 30 15 * * *` (15:30 UTC = 00:30 JST), `workflow_dispatch`, pushトリガー。`scripts/fetch_live_validation.py:1` を実行
  - Dependabot PRは `actions/checkout v7` 等で現在失敗中（`gh run list` で確認）。本体CIには影響なし。必要なら `ci.yml` の `actions/checkout@v4` を `v4` 固定のままにするか、dependabotを `github-actions` のみに限定する
- **手動実行**: `gh workflow run "Accuracy Check (Live Page)" --repo harkingbee/ana-tokutabi-watcher`
- **ログ確認**: `gh run view <id> --repo harkingbee/ana-tokutabi-watcher --log-failed`

---

## 5. Claude Code で継続する際の手順

### 5.1 環境セットアップ

```bash
cd "/Users/harkingbee/opne code/project/ana_tokutabi_watcher"
uv sync --extra dev
cp config.example.yaml config.yaml   # 必要に応じて編集
cp .env.example .env                 # DISCORD_WEBHOOK_URL を記入
# GitHub CLI 認証済みか確認
gh auth status
```

### 5.2 よく使うコマンド

```bash
# テスト・Lint
uv run pytest -v
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# パーサー単体検証
uv run python scripts/fetch_live_validation.py --output live_snapshot.json
cat live_snapshot.json | jq .osaka_routes

# CLI
uv run ana-tokutabi fetch-routes --dry-run
DATABASE_URL=sqlite:////tmp/test.db uv run ana-tokutabi check-availability --dry-run

# Docker
docker compose up -d --build && docker compose logs -f

# GitHub
gh repo view harkingbee/ana-tokutabi-watcher
gh run list --repo harkingbee/ana-tokutabi-watcher --limit 5
```

### 5.3 パーサーを修正する際のフロー

1. ライブページを再取得: `curl -s -A "ana-tokutabi-watcher/0.1" https://www.ana.co.jp/ja/jp/guide/amc/award/domestic/toku-tabi/ -o /tmp/ana_live.html`
2. `src/ana_tokutabi_watcher/services/toku_tabi_parser.py` と `utils/dates.py` を修正
3. ローカルで `uv run pytest tests/test_live_ana_parser.py -v` と `uv run python scripts/fetch_live_validation.py` で検証
4. fixture更新が必要なら `cp /tmp/ana_live.html tests/fixtures/live_ana_20260904.html` し、`tests/test_live_ana_parser.py` の期待値を更新
5. `uv run ruff format src/ tests/` して `git push`

### 5.4 注意事項（Claude Code特有）

- このプロジェクトは `ana_tokutabi_watcher/` が **単独gitリポジトリ**（`origin` は `ana-tokutabi-watcher`）。親の `project/` は別monorepoなので、コミット時は `workdir` を正しく指定すること
- `.env` / `data/*.db` は `.gitignore:1` で除外。Discord Webhookは `gh secret` ではなくローカル `.env` で管理（Actionsでは `DISCORD_WEBHOOK_URL` を Secrets に登録して使う想定）
- ANAサイトへのアクセスは `rate_limit.min_seconds_between_requests:10` を守り、大量検証をしないこと（`utils/urls.py:1` は入口URLのみを返す設計）
- `availability_mode` は `safe_link_only` を維持。`browser_public_only` は `clients/ana_availability_client.py:1` が無効化されていることを確認

---

## 6. 今後のTODO / 既知の課題

- [ ] Dependabotの `actions/checkout v7` / `setup-python v7` PRがCI失敗中。`ci.yml` を v4 固定にするか、ワークフローを v7 互換に更新
- [ ] `live_ana_20260904.html` が675KBと大きい。Git LFSやトリミング（`available-flights` セクションのみ抽出）への移行を検討。現状は `accuracy.yml` が毎回フル取得するため問題なし
- [ ] 対象外期間（休止中）は `osaka_route_texts` が0件になるが、これは正常。`scripts/fetch_live_validation.py:60` では警告のみにしている
- [ ] `check-availability` の `max_requests_per_run:30` は `safe_link_only` ではリンク生成のみなので実リクエストは発生しないが、将来 `browser_public_only` を有効化する際はレート制限を厳守
- [ ] 通知の多言語対応・テストは未実装。現状は日本語固定

---

## 7. 参考ファイルパス（主要）

- `pyproject.toml:35` ruff設定
- `src/ana_tokutabi_watcher/main.py:1` CLIエントリ
- `src/ana_tokutabi_watcher/services/toku_tabi_parser.py:154` parse_campaign_html（精度向上の核心）
- `src/ana_tokutabi_watcher/utils/dates.py:38` parse_period
- `tests/test_live_ana_parser.py:1` 実データテスト
- `scripts/fetch_live_validation.py:1` ライブ検証スクリプト
- `.github/workflows/accuracy.yml:1` 精度検証ワークフロー
- `README.md:191` GitHub精度向上の説明

---

**引き継ぎ完了。Claude Codeは上記フローで `ana-tokutabi-watcher` リポジトリを継続開発してください。**
