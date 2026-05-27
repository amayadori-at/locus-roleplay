# Locus RP Vault

このディレクトリは **Locus RP** が実行時に読み書きするデータ領域です。  
シナリオ・ペルソナ・プロファイルをここで管理します。

---

## ディレクトリ構成

```
vault/
  rp/
    scenarios/    シナリオ（1シナリオ = 1ディレクトリ）
    personas/     ユーザーペルソナ
    profiles/     モデルプロファイル
```

---

## ペルソナ

`rp/personas/` 配下に Markdown ファイルを置きます。

```markdown
---
type: persona
id: yuuki
name: ユウキ
---

# ユウキ

ユウキの設定テキスト。
```

- `id` はファイル名と一致させてください。
- `name` がセッション画面の表示名になります。
- 本文はGMへ渡すユーザーキャラクターの設定として使用されます。

### {{user}} プレースホルダー

シナリオテキスト・Starting・GM応答内の `{{user}}` は、セッション画面で **選択中のペルソナ名** に置き換えて表示されます。

例：
```
[アリア]: 「君が最後のメンバーである{{user}}だな？」
```
→ ペルソナ名が「ユウキ」なら「君が最後のメンバーであるユウキだな？」と表示されます。

---

## プロファイル

`rp/profiles/` 配下に JSON ファイルを置きます。APIエンドポイント・モデルID・パラメータを定義します。

```json
{
  "id": "rp_kimi_2_5",
  "kind": "roleplay",
  "endpoint_env": "LLM_BASE_URL",
  "api_key_env": "LLM_API_KEY",
  "model": "moonshotai/kimi-k2.6",
  "context_size": 32768,
  "temperature": 0.8,
  "max_tokens": 2048
}
```

- `kind`: `roleplay`（GM応答）または `state`（状態更新）
- APIキーはファイルに直接書かず、環境変数名を指定してください。

---

## シナリオ構成

```
rp/scenarios/{scenario_id}/
  scenario.md          シナリオ定義（必須）
  system_prompt.md     システムプロンプト
  startings/           スタートメッセージ（複数可）
  gm/                  GMプロンプト群
  characters/          キャラクター設定
  lore/                世界設定・ロア
  assets/              画像アセット
    characters.json    キャラクター定義
    situations.json    状況定義
    images/            立ち絵・バストアップ画像
  state/               状態管理
    current.json       初期ステート
    view.html          ステート表示テンプレート（任意）
    view.css           ステート表示スタイル（任意）
  sessions/            セッションログ（自動生成）
  memory/              長期記憶（自動生成）
```

### scenario.md

YAML フロントマターでシナリオの動作を制御します。

```yaml
---
type: scenario
id: my_scenario
name: シナリオ名
image_enabled: true
image_mode: inline
missing_image_behavior: fallback_normal
memory_update_interval_turns: 4
rag_scope:
  - memory
  - lore
  - characters
---
```

| キー | 説明 |
|------|------|
| `image_enabled` | 画像表示のON/OFF |
| `image_mode` | `inline`（本文中に表示）のみ対応 |
| `missing_image_behavior` | 画像が存在しない場合の挙動。`fallback_normal`（normal.pngで代替）または `skip` |
| `memory_update_interval_turns` | 長期記憶を更新するターン間隔 |
| `rag_scope` | RAG 検索対象のカテゴリ。`memory` / `lore` / `characters` を列挙 |
| `character_rag` | キャラクター検索方式。未指定は完全一致。`{match: fuzzy}` で部分一致を許可 |

### startings/

セッション開始時に表示される最初のGMメッセージです。  
複数配置するとセッション作成時に選択できます。

フロントマターで `type: starting` と `id` を指定してください。  
本文は通常のシナリオテキストと同じ書式が使えます。

### gm/

GMへの役割・方針プロンプトを置くディレクトリです。ファイル名は自由です。  
`narration_policy.md`（文体）、`state_update_policy.md`（State更新方針）、`image_policy.md`（画像方針）などを分けて管理するのが一般的です。

### characters/

`characters/{character_id}.md` にキャラクター設定を置きます。

```yaml
---
type: character
id: aria_claudewell
name: アリア・フォン・クロードウェル
scenario: my_scenario
aliases:
  - アリア
  - Aria
role: 王国騎士
tags:
  - knight
  - companion
keywords:
  - アリア
  - 王国騎士
rag: true
priority: 90
image_character_id: aria_claudewell
---
```

