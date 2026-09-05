# ANA 今週のトクたびマイル 大阪発着監視

[![CI](https://github.com/harkingbee/ana-tokutabi-watcher/actions/workflows/ci.yml/badge.svg)](https://github.com/harkingbee/ana-tokutabi-watcher/actions/workflows/ci.yml)
[![Accuracy](https://github.com/harkingbee/ana-tokutabi-watcher/actions/workflows/accuracy.yml/badge.svg)](https://github.com/harkingbee/ana-tokutabi-watcher/actions/workflows/accuracy.yml)

ANA公式「今週のトクたびマイル」ページから大阪（ITM/KIX/UKB）発着の対象路線を毎週自動検出し、搭乗期間の空席を監視してDiscordへ通知するPythonプロジェクトです。**GitHub Actionsによるライブページ精度検証**でHTML構造変更を早期検知します。

> **重要**: 本ツールはANAの利用規約・robots.txtを尊重し、CAPTCHA/OTP/ログイン保護を迂回しません。デフォルトは**安全モード（safe_link_only）**で、空席の自動取得は行わず公式検索URLを通知します。予約・発券操作は一切行いません。

## システム概要

1. 毎週水曜 00:00 JST（+00:01/00:05/00:15リトライ）に公式ページを取得・解析
2. 大阪発着のみ抽出・正規化してSQLiteに保存
3. 予約発券期間中は毎時00分に空席監視（APScheduler）
4. Discord Embedで通知（重複排除・再通知間隔制御）
5. 安全モードでは空席自動確認をせず、手動確認リンクを通知

```
公式ページ取得 → パーサー → 正規化 → SQLite保存 → 空席監視 → Discord通知
```

## 必要環境

- Python 3.12以上
- uv（推奨）または pip
- Discord Webhook URL

## セットアップ

```bash
cd ana_tokutabi_watcher

# 依存インストール（uv）
uv sync --extra dev
# または pip
pip install -e ".[dev]"

# 設定ファイル作成
cp config.example.yaml config.yaml
cp .env.example .env
# .env に DISCORD_WEBHOOK_URL を記入
```

### Discord Webhookの作り方

1. Discordサーバー → チャンネル設定 → 連携サービス → Webhookを作成
2. Webhook URLをコピー
3. `.env` に貼り付け:
   ```
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
   ```

### config.yaml の設定

主要項目:

```yaml
timezone: "Asia/Tokyo"
campaign_url: "https://www.ana.co.jp/ja/jp/guide/amc/award/domestic/toku-tabi/"
availability_mode: "safe_link_only"  # safe_link_only / browser_public_only / custom_api

monitor:
  origins: ["ITM", "KIX", "UKB"]
  destination_allowlist: []  # 空なら全て対象
  destination_blocklist: []  # 除外したい到着地
  max_notifications_per_run: 20
  resend_after_hours: 24    # 同一通知の再通知間隔

discord:
  enabled: true
  username: "ANAトクたび監視"
```

## 手動実行

```bash
# 対象路線を取得・保存
uv run ana-tokutabi fetch-routes

# 保存済み路線を表示
uv run ana-tokutabi show-routes

# 空席監視（予約期間外はスキップ）
uv run ana-tokutabi check-availability

# Discord送信せずEmbed JSONを表示
uv run ana-tokutabi dry-run

# Discordテスト通知
uv run ana-tokutabi test-discord
uv run ana-tokutabi test-discord --dry-run

# 保存せず表示のみ
uv run ana-tokutabi fetch-routes --dry-run
```

## 常駐実行

```bash
uv run ana-tokutabi run-scheduler
```

APSchedulerが以下を自動実行:

- 水曜 00:00 + リトライ3回で路線取得
- 毎時00分に空席監視（予約期間中のみ）

## Dockerでの起動

```bash
cp config.example.yaml config.yaml
cp .env.example .env
# .env と config.yaml を編集

docker compose up -d --build
docker compose logs -f
```

## 定期実行の選択肢

### macOS launchd

`~/Library/LaunchAgents/com.ana.tokutabi.plist`:

```xml
<key>StartCalendarInterval</key>
<dict><key>Minute</key><integer>0</integer></dict>
<key>ProgramArguments</key>
<array><string>/opt/homebrew/bin/uv</string><string>run</string><string>ana-tokutabi</string><string>check-availability</string></array>
```

### Linux systemd

`/etc/systemd/system/ana-tokutabi.service` + timer で毎時実行。

### GitHub Actions

`.github/workflows/ci.yml` はテスト用。定期実行を追加する場合:

```yaml
on:
  schedule:
    - cron: "0 * * * *"
```

> **注意**: GitHub Actionsのcronは遅延する可能性があるため、厳密な毎時00分監視にはVPS/Raspberry Pi/NAS/Cloud Run Job + Cloud Scheduler等を推奨します。Discord WebhookはGitHub Secretsで管理してください。

## ANAサイトの規約と自動アクセスの注意

- 公開ページのみ取得し、User-Agentを明示、タイムアウト設定、429/403/5xxで指数バックオフ
- 1回取得で十分な場合は繰り返しアクセスしない
- 認証が必要なページや非公開APIにはアクセスしない
- `rate_limit.min_seconds_between_requests` でアクセス間隔を制御可能
- 規約変更時は利用を停止し、設定で頻度を下げてください

## 空席通知について

- 通知は空席を保証しません。必ずANA公式サイトで最終確認してください
- 空席・必要マイルは変動します
- 本ツールは予約代行ではありません

## safe_link_onlyが初期値である理由

- ANAの空席照会はログイン・規約・bot対策があり、安全に自動化できない場合がある
- 無理にスクレイピングせず、公式検索URLを通知する安全なフォールバックをデフォルトにしています
- `browser_public_only` や `custom_api` は、公開導線上かつ規約上問題ない場合のみ有効化してください

## 実行頻度とアクセス負荷を下げる方法

```yaml
rate_limit:
  min_seconds_between_requests: 30  # 間隔を伸ばす
  max_requests_per_run: 10          # 1回の最大リクエストを減らす
monitor:
  max_notifications_per_run: 5
  destination_allowlist: ["CTS", "OKA"]  # 監視対象を絞る
schedule:
  availability_check:
    minute: 0  # 毎時1回のみ
```

## トラブルシューティング

| 症状 | 対処 |
|------|------|
| `fetch-routes`で路線が0件 | 公式ページのHTML構造変更の可能性。`tests/fixtures/sample_tokutabi.html`を参考にパーサーを確認 |
| Discord通知が届かない | `.env`のWebhook URL、DiscordのWebhook設定、ネットワークを確認。`test-discord --dry-run`でペイロード確認 |
| 予約期間外でスキップされる | `show-routes`で期間を確認。期間外は正常動作 |
| DBエラー | `data/ana_tokutabi.db`を削除して再作成、`DATABASE_URL`を確認 |

## GitHubを活用した精度向上

本プロジェクトはGitHubを活用してパーサー精度を継続的に担保します。

### ライブページ精度検証

- `tests/fixtures/live_ana_20260904.html` は実際のANA公式ページ（2026-09-04取得）のスナップショットです。`tests/test_live_ana_parser.py` がこの実データでパーサーを検証します。
- `.github/workflows/accuracy.yml` は毎日00:30 JSTにライブページを再取得し、`scripts/fetch_live_validation.py` でパース精度を検証します。成功時は `live_snapshot.json/html` をartifactとして保存、失敗時は自動でIssueを作成します。
- ローカルでも同様の検証が可能です:

```bash
uv run python scripts/fetch_live_validation.py --output live_snapshot.json
cat live_snapshot.json | jq .osaka_routes
```

### ブロック分割による精度向上

実ページでは2週間分（例: 9/2-9/8 と 9/9-9/15）が同居します。`extract_all_campaign_blocks` でブロック単位に分割し、検出した `booking_start/travel_start` に一致するブロックの路線のみを採用することで、誤った搭乗期間への紐付けを防ぎます。

### GitHubでの運用

- `gh repo view` / `gh api` で取得した類似リポジトリ（`ana-award-discord-reminder`, `solaseed-award-seat-watcher`）の知見を反映し、規約遵守の安全モードをデフォルトにしています。
- Dependabotが依存関係を週次で更新し、`accuracy` ワークフローがHTML構造変更を即時検知します。
- Issue Template（`.github/ISSUE_TEMPLATE/parser_failure.md`）で構造変更時の報告を効率化しています。

### パーサー改善の経緯

- 初期のテキストベース抽出から、HTML構造ベース（`p`タグの `⇔` 路線）への二段階抽出に改善
- 期間パースを「〜」だけでなく「〜から〜まで」「0:00から〜23:59まで」形式に対応（`RE_PERIOD_KARA`）
- ノイズ除外（`表します` `変更` `可能` など）を強化し、重複除外で精度向上
- 実ページでの検証で大阪路線の抽出精度を 7件以上で安定（2026-09-04時点で 3500/5500/6500マイルで正しく分離）

## 開発

```bash
uv run pytest -v
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run ruff format src/ tests/
# ライブ検証
uv run python scripts/fetch_live_validation.py
```

## ライセンス

MIT
