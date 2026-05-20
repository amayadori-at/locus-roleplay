---
type: gm_policy
id: luminous_goblin_crisis_image_policy
scenario: luminous_goblin_crisis
---

# Image Policy

## 目的

このファイルは、シナリオ「ルミナス王国ゴブリン大量発生」における画像マーカー運用方針を定義する。

GMは、ロールプレイ応答内で必要に応じて画像マーカーを挿入できる。  
画像マーカーは、主要NPCの立ち絵や表情差分を表示するために使用する。

画像は演出補助であり、文章描写の代替ではない。  
画像マーカーを使用する場合でも、状況、表情、態度、台詞は文章で十分に描写する。

---

## 前提

画像表示は `scenario.md` の frontmatter によって制御される。

```yaml
image_enabled: true
image_mode: inline
missing_image_behavior: fallback_normal
```

`image_enabled` が `true` の場合のみ、GM応答内の画像マーカーが画像表示対象となる。

画像マーカー形式は以下とする。

```text
[[image: {character_id}/{situation_id}.png]]
```

画像ファイルは以下のパスに配置される。

```text
rp/scenarios/luminous_goblin_crisis/assets/images/{character_id}/{situation_id}.png
```

---

## 使用可能な character_id

このシナリオで使用する主要キャラクターIDは以下である。

```text
aria_claudewell
tiariel_alwen
theora
```

原則として、この3名以外の画像マーカーは使用しない。  
ルミナス3世やその他NPCの画像を追加する場合は、該当画像ファイルとキャラクターIDが明示されてから使用する。

---

## situation_id 命名方針

`situation_id` は、英数字、underscore、hyphen のみで構成する。

推奨する situation_id は以下である。

```text
normal
serious
combat
angry
sad
smile
surprised
injured
thinking
```

必要に応じて追加してよいが、画像ファイルが存在することを前提にしない。  
画像が未作成の差分を使用する場合でも、`missing_image_behavior: fallback_normal` により `normal.png` へ fallback できる。

ただし、無秩序に situation_id を増やさない。

---

## 基本画像

各主要NPCには、最低限以下の画像が存在する想定とする。

```text
assets/images/aria_claudewell/normal.png
assets/images/tiariel_alwen/normal.png
assets/images/theora/normal.png
```

`normal.png` は、そのキャラクターの通常立ち絵として扱う。

状況差分が存在しない場合は、`normal.png` への fallback を前提にする。

---

## 画像マーカーの挿入位置

画像マーカーは、キャラクターの登場または焦点化に合わせて、自然な位置に挿入する。

推奨位置：

- キャラクターが初登場した直後
- 重要な台詞の直前
- 戦闘態勢に入る直前
- 感情が大きく変化した直後
- シーンの主役が切り替わった直後

### 例

```text
厳格そうな女騎士がこちらに気がつく。

[[image: aria_claudewell/normal.png]]

[アリア]: 「君が最後のメンバーである{{user}}だな？　定刻前の集合感謝する」
```

---

## 使用すべき場面

画像マーカーは、以下のような場面で使用する。

### 初登場

主要NPCが初めて登場する場面では、原則として `normal.png` を使用する。

```text
[[image: aria_claudewell/normal.png]]
[[image: tiariel_alwen/normal.png]]
[[image: theora/normal.png]]
```

ただし、3名が同時に登場する場面で画像が多くなりすぎる場合は、会話順に一人ずつ挿入してよい。

### 重要会話

NPCが重要な判断、告白、警告、価値観の表明を行う場合、画像を使用してよい。

例：

```text
[[image: aria_claudewell/serious.png]]
```

```text
[[image: tiariel_alwen/thinking.png]]
```

```text
[[image: theora/serious.png]]
```

### 戦闘前・戦闘中

NPCが戦闘態勢に入る、前衛に出る、弓を構える、魔術を詠唱するなどの場合、戦闘用画像を使用してよい。

例：

```text
[[image: aria_claudewell/combat.png]]
```

```text
[[image: tiariel_alwen/combat.png]]
```

```text
[[image: theora/combat.png]]
```

### 感情変化

NPCの感情がはっきり変化した場合、適切な画像を使用してよい。

例：

```text
[[image: aria_claudewell/angry.png]]
[[image: tiariel_alwen/sad.png]]
[[image: theora/surprised.png]]
```

---

## 使用を控える場面

以下の場面では、画像マーカーの使用を控える。

- 毎回の応答。
- 同じキャラクターの同じ画像を短時間で連続使用する場面。
- 単なる相槌。
- 軽い移動描写。
- 背景説明だけの場面。
- ユーザーの行動処理が主で、NPCが焦点ではない場面。
- 緊迫した戦闘中で画像がテンポを阻害する場面。
- 複数NPCが短く会話するだけの場面。

画像は演出補助として使い、応答を過剰に分断しない。

---

## キャラクター別画像方針

### アリア・フォン・クロードウェル

使用する character_id：

```text
aria_claudewell
```

推奨 situation_id：

```text
normal
serious
combat
angry
injured
thinking
```

使用場面：

- 初登場
- 任務説明
- 不正や規律違反を制止する場面
- 戦闘で前衛に立つ場面
- 王国への報告を判断する場面
- ルミナス3世の参戦に葛藤する場面
- ユーザーを騎士として評価する場面

例：

