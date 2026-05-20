---
type: gm_policy
id: luminous_goblin_crisis_state_update_policy
scenario: luminous_goblin_crisis
---

# State Update Policy

## 目的

このファイルは、シナリオ「ルミナス王国ゴブリン大量発生」における State 更新方針を定義する。

State は、各セッションにおいて「今、何が真であるか」を表す現在値である。  
過去の出来事や、関係変化の理由、伏線、発見の履歴は Memory で扱い、State とは混同しない。

State updater は、Current State、ユーザーメッセージ、GM応答を読み、セッション中に変化した現在値だけを patch JSON として出力する。

State updater は、必ず有効な JSON のみを返す。  
説明文、Markdown、コードブロック、コメント、補足文を出力してはならない。

---

## 出力形式

State updater は、以下の形式で出力する。

```json
{
  "patch": {}
}
```

変更がある場合：

```json
{
  "patch": {
    "characters": {
      "aria_claudewell": {
        "mood": "警戒"
      }
    },
    "flags": {
      "first_meeting_completed": true
    }
  }
}
```

変更がない場合：

```json
{
  "patch": {}
}
```

`patch` は必須であり、object でなければならない。

`notes` と `warnings` は任意だが、原則として使用しない。  
使用する場合でも、正本ではない補助情報として扱う。

---

## 更新対象の基本構造

このシナリオでは、以下のトップレベルキーを想定する。

```json
{
  "time": "",
  "current_location": "",
  "scene": {},
  "characters": {},
  "relationships": {},
  "inventory": {},
  "flags": {},
  "quests": {},
  "world": {}
}
```

この構造に存在しないキーでも、必要があれば追加してよい。  
ただし、既存構造と意味が重複するキーをむやみに作らない。

---

## Merge Semantics 前提

patch は deep merge される。

- object は再帰的に merge される。
- scalar は置換される。
- array は全体置換される。
- delete semantics は使用しない。
- 削除目的で `null` を使わない。
- 既存値を保持したい場合は、patch に含めない。

配列を更新する場合は、必ず更新後の完全な配列を出力する。

---

## 更新してよいもの

State updater は、明確に変化した現在値のみを更新する。

更新対象例：

- 現在地
- 時刻
- 天候、明るさ、危険度などのシーン状態
- キャラクターのHP、MP、負傷、気分、現在地
- 関係値
- 所持品
- クエスト進行状況
- ゴブリン討伐数
- ゴブリン巣の発見・駆除状況
- 上位個体の発見・討伐状況
- 魔素異常の発見状況
- 北西部への疑いの進行
- 王国への報告状況
- ルミナス3世の参戦・生存状況
- 魔素溜まりの発見・処理状況
- エンディング条件に関わる内部フラグ

---

## 更新してはならないもの

以下は State に保存しない。

- 長文の過去出来事
- 信頼が変化した理由の詳細な物語記録
- セッション要約
- 未解決の伏線メモ
- 発見済み情報の長文説明
- NPCが覚えておくべきユーザーの行動履歴
- lore や character の恒常設定
- システムプロンプトやGMポリシーの内容
- 画像ファイル情報の詳細
- RAG検索結果
- Memoryファイル本文

これらは必要に応じて Memory で扱う。

---

## 捏造禁止

State updater は、ユーザーメッセージとGM応答から明確に読み取れる変化だけを反映する。

以下をしてはならない。

- 明示されていない負傷を追加する。
- 明示されていないアイテムを追加する。
- 戦闘結果が未確定なのに勝利済みにする。
- NPCの信頼値を大きく変化させる理由がないのに上げ下げする。
- ゴブリンロードや魔素溜まりの発見を、描写されていないのに true にする。
- ルミナス3世の参戦や死亡を、描写されていないのに設定する。
- ユーザーの内心、感情、意図を State に保存する。
- ユーザーの未宣言行動を実行済みにする。

不明な場合は更新しない。

---

## 推奨 State 初期構造

このシナリオの初期 state は、概ね以下を想定する。

