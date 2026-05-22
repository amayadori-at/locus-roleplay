# Locus RP Frontend

Svelte 5 + Vite によるフロントエンド実装です。

---

## 開発用起動

Python バックエンドを別ターミナルで起動します。

```bash
python app/main.py --port 8787
```

フロントエンドを起動します。

```bash
npm install
npm run dev
```

Vite dev server は `/api` を `http://127.0.0.1:8787` にプロキシします。

バックエンドを別ポートで起動する場合は `LOCUS_BACKEND_URL` を指定します。

```bash
LOCUS_BACKEND_URL=http://127.0.0.1:9877 npm run dev
```

---

## ビルド・チェック・テスト

```bash
npm test          # vitest（ユニットテスト + コンポーネントテスト）
npm run check     # svelte-check（型チェック）
npm run build     # プロダクションビルド（frontend/dist/ に出力）
```

ビルド後は repo root で `python app/main.py` を起動すると `frontend/dist` が自動的に配信されます。

配信先を明示する場合:

```bash
python app/main.py --static-dir frontend/dist
```

---

## テスト構成

| ファイル | 内容 |
|---|---|
| `src/lib/stateTemplate.test.js` | `resolveStateValue` / `expandPlaceholders` / `sanitizeHtml` / `buildRenderedHtml` のユニットテスト |
| `src/lib/StatePanel.test.js` | `StatePanel.svelte` のコンポーネントテスト（Shadow DOM・フォールバック挙動） |

テスト環境: vitest + jsdom + @testing-library/svelte

---

## 方針

- アイコンは `lucide-svelte` を使います。
- CSS は軽量なプロジェクト CSS で進めます（Tailwind 等は必要性が明確になるまで導入しません）。
- 共通色・spacing・typography は `src/app.css`、コンポーネント固有スタイルは各 Svelte ファイルへ寄せます。
- フロントエンドは API キーや endpoint 値を扱いません。
