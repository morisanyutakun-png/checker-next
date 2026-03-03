# 設計判断・前提条件 (ASSUMPTIONS)

移行時に行った設計判断と、その理由をまとめています。

---

## 1. データベース設計

### JSONB の積極的使用

`questions` (問題リスト) や `result` (採点結果) は **JSONB カラム** で保存しています。

**理由:**
- 元の `config.json` の構造がネスト深く（問題ごとに `bubbles` 配列、各 bubble に `x,y,w,h,label`）、正規化すると 5 テーブル以上に分散して JOIN コストが高い
- 読み書きは常にまとまり単位（「科目の問題一覧」「採点結果全体」）で行われるため、行単位アクセスのメリットが少ない
- PostgreSQL の JSONB はインデックス・部分クエリに対応しており、将来の拡張にも耐えうる

### AppConfig + Subject テーブル分離

閾値やオフセットなどグローバル設定 (`AppConfig`) と、科目単位の設定 (`Subject`) を分離。

**理由:**
- グローバル設定は 1 行のみ（singleton パターン）
- 科目は動的に増減するため、リレーション分離が適切
- 元の JSON では `subjects` 配列内にフラットに格納されていたが、DB では科目ごとの CRUD が容易

---

## 2. OMR エンジン

### omr.py をそのまま移植

`omr.py`（約 1295 行）は **変更なし** で FastAPI 側にコピーしています。

**理由:**
- OpenCV ベースの画像処理ロジックはフレームワーク非依存
- fiducial 検出、ホモグラフィ変換、バブル解析のアルゴリズムは十分にテスト済み
- リファクタリングによるバグ混入リスクを回避

### omr_service.py ラッパー

`omr.py` を直接呼ばず、`omr_service.py` 経由で呼び出し。

**理由:**
- 将来的に非同期化（バックグラウンドタスク化）する際の差し替え口
- テスト時のモック差し替えが容易
- DB からの設定読み込みと omr.py の入力フォーマットを変換するアダプター層

---

## 3. LaTeX 関連

### xelatex をコンテナに内蔵

API の Dockerfile に `texlive-xetex`, `fonts-noto-cjk` を含めています（イメージサイズ +500MB 程度）。

**理由:**
- 日本語フォント (Noto Sans CJK) を使用するため xelatex が必要
- pdflatex では CJK 対応が複雑
- サーバーレス環境では LaTeX が使えないため、コンテナ化が最も確実

### テンプレートの維持

`sheet.tex`, `sheet.math_double.tex` は元のまま `templates/` に配置。

**理由:**
- LaTeX テンプレートは Python の文字列置換（`str.replace`）でレンダリングされる
- バブル座標付きの OMR マーク用 TikZ コードを Python から動的に生成
- テンプレート変更は採点精度に直結するため、安定版を維持

---

## 4. ファイルストレージ

### ローカルファイルシステム

生成された PDF は `storage/` ディレクトリにローカル保存。

**理由:**
- PDF ファイルは一時的（採点完了後は不要なケースが多い）
- S3 等のクラウドストレージは追加コスト・設定の複雑さが増す
- Docker volume による永続化で開発環境には十分
- 将来的にクラウドストレージに移行する場合は `latex_service.py` のファイル保存部分のみ変更すればよい

---

## 5. 認証・認可

### 認証なし

現時点では認証機構を実装していません。

**理由:**
- 元の Flask アプリにも認証がなかった
- 校内ネットワーク等の閉じた環境での使用を想定
- 必要に応じて FastAPI の `Depends()` で JWT / セッション認証を追加可能

---

## 6. 印刷機能

### CUPS 依存

サーバー側印刷は `lp` コマンド（CUPS）を使用。

**理由:**
- 元の Flask アプリと同じ方式
- Docker コンテナから CUPS サーバーに接続する構成
- ブラウザ印刷（`window.print()`）はフロントエンド側で別途対応済み

---

## 7. フロントエンド

### Next.js App Router (RSC は最小限)

ほぼすべてのページが `"use client"` ディレクティブを使用。

**理由:**
- フォーム操作、ファイルアップロード、動的 UI 更新が大半のため CSR が主体
- SSR のメリット（SEO, 初回描画速度）は管理ツールでは優先度が低い
- API への fetch は `useEffect` + `useState` パターンでシンプルに実装

### Tailwind CSS v4

`@import "tailwindcss"` 形式の v4 構文を使用。

**理由:**
- Next.js 15 との互換性
- CSS 変数ベースのカスタムテーマが容易
- `globals.css` に Apple-like デザインシステムのカスタムプロパティを定義

---

## 8. API 設計

### REST + JSON

GraphQL や tRPC は採用せず、シンプルな REST エンドポイント。

**理由:**
- 元の Flask ルートとの 1:1 対応が明確
- エンドポイント数が少ない（10 程度）
- FastAPI の OpenAPI 自動生成（Swagger UI）で十分

### `NEXT_PUBLIC_API_BASE_URL` を空文字

開発環境では Next.js の `rewrites` で `/api/*` を FastAPI に中継。

**理由:**
- CORS 問題を回避
- フロントエンドの fetch URL を `/api/...` で統一できる
- 本番では直接 API サーバーの URL を設定

---

## 9. 移行していない機能

| 機能 | 理由 |
|------|------|
| `debug_*` 系スクリプト | 開発用ユーティリティのため |
| `dev_*` 系スクリプト | テスト用コードのため |
| `scripts/set_omr_offsets.py` | CLI ツールとして別途移行可能 |
| `tools/run_omr_check.py` | CLI ツールとして別途移行可能 |

---

## 10. 将来の拡張ポイント

- **認証**: FastAPI + NextAuth.js で JWT ベース認証
- **バックグラウンドタスク**: Celery or `asyncio.create_task` で大量 PDF 処理を非同期化
- **クラウドストレージ**: S3 互換ストレージへの PDF 保存
- **WebSocket**: 採点進捗のリアルタイム通知
- **テスト**: pytest + httpx (API), Playwright (E2E)