```json
{
  "time": "第1章 初日 朝",
  "current_location": "王都ルミナス 指定広場",
  "scene": {
    "phase": "party_meeting",
    "weather": "clear",
    "danger_level": 0
  },
  "characters": {
    "user": {
      "hp": null,
      "mp": null,
      "mood": null,
      "injury": "none",
      "location": "王都ルミナス 指定広場",
      "status": "active"
    },
    "aria_claudewell": {
      "hp": 30,
      "mp": null,
      "mood": "厳格",
      "injury": "none",
      "location": "王都ルミナス 指定広場",
      "status": "active"
    },
    "tiariel_alwen": {
      "hp": 22,
      "mp": null,
      "mood": "穏やか",
      "injury": "none",
      "location": "王都ルミナス 指定広場",
      "status": "active"
    },
    "theora": {
      "hp": 18,
      "mp": 30,
      "mood": "気怠げ",
      "injury": "none",
      "location": "王都ルミナス 指定広場",
      "status": "active"
    }
  },
  "relationships": {
    "aria_claudewell:user": {
      "trust": 20,
      "suspicion": 45,
      "note": "初対面。監督対象として警戒している。"
    },
    "tiariel_alwen:user": {
      "trust": 35,
      "suspicion": 15,
      "note": "初対面。柔らかく接しつつ観察している。"
    },
    "theora:user": {
      "trust": 25,
      "suspicion": 25,
      "note": "初対面。軽口を交えながら実力を見ようとしている。"
    }
  },
  "inventory": {
    "user": [],
    "aria_claudewell": ["長剣", "盾", "王国騎士の記録具"],
    "tiariel_alwen": ["弓", "矢筒", "旅装備"],
    "theora": ["魔術杖", "魔導書", "触媒袋"]
  },
  "flags": {
    "first_meeting_completed": false,
    "quest_accepted": true,
    "aria_supervising_party": true,
    "tiariel_baptismal_names_explained": false,
    "theora_commoner_status_revealed": false,
    "goblin_abnormality_suspected": false,
    "mana_anomaly_detected": false,
    "northwest_pattern_suspected": false,
    "northwest_cave_identified": false,
    "goblin_lord_identified": false,
    "goblin_lord_defeated": false,
    "mana_pool_identified": false,
    "mana_pool_resolved": false,
    "king_luminous_iii_involved": false,
    "king_luminous_iii_alive": true
  },
  "quests": {
    "goblin_crisis": {
      "status": "in_progress",
      "phase": "introduction",
      "goblins_defeated": 0,
      "nests_discovered": 0,
      "nests_cleared": 0,
      "lord_spawn_defeated": 0,
      "shamans_defeated": 0,
      "steps_completed": [],
      "steps_pending": [
        "party_introduction",
        "first_assignment",
        "investigate_goblin_activity"
      ]
    }
  },
  "world": {
    "trade_routes_secure": false,
    "village_damage_level": 2,
    "kingdom_alert_level": 2,
    "gardian_empire_involved": false
  }
}
```

これは推奨構造であり、実際の `state/current.json` の内容に従って patch を出力する。  
存在しないフィールドを無理に補完しない。

---

## キャラクターID

このシナリオで使用する主要キャラクターIDは以下である。

```text
user
aria_claudewell
tiariel_alwen
theora
```

必要に応じて、以下を追加してよい。

```text
king_luminous_iii
guild_receptionist
village_chief
merchant
royal_knight
goblin
goblin_shaman
goblin_lord
```

ただし、一時的なモブキャラクターは必要がない限り State に追加しない。

---

## 関係値更新方針

関係値は、ユーザーの行動がNPCの態度に明確な影響を与えた場合にのみ更新する。

### 推奨範囲

関係値は 0〜100 の数値を想定する。

- 0：敵対的
- 20：警戒
- 40：中立寄り
- 60：信頼傾向
- 80：強い信頼
- 100：絶対的信頼に近い

### アリアの関係値

アリアは、以下で信頼を上げやすい。

- 民間人を守る。
- 不正を拒否する。
- 任務に誠実に取り組む。
- 報告や共有を怠らない。
- 規律を守る。
- 仲間を危険に晒さない。
- 失敗を認めて改善する。

アリアは、以下で信頼を下げやすい。

- 略奪する。
- 虚偽報告をする。
- 民間人を軽視する。
- 任務を放棄する。
- 無断で危険行動を取る。
- 仲間を危険に晒す。
- 王国騎士の監督を故意に妨害する。

### ティアリエルの関係値

ティアリエルは、以下で信頼を上げやすい。

- 命を軽んじない。
- 森や自然に配慮する。
- 弱者を守る。
- 不必要な殺戮を避ける。
- 観察や慎重な判断を尊重する。
- エルフの洗礼名を尊重する。

ティアリエルは、以下で信頼を下げやすい。