```text
[[image: aria_claudewell/serious.png]]
```

アリアは、厳格さ、責任感、騎士としての威厳が出る場面で画像を使う。

---

### ティアリエル・ソル・ネア・アルウェン

使用する character_id：

```text
tiariel_alwen
```

推奨 situation_id：

```text
normal
smile
serious
combat
sad
thinking
```

使用場面：

- 初登場
- 洗礼名を名乗る場面
- 森や足跡を観察する場面
- ゴブリンの分布異常に気づく場面
- 命や自然について静かに語る場面
- 弓を構える場面
- 洗礼名を侮辱され、静かに距離を置く場面

例：

```text
[[image: tiariel_alwen/thinking.png]]
```

ティアリエルは、穏やかさ、観察力、静かな怒り、弓術士としての集中が出る場面で画像を使う。

---

### テオラ

使用する character_id：

```text
theora
```

推奨 situation_id：

```text
normal
smile
serious
combat
angry
surprised
thinking
```

使用場面：

- 初登場
- 皮肉交じりに名乗る場面
- 魔術を詠唱する場面
- 魔素異常に気づく場面
- 自分の平民出身や姓のなさに触れる場面
- 魔素溜まりを単独処理できないと認める場面
- ユーザーから対等に扱われて照れ隠しする場面

例：

```text
[[image: theora/serious.png]]
```

テオラは、皮肉、魔術師としての集中、照れ隠し、魔素異常への警戒が出る場面で画像を使う。

---

## missing_image_behavior

このシナリオでは、画像欠落時の挙動は以下とする。

```yaml
missing_image_behavior: fallback_normal
```

これは、指定画像が存在しない場合に、同じキャラクターの `normal.png` を代替表示する挙動である。

例：

```text
[[image: theora/serious.png]]
```

上記が存在しない場合、以下へ fallback する。

```text
assets/images/theora/normal.png
```

ただし、`normal.png` も存在しない場合は画像を表示しない。

---

## 禁止事項

GMは画像マーカーについて、以下をしてはならない。

- 存在しない character_id を乱用する。
- 日本語IDを使う。
- 空白を含む path を使う。
- `../` を含む path を使う。
- `/absolute/path.png` のような絶対パスを使う。
- `.jpg`、`.jpeg`、`.webp` など `.png` 以外を指定する。
- 画像マーカーだけで状況説明を済ませる。
- 毎応答で無意味に画像を挿入する。
- 同じ画像を短時間に何度も繰り返す。
- ユーザーが画像表示を望まない場合に多用する。
- 未定義キャラクターの画像を勝手に仮定する。

---

## 有効な画像マーカー例

```text
[[image: aria_claudewell/normal.png]]
[[image: aria_claudewell/serious.png]]
[[image: aria_claudewell/combat.png]]
[[image: tiariel_alwen/normal.png]]
[[image: tiariel_alwen/thinking.png]]
[[image: tiariel_alwen/combat.png]]
[[image: theora/normal.png]]
[[image: theora/serious.png]]
[[image: theora/combat.png]]
```

---

## 無効な画像マーカー例

```text
[[image: アリア/normal.png]]
[[image: aria claudewell/normal.png]]
[[image: ../secret.png]]
[[image: aria_claudewell/../../secret.png]]
[[image: /absolute/path.png]]
[[image: aria_claudewell/normal.jpg]]
[[image: tiariel_alwen]]
[[image: theora/normal]]
```

---

## 応答内での扱い

画像マーカーは、独立した行として挿入する。

推奨：

```text
[[image: theora/serious.png]]

[テオラ]: 「待って。ここ、魔力の流れが変」
```

非推奨：

```text
[テオラ]: 「待って」[[image: theora/serious.png]]
```

画像マーカーの前後には空行を置いてよい。  
ただし、応答全体が画像マーカーだらけにならないようにする。

---

## 初期導入での推奨使用

開始メッセージで三名が順番に登場する場合、以下のように画像を挿入することを推奨する。

```text
厳格そうな女騎士がこちらに気がつく。

[[image: aria_claudewell/normal.png]]

[アリア]: 「君が最後のメンバーである{{user}}だな？　定刻前の集合感謝する。私がこのパーティを監督する王国騎士、アリア・フォン・クロードウェルだ」
```

```text
弓を背負い柔和な笑みを浮かべる女エルフが続けて口を開いた。

[[image: tiariel_alwen/normal.png]]

[ティアリエル]: 「ティアリエル・アルウェンです。ソルとネアを洗礼名として戴いています。ティアリエルとお呼びください。」
```

```text
とんがり帽子を被ったいかにもな女魔術師が続ける。

[[image: theora/normal.png]]

[テオラ]: 「テオラよ。生憎と平民の出だから、礼儀には期待しないで」
```

ただし、開始メッセージ側に画像マーカーを含めない方針の場合、GM応答側で初回の焦点化時に画像を出してもよい。

---

## 最終方針

画像は、ロールプレイの没入感を高める補助要素である。

画像を出すこと自体を目的にせず、以下を満たす場合のみ使用する。

- そのキャラクターが場面の中心にいる。
- 表情、態度、戦闘姿勢、感情変化が重要である。
- 画像を出すことで場面の理解や印象が強まる。
- 応答のテンポを損なわない。

画像がなくても、シーンが成立するように文章描写を維持する。