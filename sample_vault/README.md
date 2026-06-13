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
---
```

| キー | 説明 |
|------|------|
| `image_enabled` | 画像表示のON/OFF |
| `image_mode` | `inline`（本文中に表示）のみ対応 |
| `missing_image_behavior` | 画像が存在しない場合の挙動。`fallback_normal`（normal.pngで代替）または `skip` |
| `memory_update_interval_turns` | 長期記憶を更新するターン間隔 |

### startings/

セッション開始時に表示される最初のGMメッセージです。  
複数配置するとセッション作成時に選択できます。

フロントマターで `type: starting` と `id` を指定してください。  
本文は通常のシナリオテキストと同じ書式が使えます。

### gm/ / characters/ / lore/

GMへのプロンプトとして読み込まれます。ファイル名は自由です。  
RAGの対象になるため、関連性の高い内容を個別ファイルに分けておくと精度が上がります。

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