- 命を弄ぶ。
- 森を無意味に焼く。
- 洗礼名を侮辱する。
- 弱者を見捨てる。
- 報酬のためだけに民を犠牲にする。
- 無警戒な大声や軽率な行動で危険を招く。

洗礼名への侮辱は、非常に大きな関係悪化として扱う。  
一度大きく悪化した場合、短期間で回復させない。

### テオラの関係値

テオラは、以下で信頼を上げやすい。

- 平民や姓のなさを見下さない。
- 魔術師として対等に扱う。
- テオラの魔術を正当に評価する。
- 詠唱や射線を考慮する。
- 実利や報酬への関心を頭ごなしに否定しない。
- 危険時にテオラを見捨てない。

テオラは、以下で信頼を下げやすい。

- 平民出身を馬鹿にする。
- 姓がないことを侮辱する。
- 魔術師を便利な道具扱いする。
- 無茶な魔術行使を強要する。
- テオラにできないことを無責任に押しつける。
- 実力を血筋や身分だけで否定する。

---

## 関係値更新量の目安

通常の小さな好印象または悪印象：

```json
{
  "trust_delta": 1,
  "suspicion_delta": -1
}
```

明確な好印象または悪印象：

```json
{
  "trust_delta": 3,
  "suspicion_delta": -2
}
```

重要な信頼獲得または重大な失望：

```json
{
  "trust_delta": 5,
  "suspicion_delta": -5
}
```

致命的な侮辱、裏切り、重大な不正：

```json
{
  "trust_delta": -10,
  "suspicion_delta": 10
}
```

実際の patch では delta ではなく、更新後の値を出力する。  
既存値が不明な場合は、無理に計算せず更新しない。

---

## mood 更新方針

`characters.*.mood` は現在の感情・態度を短い語で表す。

例：

```text
警戒
穏やか
気怠げ
緊張
負傷
動揺
怒り
安堵
集中
疲労
不信
決意
```

mood は、GM応答で明確な態度変化が描写された場合に更新する。  
一時的すぎる表情変化は、State に保存しなくてよい。

---

## injury / status 更新方針

負傷や状態異常は明確に描写された場合のみ更新する。

### injury の例

```text
none
軽傷
中傷
重傷
気絶
毒
疲労
魔力消耗
```

### status の例

```text
active
resting
unconscious
missing
captured
dead
```

主要NPCを `dead` にする場合は、GM応答に明確な死亡描写が必要である。  
曖昧な危険描写だけで死亡扱いにしない。

---

## inventory 更新方針

所持品の追加・消費・喪失が明確に描写された場合のみ更新する。

配列は全体置換であるため、inventory を更新する場合は更新後の完全な配列を出す。

例：

Current:

```json
{
  "inventory": {
    "user": ["短剣"]
  }
}
```

ユーザーがランタンを受け取った場合：

```json
{
  "patch": {
    "inventory": {
      "user": ["短剣", "小型ランタン"]
    }
  }
}
```

所持品の存在が曖昧な場合は更新しない。

---

## クエスト進行更新方針

`quests.goblin_crisis` は、このシナリオの主要クエスト進行を表す。

### status の例

```text
not_started
in_progress
completed
failed
```

### phase の例

```text
introduction
first_assignment
field_investigation
goblin_nest_hunt
abnormality_discovery
northwest_pattern
northwest_cave_investigation
final_preparation
goblin_lord_battle
aftermath
ended
```

phase は、明確に進行段階が移った場合のみ更新する。

---

## ゴブリン討伐関連の更新

以下が明確に発生した場合、数値またはフラグを更新する。

- ゴブリンを倒した。
- ゴブリンの巣を発見した。
- ゴブリンの巣を駆除した。
- ゴブリンシャーマンを発見した。
- ゴブリンシャーマンを倒した。
- ゴブリンロードの子または上位個体を倒した。
- 巣に魔素異常があることを発見した。
- 被害分布が北西部から広がっていると分かった。
- 北西部の海沿いの洞窟が疑わしいと分かった。
- ゴブリンロードを確認した。
- ゴブリンロードを討伐した。

### 例

```json
{
  "patch": {
    "quests": {
      "goblin_crisis": {
        "goblins_defeated": 8,
        "nests_discovered": 1,
        "nests_cleared": 1,
        "phase": "goblin_nest_hunt",
        "steps_completed": ["party_introduction", "first_assignment", "cleared_first_nest"],
        "steps_pending": ["investigate_abnormal_goblins"]
      }
    },
    "flags": {
      "first_nest_cleared": true
    }
  }
}
```

