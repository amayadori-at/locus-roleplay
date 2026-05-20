# Locus RP

**Obsidian-first roleplay session manager for OpenAI-compatible LLMs.**

Obsidian Vault をデータの正本として、ブラウザからロールプレイセッションを管理するローカル Web アプリケーションです。

---

## 本システムについて

- Codex / Claude Code両方を使って仕様駆動開発を行っています。
- Webフロント上でもプロンプトの編集は可能としており、LLMへ送信するプロンプトの組み立て順序も設定可能です。
  - プロンプトのノード順序や視覚的なノード操作はベータ版です。使い勝手やUI/UX上の不備などはフィードバックをください。
- OpenAI互換のAPIを提供しているエンドポイントであれば動作するはずです。テスト環境ではNanoGPTで確認を行っています。
- LLM接続ProfileとしてはRoleplay用ProfileとState, Memory更新用Profileを必要としています。
  - Roleplay用にはGLMやKimi,DeepSeekといった大規模LLMを推奨します。
  - State, Memory更新用には8B程度の軽量LLMで問題ありません。
  - ベクターストレージ用のLLMも設定することで長期セッションのRAG検索性能が向上します。
- その他バグの報告や、機能要望はお気軽に起票をお願いします。ある程度のバグ取りやUX最適化は行っていますが、個人開発だと気付ける範囲に限界があるため。

---

## 特徴

- **Obsidian Vault 連携** — シナリオ・キャラクター設定・Lore・ペルソナ・セッションログをすべて Vault で管理。Obsidian から直接編集できます。
- **OpenAI 互換 API 対応** — ローカル LLM・クラウド API を問わず、OpenAI 互換エンドポイントを持つ任意のモデルを使用できます。
- **セッション管理** — ターン履歴・現在ステータス（State）の自動追跡、セッションの分岐・再開に対応します。
- **RAG 対応** — Memory・Lore・キャラクター設定をキーワード検索でプロンプトへ自動挿入します。
- **長期記憶** — 数ターンごとに軽量モデルがセッション要約を Vault へ書き込みます。
- **インライン画像** — GM 応答中に画像マーカーを挿入し、会話ログへキャラクター画像を表示します。
- **ストリーミング対応** — GM 応答をリアルタイムに受信できます。
- **1 プロセス起動** — Python サーバーが API とフロントエンド配信を兼ねます。別途 Web サーバーは不要です。

---

## 動作要件

| 項目 | 要件 |
|---|---|
| OS | Linux / macOS / Windows（WSL 推奨） |
| Python | 3.11 以上（外部ライブラリ不要） |
| Node.js | 18 以上（**ソースからビルドする場合のみ**） |
| LLM API | OpenAI 互換 API エンドポイントと API キー |

---

## セットアップ

### Release zip から起動する（推奨）

Node.js 不要、Python 3.11 以上のみ必要です。

**1. zip をダウンロードして展開する**

