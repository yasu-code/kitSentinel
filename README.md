# kitSentinel

ミールキット予約監視システム。対象週の予約が1件もない場合にLINE通知を送る。

予約締め切りは水曜日のため、実行曜日によって監視対象週が変わる。

| 実行曜日 | 監視対象 |
|---|---|
| 月・火・水 | 来週（月〜日） |
| 木・金・土・日 | 再来週（月〜日） |

## 構成

- **本番環境:** AWS Lambda (Container) + EventBridge Scheduler + Secrets Manager
- **ローカル開発:** Docker Compose または `run_local.py`（直接実行）

## 認証情報の管理

認証情報は AWS Secrets Manager（シークレット名: `kitSentinel`）で一括管理する。

| キー名 | 説明 |
|---|---|
| `SITE_LOGIN_ID` | 予約サイトのログインID |
| `SITE_LOGIN_PW` | 予約サイトのパスワード |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API チャンネルアクセストークン |
| `LINE_USER_ID` | LINE通知先のユーザーID |

## ローカル開発環境での実行方法

### 事前準備

`.env` ファイルを編集して以下の環境変数を設定する。

| 変数名 | 説明 |
|---|---|
| `SITE_URL` | 予約サイトのログインページURL |
| `SECRETS_NAME` | Secrets Manager のシークレット名（例: `kitSentinel`） |

> **注意:** `.env` はGit管理対象外（`.gitignore` で除外済み）

AWS 認証情報（`~/.aws`）が設定済みであること（Secrets Manager へのアクセスに使用）。

---

### 方法A: Docker Compose（Lambda Runtime エミュレータ経由）

#### コンテナの起動

```bash
docker compose up --build
```

Lambda Runtime Interface Emulator が起動し、ポート `9000` でリクエストを受け付ける。

#### 実行（別ターミナルから）

**通常実行（実行曜日に応じて来週または再来週を監視）:**

```bash
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" \
  -H "Content-Type: application/json" \
  -d '{}'
```

**任意の日付を基準日に指定（テスト用）:**

```bash
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" \
  -H "Content-Type: application/json" \
  -d '{"date": "2026-03-17"}'
```

---

### 方法B: `run_local.py`（直接実行）

Docker 不要でローカルの Python 環境から直接実行できる。

```bash
# 通常実行（実行曜日に応じて来週または再来週を監視）
python run_local.py

# 任意の日付を基準日に指定（テスト用）
python run_local.py 2026-03-17
```

---

### 実行結果の例

```json
// 予約あり
{"status": "SAFE", "reserved_days": ["18", "19"]}

// 予約なし → LINE通知送信
{"status": "ALERT", "line_notify": "sent"}

// エラー
{"status": "ERROR", "reason": "browser_error"}
```

## 本番デプロイ

AWS Lambda へのデプロイは ECR 経由で行う。

```bash
# ECRへpush（コンソールを参考に）
```

### Lambda 推奨設定

| 項目 | 推奨値 |
|---|---|
| タイムアウト | 120秒以上（Playwright/Chromium 起動コストを考慮） |
| メモリ | 1024MB以上 |
| 環境変数 | `SITE_URL`, `SECRETS_NAME` |