| フィールド | 説明 |
|------|------|
| `type` | `character` 固定 |
| `id` | キャラクターID。ファイル名と一致させる |
| `name` | 表示名 |
| `aliases` | 別名・表記揺れ。RAG の名前マッチに使用 |
| `keywords` | 完全一致検索用の明示キーワード。`aliases` に含まれない呼称はここに追記 |
| `role` | 物語上の役割 |
| `tags` | 検索・RAG 用タグ |
| `rag` | `false` にすると RAG 対象から除外 |
| `priority` | 検索優先度（数値が大きいほど優先） |
| `image_character_id` | 画像パスで使用するID。省略時は `id` と同じ |

キャラクター検索はデフォルトで **完全一致**（`id` / `name` / `aliases` / `keywords` への一致）で動作します。  
広範な部分一致が必要な場合は `scenario.md` に `character_rag: {match: fuzzy}` を追加してください。

### lore/

`lore/{lore_id}.md` に世界設定・ロアを置きます。

```yaml
---
type: lore
id: old_library
name: 旧図書館
scenario: my_scenario
tags:
  - location
keywords:
  - 旧図書館
  - 禁書庫
keywords_enabled: true
chunk_enabled: true
rag: true
priority: 70
---
```

| フィールド | 説明 |
|------|------|
| `type` | `lore` 固定 |
| `id` | Lore ID。ファイル名と一致させる |
| `name` | 表示名 |
| `tags` | 検索・RAG 用タグ |
| `keywords` | キーワードトリガー用の完全一致キーワード |
| `keywords_enabled` | `true` にするとキーワードトリガー専用になり、通常の RAG 検索対象から除外される |
| `chunk_enabled` | `true`（デフォルト）で `keywords_enabled: true` 時にセクション単位で投入。`false` でファイル全文を投入 |
| `rag` | `false` にすると通常 RAG 対象から除外（キーワードトリガーは止まらない。完全に止めるには `keywords_enabled: false`） |
| `priority` | 検索優先度（数値が大きいほど優先） |

#### keywords_enabled の使い分け

| 設定 | 動作 |
|------|------|
| 未設定 / `keywords_enabled: false` | 通常の RAG 検索対象。`keywords` があっても両方のルートで投入される |
| `keywords_enabled: true` | キーワードが一致したときのみ投入。組織・設定系 Lore の意図しない投入を防ぎたい場合に有効 |

`keywords_enabled: true` のファイルは `keywords` が空だとどのクエリにもヒットしません。  
空文字列のキーワードは無効です。1文字キーワードは誤爆が多いため警告対象です。

---

## `<locus-rag>` タグ

Lore や Memory の Markdown ファイル内に `<locus-rag>` タグを記述すると、**ファイル内の特定の範囲だけ**をRAG検索の単位として切り出せます。  
ファイル全体を投入せず、クエリに関係する箇所だけをプロンプトに載せたい場合に使います。

```markdown
---
type: lore
id: summoning_logic
name: 召喚ロジック
keywords:
  - 召喚
keywords_enabled: true
chunk_enabled: true
---

# 召喚ロジック概要

召喚システムの全体方針。

<locus-rag id="roster-constraint" title="召喚制約" keywords="召喚制約, サーヴァント一覧" priority="25">
召喚できるのは登録済みの30体のみ。未登録の英霊は召喚不可。
</locus-rag>

<locus-rag id="summon-random" title="ランダム召喚" keywords="ランダム召喚, おまかせ">
ランダム召喚では登録済みの英霊からランダムに一体を選出する。
</locus-rag>
```

### locus-rag の属性

| 属性 | 説明 |
|------|------|
| `id` | チャンクの識別子。ファイル内で一意にする |
| `title` | チャンクのタイトル。RAG 結果のヘッダに使用 |
| `tags` | チャンク単位の検索タグ（カンマ区切り） |
| `keywords` | チャンク単位のキーワード。ファイルレベルでキーワードがマッチしても、このキーワードが一致しないチャンクは投入されない |
| `priority` | チャンク単位の優先度（数値）。値が大きいほど優先的にプロンプトへ投入される |

### `<locus-rag>` と見出し分割の違い