[Releases](https://github.com/amayadori-at/locus-roleplay/releases) から最新の `locus-rp-v*.zip` をダウンロードして展開します。

```
locus-rp-v1.0.0/
  app/
  frontend/
  server.sh       ← Linux / macOS
  server.bat      ← Windows
  .env.example
```

**2. 環境変数を設定する**

```bash
cp .env.example .env
```

`.env` を編集します。

```env
# Obsidian Vault の絶対パス（例: /home/user/MyVault）
LOCUS_VAULT_ROOT=/path/to/your/vault

# OpenAI 互換 API の Base URL と API キー
LLM_BASE_URL=https://api.example.com/v1
LLM_API_KEY=your-api-key-here
```

> API キーは `.env` にのみ記載し、リポジトリにはコミットしないでください。

**3. サーバーを起動する**

Linux / macOS:
```bash
bash server.sh
```

Windows:
```bat
server.bat
```

`http://localhost:8787` でアクセスできます。  
LAN 内の別端末からは `http://<サーバーの LAN IP>:8787` でアクセスできます（既定で `0.0.0.0` にバインドします）。

---

### ソースから起動する

**1. リポジトリのクローン**

```bash
git clone https://github.com/amayadori-at/locus-roleplay.git
cd locus-roleplay
```

**2. 環境変数の設定**

```bash
cp .env.example .env
```

`.env` を編集します（内容は上記と同じ）。

**3. フロントエンドのビルド**

```bash
cd src/frontend
npm install
npm run build
cd ../..
```

**4. サーバーの起動**

```bash
python src/app/main.py
```

`http://localhost:8787` でアクセスできます。

---

## サンプルシナリオを試す

リポジトリには `sample_vault/` にサンプルシナリオが含まれています。  
以下の手順で自分の Vault にコピーするとすぐに試せます。

### 1. Vault に `rp/` ディレクトリを作成する

Vault がまだない場合は、任意の空ディレクトリを Vault として使用できます。

```
MyVault/
└─ rp/
```

### 2. サンプルをコピーする

`sample_vault/rp/` の中身をそのまま自分の Vault の `rp/` にコピーします。

```bash
cp -r sample_vault/rp/. /path/to/your/vault/rp/
```

コピー後の構造：

```
MyVault/
└─ rp/
   ├─ scenarios/
   │  └─ luminous_goblin_crisis/   ← サンプルシナリオ
   └─ profiles/
      └─ *.json                    ← モデルプロファイル例
```

### 3. プロファイルの API 設定を編集する

`rp/profiles/` 内の JSON ファイルを開き、使用する API の `endpoint_env` / `api_key_env` が `.env` の変数名と一致していることを確認してください（デフォルトは `LLM_BASE_URL` / `LLM_API_KEY`）。

### 4. サーバーを起動してアクセスする

`http://localhost:8787` を開き、シナリオ一覧に **ルミナス王国ゴブリン大量発生** が表示されれば準備完了です。

---

## Vault の構成

Vault の詳細な説明とシナリオ作成ガイドは [`sample_vault/README.md`](sample_vault/README.md) を参照してください。

基本構造：

```
YourVault/
└─ rp/
   ├─ scenarios/      シナリオ（1シナリオ = 1ディレクトリ）
   ├─ personas/       ユーザーペルソナ
   └─ profiles/       モデルプロファイル（JSON）
```

---

## モデルプロファイルの設定

`rp/profiles/` に JSON ファイルを置くことで、使用するモデルと API 設定を管理します。

```json
{
  "id": "my_profile",
  "kind": "roleplay",
  "endpoint_env": "LLM_BASE_URL",
  "api_key_env": "LLM_API_KEY",
  "model": "your-model-id",
  "context_size": 128000,
  "temperature": 0.85,
  "max_tokens": 4096
}
```

- `endpoint_env` / `api_key_env` には `.env` の **変数名** を指定します。API キーそのものをこのファイルに書いてはなりません。
- `kind`: `roleplay`（GM 応答生成）または `state`（State 更新・記憶要約）

---

## 起動オプション

```bash
# ポートとホストの変更
python src/app/main.py --host 127.0.0.1 --port 8080

# 静的ファイルのディレクトリを明示
python src/app/main.py --static-dir /path/to/frontend/dist
```

主な環境変数：

| 環境変数 | 説明 |
|---|---|
| `LOCUS_VAULT_ROOT` | Obsidian Vault の絶対パス（必須） |
| `LOCUS_STATIC_DIR` | 静的ファイルのディレクトリ（省略可） |
| `LOCUS_EMBEDDING_MODEL` | Embedding モデル ID（省略時は RAG キーワードのみ） |

---

## ネットワークアクセス

既定では `0.0.0.0` にバインドするため、LAN 内の他端末やスマートフォンからもアクセスできます。  
公開インターネットへの露出は想定していません。

---

## 開発者向け

フロントエンドの変更をリアルタイムで確認する場合：

```bash
# ターミナル 1: Python バックエンド
python src/app/main.py --port 8787

# ターミナル 2: Vite 開発サーバー（/api を 8787 にプロキシ）
cd src/frontend
npm run dev
```

---

## ライセンス

MIT License