配列を更新する場合は、更新後の完全な配列を出す。

---

## 真相関連フラグ

以下のフラグは、証拠が明確に描写された場合のみ true にする。

```json
{
  "flags": {
    "goblin_abnormality_suspected": false,
    "mana_anomaly_detected": false,
    "northwest_pattern_suspected": false,
    "northwest_cave_identified": false,
    "goblin_lord_identified": false,
    "goblin_lord_defeated": false,
    "mana_pool_identified": false,
    "mana_pool_resolved": false
  }
}
```

### 更新条件

`goblin_abnormality_suspected`

- ゴブリンの動きが通常より統率されている。
- 上位個体やゴブリンシャーマンが確認された。
- 通常の繁殖だけでは説明しにくい状況が描写された。

`mana_anomaly_detected`

- テオラが魔素異常を明確に察知した。
- 巣や上位個体に魔力の異常があると描写された。

`northwest_pattern_suspected`

- ティアリエルまたは調査により、被害や巣の分布が北西部から波及していると示された。

`northwest_cave_identified`

- 北西部の海沿いの洞窟が疑わしい地点として明確に特定された。

`goblin_lord_identified`

- ゴブリンロードの存在が明確に確認された。

`goblin_lord_defeated`

- ゴブリンロードが明確に討伐された。

`mana_pool_identified`

- 洞窟などで魔素溜まりが明確に確認された。

`mana_pool_resolved`

- 王国と魔術師ギルドなどの専門対応により、魔素溜まりが処理された。

---

## ルミナス3世関連フラグ

以下のフラグを使用する。

```json
{
  "flags": {
    "king_luminous_iii_involved": false,
    "king_luminous_iii_joined_battle": false,
    "king_luminous_iii_alive": true,
    "king_luminous_iii_injured": false
  }
}
```

### 更新条件

`king_luminous_iii_involved`

- 王国への報告、謁見、命令、援軍要請などでルミナス3世が事件に関与した場合。

`king_luminous_iii_joined_battle`

- ルミナス3世が実際に戦場、洞窟、または討伐作戦に同行・参戦した場合。

`king_luminous_iii_alive`

- 初期値は true。
- 明確な死亡描写がない限り false にしない。

`king_luminous_iii_injured`

- ルミナス3世が負傷したと明確に描写された場合のみ true にする。

---

## world 更新方針

`world` は可変の世界状態を表す。

このシナリオでは以下を想定する。

```json
{
  "world": {
    "trade_routes_secure": false,
    "village_damage_level": 2,
    "kingdom_alert_level": 2,
    "gardian_empire_involved": false
  }
}
```

### `trade_routes_secure`

交易路の安全が回復した場合に true にする。  
一部だけ安全になった場合は、別フィールドまたは `quests` 側で表現する。

### `village_damage_level`

村落被害の深刻度を 0〜5 程度で扱う。

- 0：被害なし
- 1：軽微な被害
- 2：複数村で被害
- 3：深刻な略奪や負傷者多数
- 4：村の壊滅・放棄が発生
- 5：広域崩壊

GM応答で被害拡大または抑制が明確に描写された場合のみ更新する。

### `kingdom_alert_level`

王国の警戒度を 0〜5 程度で扱う。

- 0：平常
- 1：軽微な警戒
- 2：地方被害対応
- 3：国家的警戒
- 4：王国軍・騎士団の本格投入
- 5：国家非常事態

### `gardian_empire_involved`

このシナリオでは、ガルディアン帝国は黒幕ではない。  
原則として false のままにする。

ユーザーやNPCが疑っただけでは true にしない。  
実際に関与していないため、GM応答でも true にするべきではない。

---

## steps_completed / steps_pending 更新方針

`steps_completed` と `steps_pending` は配列である。

更新する場合は、必ず更新後の完全な配列を出す。

### 例

Current:

```json
{
  "quests": {
    "goblin_crisis": {
      "steps_completed": ["party_introduction"],
      "steps_pending": ["first_assignment", "investigate_goblin_activity"]
    }
  }
}
```

Patch:

```json
{
  "patch": {
    "quests": {
      "goblin_crisis": {
        "steps_completed": ["party_introduction", "first_assignment"],
        "steps_pending": ["investigate_goblin_activity", "clear_first_nest"]
      }
    }
  }
}
```

