# Checker-Next

**OMR（マークシート）自動採点 Web アプリケーション**  
Next.js 15 (App Router) + FastAPI + PostgreSQL (Neon) によるモダンなフルスタック構成。

> **v2.0** – 2026-03

---

## 目次

- [アーキテクチャ](#アーキテクチャ)
- [技術スタック](#技術スタック)
- [ディレクトリ構成](#ディレクトリ構成)
- [ローカル開発](#ローカル開発)
- [本番デプロイ](#本番デプロイ)
  - [1. Neon (データベース)](#1-neon-データベース)
  - [2. Koyeb (バックエンド API)](#2-koyeb-バックエンド-api)
  - [3. Vercel (フロントエンド)](#3-vercel-フロントエンド)
- [OMR 採点フロー](#omr-採点フロー)
- [API リファレンス](#api-リファレンス)
- [環境変数一覧](#環境変数一覧)
- [トラブルシューティング](#トラブルシューティング)

---

## アーキテクチャ

```
┌─────────────────┐      ┌──────────────────┐      ┌───────────────────┐
│   Next.js 15    │─────▶│    FastAPI        │─────▶│   PostgreSQL      │
│   (Vercel)      │ REST │    (Koyeb)        │ SQL  │   (Neon)          │
│                 │      │                    │      │                   │
│  React 19       │      │  OpenCV + PyMuPDF │      │  asyncpg + SSL    │
│  Tailwind v4    │      │  xelatex (TeX)    │      │                   │
└─────────────────┘      └──────────────────┘      └───────────────────┘
```

### データフロー

1. **マークシート生成**: 管理画面で教科・問題を設定 → LaTeX → PDF 生成（バブル座標メタデータ付き）
2. **PDF アップロード**: スキャンした解答用紙 PDF をアップロード
3. **OMR 解析**: OpenCV でフィデューシャルマーク検出 → ホモグラフィ変換 → バブル塗りつぶし判定
4. **採点結果**: 正誤判定・スコア算出 → DB 保存 → CSV ダウンロード・注釈画像表示

---

## 技術スタック

| レイヤー | 技術 | ディレクトリ |
|---------|------|------------|
| フロントエンド | Next.js 15 (App Router), React 19, Tailwind CSS v4 | `apps/web/` |
| バックエンド API | FastAPI, SQLAlchemy 2.x (async), Pydantic v2 | `apps/api/` |
| データベース | PostgreSQL 16 (dev) / **Neon** (prod) | Docker `db` / Neon |
| OMR エンジン | OpenCV, PyMuPDF (fitz), Pillow, NumPy | `apps/api/app/omr.py` |
| LaTeX 生成 | xelatex (TeX Live), Noto CJK フォント | `apps/api/templates/` |
| ホスティング | **Vercel** (Web) / **Koyeb** (API) / **Neon** (DB) | - |
| 開発環境 | Docker Compose, nginx (任意) | `docker-compose.yml` |

---

## ディレクトリ構成

```
checker-next/
├── apps/
│   ├── api/                    # FastAPI バックエンド
│   │   ├── app/
│   │   │   ├── main.py             # エントリポイント + ヘルスチェック
│   │   │   ├── config.py           # Pydantic Settings (環境変数)
│   │   │   ├── db.py               # SQLAlchemy async エンジン (Neon SSL対応)
│   │   │   ├── models.py           # ORM: AppConfig, Subject, Score, GeneratedPdf
│   │   │   ├── schemas.py          # Pydantic スキーマ
│   │   │   ├── omr.py              # OMR エンジン (1200行, OpenCV)
│   │   │   ├── routers/
│   │   │   │   ├── config_router.py    # GET/PUT /api/config
│   │   │   │   ├── sheets.py          # PDF 生成・印刷
│   │   │   │   ├── upload.py          # PDF アップロード → 採点
│   │   │   │   ├── scores.py          # 採点結果・注釈画像
│   │   │   │   └── generated.py       # 生成済み PDF 取得
│   │   │   └── services/
│   │   │       ├── config_service.py   # DB ⇔ config 変換
│   │   │       ├── latex_service.py    # LaTeX テンプレート → PDF
│   │   │       └── omr_service.py      # OMR ラッパー
│   │   ├── alembic/                # DB マイグレーション
│   │   ├── templates/              # LaTeX テンプレート
│   │   ├── storage/                # 生成 PDF / スコア保存
│   │   ├── Dockerfile              # マルチステージ (dev / prod)
│   │   └── requirements.txt
│   └── web/                    # Next.js フロントエンド
│       ├── src/
│       │   ├── app/
│       │   │   ├── page.tsx            # ホーム (アップロード & 採点)
│       │   │   ├── layout.tsx          # Apple 風グローバルレイアウト
│       │   │   ├── globals.css         # Apple デザインシステム CSS
│       │   │   ├── admin/page.tsx      # 設定管理
│       │   │   ├── sheet/[idx]/page.tsx # シート PDF プレビュー
│       │   │   ├── scores/page.tsx     # 採点履歴一覧
│       │   │   └── scores/[id]/page.tsx # 採点結果詳細
│       │   └── lib/api.ts         # API クライアント (fetch ラッパー)
│       ├── vercel.json             # Vercel デプロイ設定
│       ├── Dockerfile              # マルチステージ (dev / prod)
│       └── package.json
├── infra/
│   └── nginx.conf              # リバースプロキシ (任意)
├── docker-compose.yml
├── .env.example                # 環境変数テンプレート
└── README.md
```

---

## ローカル開発

### 前提条件

- Docker & Docker Compose v2
- (任意) Node.js 22+, Python 3.12+

### クイックスタート

```bash
# 1. クローン
git clone <repo-url> checker-next
cd checker-next

# 2. 環境変数を設定
cp .env.example .env

# 3. 全サービスを起動
docker compose up --build
```

### 起動後のアクセス先

| サービス | URL |
|---------|-----|
| フロントエンド (Next.js) | http://localhost:3000 |
| バックエンド API (FastAPI) | http://localhost:8000 |
| Swagger UI (API ドキュメント) | http://localhost:8000/docs |
| ヘルスチェック | http://localhost:8000/api/health |
| PostgreSQL | `localhost:5432` |

### オプション: nginx リバースプロキシ

```bash
docker compose --profile with-nginx up --build
# → http://localhost:8080 で統合アクセス（/api/* → FastAPI, /* → Next.js）
```

### オプション: pgAdmin

```bash
docker compose --profile tools up --build
# → http://localhost:5050 (admin@local.dev / admin)
```

### Docker を使わない場合

```bash
# ターミナル 1: API サーバー
cd apps/api
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# ターミナル 2: Web フロントエンド
cd apps/web
npm install
npm run dev
```

> **注意**: Docker 不使用の場合、LaTeX (xelatex) と PostgreSQL を別途インストールする必要があります。

---

## 本番デプロイ

### 全体像

```
    ユーザー
       │
       ▼
┌─────────────┐   rewrite(/api/*)   ┌──────────────┐   asyncpg+SSL   ┌──────────┐
│   Vercel    │ ─────────────────▶  │    Koyeb     │ ─────────────▶  │   Neon   │
│   (Web)     │                     │    (API)     │                  │   (DB)   │
│   Next.js   │                     │   FastAPI    │                  │ Postgres │
└─────────────┘                     └──────────────┘                  └──────────┘
```

---

### 1. Neon (データベース)

1. [Neon Console](https://console.neon.tech) にサインアップしてプロジェクトを作成
2. 接続文字列をコピー:
   ```
   postgresql://user:password@ep-xxx-yyy.us-east-2.aws.neon.tech/checker?sslmode=require
   ```
3. **SQLAlchemy 用にプレフィックスを変換**:
   ```bash
   # async 用
   DATABASE_URL=postgresql+asyncpg://user:password@ep-xxx-yyy.us-east-2.aws.neon.tech/checker?sslmode=require

   # sync 用 (Alembic)
   DATABASE_URL_SYNC=postgresql+psycopg2://user:password@ep-xxx-yyy.us-east-2.aws.neon.tech/checker?sslmode=require
   ```

> Neon の SSL は `db.py` で自動検出されます。接続文字列に `neon.tech` が含まれていれば SSL コンテキストが自動設定されます。

---

### 2. Koyeb (バックエンド API)

#### 方法 A: GitHub 連携 (推奨)

1. [Koyeb Console](https://app.koyeb.com) で新規サービスを作成
2. GitHub リポジトリを接続
3. 以下を設定:
   - **Builder**: Dockerfile
   - **Dockerfile path**: `apps/api/Dockerfile`
   - **Build target**: `prod`
   - **Port**: `8000`
4. 環境変数を設定:

   | 変数名 | 値 |
   |--------|-----|
   | `DATABASE_URL` | `postgresql+asyncpg://...@ep-xxx.neon.tech/checker?sslmode=require` |
   | `DATABASE_URL_SYNC` | `postgresql+psycopg2://...@ep-xxx.neon.tech/checker?sslmode=require` |
   | `CORS_ORIGINS` | `https://your-app.vercel.app` |
   | `SECRET_KEY` | `<ランダムな32文字>` |
   | `STORAGE_DIR` | `/app/storage` |
   | `PORT` | `8000` |
   | `DEBUG` | `false` |

5. デプロイ → `https://your-api-xxx.koyeb.app` が発行される

#### 方法 B: Docker イメージ

```bash
cd apps/api
docker build --target prod -t checker-api:prod .
# Koyeb の Docker レジストリにプッシュ
```

#### ヘルスチェック確認

```bash
curl https://your-api-xxx.koyeb.app/api/health
# → {"status": "ok", "version": "2.0.0"}
```

---

### 3. Vercel (フロントエンド)

#### 方法 A: Vercel CLI

```bash
cd apps/web
npx vercel --prod
```

#### 方法 B: Vercel Dashboard (推奨)

1. [Vercel](https://vercel.com) に GitHub リポジトリをインポート
2. 設定:
   - **Root Directory**: `apps/web`
   - **Framework**: Next.js
   - **Build Command**: `npm run build`
   - **Output Directory**: `.next`
3. 環境変数を設定:

   | 変数名 | 値 |
   |--------|-----|
   | `API_BASE_URL` | `https://your-api-xxx.koyeb.app` |
   | `NEXT_PUBLIC_API_BASE_URL` | _(空のまま)_ |

4. デプロイ

> **重要**: `NEXT_PUBLIC_API_BASE_URL` は空のままにしてください。フロントエンドの `/api/*` リクエストは Next.js の `rewrites` 設定により Vercel 側でサーバーサイドプロキシされ、CORS 問題を回避します。

#### デプロイ確認

```bash
# フロントエンド
open https://your-app.vercel.app

# API が Vercel 経由でプロキシされていることを確認
curl https://your-app.vercel.app/api/health
# → {"status": "ok", "version": "2.0.0"}
```

---

## OMR 採点フロー

### フロー概要

```
マークシート PDF
       │
       ▼
┌─────────────────────┐
│  PyMuPDF: PDF → 画像  │  300 DPI, landscape 統一
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│  フィデューシャル検出   │  4隅のマーカー (●□▲○)
│  (Contour検出 + OTSU)│  OpenCV findContours
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│  ホモグラフィ変換      │  4点 → findHomography
│  (または Affine)      │  3点 → getAffineTransform
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│  バブル座標 → パッチ抽出│  mm → px 変換
│  (透視変換 warpPerspective)│  18%マージン除去
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│  塗りつぶし判定        │  OTSU二値化 → 黒画素率
│  (threshold = 0.35)  │  最大スコアの選択肢を採用
└──────────┬──────────┘
           ▼
    採点結果 JSON
    + 注釈画像 PNG
```

### 管理画面から採点まで

1. **`/admin`** で教科を作成し、問題数と選択肢数を設定
2. **`/sheet/{idx}`** でマークシート PDF を生成・ダウンロード（バブル座標メタデータが自動保存される）
3. 生徒に印刷配布 → マークを記入 → **スキャン**
4. **`/`** (ホーム) でスキャン済み PDF をアップロード → 自動採点
5. **`/scores`** で採点履歴を確認、CSV ダウンロード

---

## API リファレンス

| メソッド | エンドポイント | 説明 |
|---------|-------------|------|
| `GET` | `/api/health` | ヘルスチェック |
| `GET` | `/api/config` | 設定取得 (閾値 + 教科一覧) |
| `PUT` | `/api/config` | 設定更新 |
| `GET` | `/api/sheets/{idx}/generate` | マークシート PDF 生成 |
| `GET` | `/api/sheets/{idx}/pdf` | PDF 直接ダウンロード |
| `GET` | `/api/sheets/{idx}/tex` | LaTeX ソース取得 |
| `POST` | `/api/sheets/{idx}/print` | サーバー側印刷 |
| `GET` | `/api/generated/{gid}/pdf` | 生成済み PDF 取得 |
| `GET` | `/api/generated/{gid}/json` | 生成メタデータ取得 |
| `POST` | `/api/upload` | PDF アップロード → OMR 採点 |
| `GET` | `/api/scores` | 採点一覧 |
| `GET` | `/api/scores/{id}` | 採点詳細 |
| `GET` | `/api/scores/{id}/annotated/{page}` | 注釈画像 (PNG) |

Swagger UI: http://localhost:8000/docs

---

## 環境変数一覧

### バックエンド (FastAPI / Koyeb)

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `DATABASE_URL` | PostgreSQL 接続 (asyncpg) | `postgresql+asyncpg://postgres:postgres@db:5432/checker` |
| `DATABASE_URL_SYNC` | PostgreSQL 接続 (psycopg2, Alembic用) | `postgresql+psycopg2://...` |
| `CORS_ORIGINS` | CORS 許可オリジン (カンマ区切り) | `http://localhost:3000` |
| `STORAGE_DIR` | ファイル保存ディレクトリ | `/app/storage` |
| `SECRET_KEY` | アプリケーションシークレット | `dev-secret-change-me` |
| `DEBUG` | デバッグモード | `false` |
| `PORT` | サーバーポート | `8000` |
| `OMR_DEFAULT_DY_MM` | OMR デフォルト Y オフセット (mm) | `8.0` |

### フロントエンド (Next.js / Vercel)

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `API_BASE_URL` | サーバーサイド rewrite 先 URL | `http://api:8000` |
| `NEXT_PUBLIC_API_BASE_URL` | クライアント API ベース (空推奨) | `""` |

### ローカル開発 (Docker Compose)

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `POSTGRES_USER` | PostgreSQL ユーザー | `postgres` |
| `POSTGRES_PASSWORD` | PostgreSQL パスワード | `postgres` |
| `POSTGRES_DB` | データベース名 | `checker` |

---

## トラブルシューティング

### Neon 接続エラー

```
SSL connection is required
```

→ 接続文字列に `?sslmode=require` が含まれていることを確認。アプリは `neon.tech` を検出して自動で SSL 設定を適用します。

### LaTeX コンパイルエラー

```
xelatex not found
```

→ Docker コンテナ内では自動インストール済み。ローカル実行の場合は TeX Live をインストール:
```bash
# macOS
brew install --cask mactex-no-gui

# Ubuntu/Debian
sudo apt install texlive-xetex texlive-lang-japanese fonts-noto-cjk
```

### Vercel で API が 404

→ `API_BASE_URL` 環境変数が Koyeb の URL に正しく設定されているか確認してください。
`next.config.ts` の `rewrites` がサーバーサイドで `/api/*` をプロキシします。

### Koyeb でコンテナが起動しない

→ Dockerfile の `build target` が `prod` に設定されているか確認。
ポートは環境変数 `PORT` で制御されます (デフォルト: 8000)。

---

## ライセンス

MIT

---

## 既存データの移行

元の `config.json` からデータベースへの移行:

```bash
# API コンテナに config.json をコピーして移行スクリプトを実行
docker compose exec api python -c "
import json, asyncio
from app.services.config_service import save_config
from app.db import AsyncSessionLocal

async def migrate():
    with open('/tmp/config.json') as f:
        data = json.load(f)
    async with AsyncSessionLocal() as session:
        await save_config(session, data)
        await session.commit()

asyncio.run(migrate())
"
```

---

## 開発ガイド

### API にパッケージ追加

```bash
# requirements.txt を編集後
docker compose build api
docker compose up api
```

### フロント側パッケージ追加

```bash
docker compose exec web npm install <package>
```

### ホットリロード

- **API**: `uvicorn --reload` (Dockerfile dev ターゲットでデフォルト有効)
- **Web**: Next.js Fast Refresh (デフォルト有効)
- ソースコードはボリュームマウントされているため、ホスト側の編集が即座に反映されます。

---

## ライセンス

Private