| 方法 | 説明 |
|------|------|
| `<locus-rag>` タグ | 任意の範囲を明示的に区切る。キーワードや優先度をチャンク単位で設定できる |
| Markdown 見出し（`##` 等） | 見出し単位で自動分割。`chunk_enabled: true` 時に有効 |

`<locus-rag>` タグがある場合はタグ範囲が優先されます。  
タグのない部分は見出し分割、またはファイル全体として扱われます。

---

## Memory

`memory/` はアプリケーションが自動生成・更新します。手動で編集して内容を調整することもできます。

```yaml
---
type: memory
memory_kind: session_summary
scenario: my_scenario
session_id: session_001
characters:
  - user
  - aria_claudewell
locations:
  - old_library
topics:
  - hidden_key
importance: 72
created: "2026-05-25"
rag: true
---

ユーザーは旧図書館でアリアに古い鍵を見せた。アリアは鍵に強い反応を示した。
```

| フィールド | 説明 |
|------|------|
| `type` | `memory` 固定 |
| `memory_kind` | `session_summary` / `fact` / `unresolved_thread` など |
| `characters` | 関連キャラクターのID一覧 |
| `locations` | 関連場所 |
| `topics` | 関連トピック |
| `importance` | 重要度スコア（数値）。`priority` に準ずる形でスコアに反映 |
| `created` | 作成日（ISO 形式: `2026-05-25`）。**直近の memory ほど優先的に投入される。** |
| `rag` | `false` にすると RAG 対象から除外 |

`created` フィールドを記入すると、新しい記憶ほどプロンプトに載りやすくなります。  
自動生成された memory には作成日が自動付与されます。

---

## 特殊記法

### 吹き出し形式 `[名前]: 「セリフ」`

GMの応答テキスト中で以下の形式の行があり、かつそのキャラクターの **bustup.png** が存在する場合、  
テキストではなく **立ち絵＋吹き出し形式** で表示されます。

```
[アリア]: 「定刻前の集合感謝する。」
```

- `名前` はキャラクターの `id`・`name`・`short_name`・`aliases` のいずれかで一致します。
- bustup.png が存在しない場合は通常のテキストとして表示されます。
- `「」`（鉤括弧）が必須です。

### インライン画像マーカー `[[image: ...]]`

GM応答の本文中に以下の形式で画像を挿入できます。

```
[[image: aria_claudewell/serious.png]]
```

- 形式: `[[image: {character_id}/{situation_id}.png]]`
- 画像ファイルは `assets/images/{character_id}/{situation_id}.png` に置いてください。
- `image_enabled: false` のシナリオでは表示されません。

---

## 画像管理

### ディレクトリ構造

```
assets/images/{character_id}/
  bustup.png        吹き出し形式で使用するバストアップ画像
  normal.png        通常立ち絵
  serious.png       真剣立ち絵
  combat.png        戦闘立ち絵
  ...
```

対応フォーマット: `.png` / `.jpg` / `.jpeg` / `.webp` / `.gif`

### characters.json

キャラクターのID・名前・使用可能な状況を定義します。

```json
{
  "schema_version": 1,
  "scenario": "my_scenario",
  "characters": [
    {
      "id": "aria_claudewell",
      "name": "アリア・フォン・クロードウェル",
      "short_name": "アリア",
      "role": "王国騎士",
      "default_situation": "normal",
      "image_base_path": "assets/images/aria_claudewell",
      "available_situations": ["normal", "serious", "combat"],
      "fallback": "normal"
    }
  ]
}
```

### situations.json

画像の状況（ファイル名）とその説明を定義します。GMへの指示として使われます。

```json
{
  "schema_version": 1,
  "scenario": "my_scenario",
  "situations": [
    {
      "id": "normal",
      "name": "通常",
      "description": "通常立ち絵。初登場・汎用描写で使用する。",
      "fallback_allowed": false
    },
    {
      "id": "serious",
      "name": "真剣",
      "description": "重要判断、警告、緊張感のある場面で使用する。",
      "fallback_allowed": true
    }
  ]
}
```

`fallback_allowed: true` の状況は、画像が存在しない場合に `fallback`（通常は `normal`）で代替されます。

---

## セッション・記憶（自動生成）

`sessions/` と `memory/` はアプリケーションが自動で生成・更新します。  
手動で編集する必要はありませんが、Obsidian で読むことができます。