小さな進行ごとに必ず更新する必要はない。  
物語上の節目で更新する。

---

## 例：初期挨拶完了

ユーザーが自己紹介し、三人との初期挨拶が完了した場合：

```json
{
  "patch": {
    "scene": {
      "phase": "party_briefing"
    },
    "flags": {
      "first_meeting_completed": true,
      "tiariel_baptismal_names_explained": true,
      "theora_commoner_status_revealed": true
    },
    "quests": {
      "goblin_crisis": {
        "phase": "introduction",
        "steps_completed": ["party_introduction"],
        "steps_pending": ["receive_first_assignment", "investigate_goblin_activity"]
      }
    }
  }
}
```

---

## 例：テオラが魔素異常に気づく

GM応答で、テオラがゴブリンシャーマンの死体や巣の魔力異常に気づいた場合：

```json
{
  "patch": {
    "flags": {
      "goblin_abnormality_suspected": true,
      "mana_anomaly_detected": true
    },
    "characters": {
      "theora": {
        "mood": "警戒"
      }
    },
    "quests": {
      "goblin_crisis": {
        "phase": "abnormality_discovery"
      }
    }
  }
}
```

---

## 例：ティアリエルが北西部への偏りに気づく

GM応答で、ティアリエルが巣の分布や足跡から北西部を疑った場合：

```json
{
  "patch": {
    "flags": {
      "northwest_pattern_suspected": true
    },
    "characters": {
      "tiariel_alwen": {
        "mood": "集中"
      }
    },
    "quests": {
      "goblin_crisis": {
        "phase": "northwest_pattern"
      }
    }
  }
}
```

---

## 例：王国への報告

GM応答で、アリアが王国へ正式報告した、または報告のため王都や騎士詰所へ向かった場合：

```json
{
  "patch": {
    "flags": {
      "reported_abnormal_goblins_to_kingdom": true
    },
    "characters": {
      "aria_claudewell": {
        "mood": "緊張"
      }
    },
    "quests": {
      "goblin_crisis": {
        "steps_completed": [
          "party_introduction",
          "first_assignment",
          "reported_abnormal_goblins"
        ]
      }
    }
  }
}
```

---

## 例：ルミナス3世が参戦を望む

GM応答で、ルミナス3世が事件に関与し、現場参戦を望んだ場合：

```json
{
  "patch": {
    "flags": {
      "king_luminous_iii_involved": true
    },
    "characters": {
      "aria_claudewell": {
        "mood": "葛藤"
      },
      "theora": {
        "mood": "困惑"
      }
    }
  }
}
```

実際に戦場へ同行した場合のみ、`king_luminous_iii_joined_battle` を true にする。

---

## 例：ゴブリンロード討伐

GM応答で、ゴブリンロードが明確に討伐された場合：

```json
{
  "patch": {
    "flags": {
      "goblin_lord_identified": true,
      "goblin_lord_defeated": true
    },
    "quests": {
      "goblin_crisis": {
        "phase": "aftermath"
      }
    }
  }
}
```

魔素溜まりが残っている場合、`mana_pool_resolved` は true にしない。

---

## 例：魔素溜まり処理完了

GM応答で、王国と魔術師ギルドの正式対応により魔素溜まりが処理された場合：

```json
{
  "patch": {
    "flags": {
      "mana_pool_identified": true,
      "mana_pool_resolved": true
    },
    "quests": {
      "goblin_crisis": {
        "status": "completed",
        "phase": "ended"
      },
      "mana_pool_resolution": {
        "status": "completed"
      }
    },
    "world": {
      "trade_routes_secure": true,
      "kingdom_alert_level": 1
    }
  }
}
```

---

## 例：変更なし

ユーザーが軽い雑談をしただけで、現在値に変化がない場合：

```json
{
  "patch": {}
}
```

---

## 出力時の最終確認

State updater は出力前に以下を確認する。

- JSONとして有効か。
- rootに `patch` があるか。
- `patch` はobjectか。
- 変更が明確なものだけを含めているか。
- 既存値を無意味に再出力していないか。
- 配列を更新する場合、完全な配列になっているか。
- 未発見の真相を state に反映していないか。
- Memoryに保存すべき長文履歴を State に入れていないか。
- ガルディアン帝国関与を誤って true にしていないか。
- ルミナス3世の死亡や負傷を、曖昧な描写だけで設定していないか。