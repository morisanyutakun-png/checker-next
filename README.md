# Checker-Next

**OMR（マークシート）自動採点 Web アプリケーション**  
Flask モノリスから **Next.js 15 + FastAPI + PostgreSQL (Neon)** へ移行したモダン構成。

> **v2.0** – 2026-03 リリース

---

## アーキテクチャ

```
┌────────────┐      ┌──────────────┐      ┌───────────────┐
│  Next.js   │─────▶│   FastAPI     │─────▶│  PostgreSQL   │
│  (React)   │ REST │  (Python)     │ SQL  │  (Neon/local) │
│  port 3000 │      │  port 8000    │      │  port 5432    │
└────────────┘      └──────────────┘      └───────────────┘
       │                     │
       │              ┌──────┴──────┐
       │              │  xelatex    │  LaTeX → PDF コンパイル
       │              │  omr.py     │  OMR 解析 (OpenCV)
       │              │  storage/   │  生成 PDF 保存
       │              └─────────────┘
       │
  (任意) nginx:8080 でリバースプロキシ統合
```

| レイヤー | 技術 | 場所 |
|---------|------|------|
| フロントエンド | Next.js 15 (App Router), React 19, Tailwind CSS v4 | `apps/web/` |
| バックエンド | FastAPI, SQLAlchemy 2.x (async), Pydantic v2 | `apps/api/` |
| データベース | PostgreSQL 16 (dev) / Neon (prod) | Docker `db` サービス |
| OMR エンジン | OpenCV, PyMuPDF, Pillow | `apps/api/app/omr.py` |
| LaTeX | xelatex (TeX Live) | API コンテナ内蔵 |
| インフラ | Docker Compose, nginx (任意) | `docker-compose.yml`, `infra/` |

---

## ディレクトリ構成

```
checker-next/
├── apps/
│   ├── api/                 # FastAPI バックエンド
│   │   ├── app/
│   │   │   ├── main.py          # アプリエントリポイント
│   │   │   ├── config.py        # Pydantic Settings
│   │   │   ├── db.py            # SQLAlchemy async セッション
│   │   │   ├── models.py        # ORM モデル (AppConfig, Subject, Score, …)
│   │   │   ├── schemas.py       # Pydantic スキーマ
│   │   │   ├── omr.py           # OMR 処理エンジン (旧 omr.py)
│   │   │   ├── routers/
│   │   │   │   ├── config_router.py   # GET/PUT /api/config
│   │   │   │   ├── sheets.py         # シート生成・PDF・印刷
│   │   │   │   ├── upload.py         # PDF アップロード・採点
│   │   │   │   ├── scores.py         # 採点結果一覧・詳細
│   │   │   │   └── generated.py      # 生成済み PDF 取得
│   │   │   └── services/
│   │   │       ├── config_service.py  # DB ⇔ config 変換
│   │   │       ├── latex_service.py   # LaTeX レンダリング
│   │   │       └── omr_service.py     # OMR ラッパー
│   │   ├── alembic/             # マイグレーション
│   │   ├── templates/           # LaTeX テンプレート (sheet.tex 等)
│   │   ├── storage/             # 生成 PDF / スコア JSON
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── web/                 # Next.js フロントエンド
│       ├── src/
│       │   ├── app/
│       │   │   ├── page.tsx           # ホーム (アップロード & 採点)
│       │   │   ├── admin/page.tsx     # 設定管理
│       │   │   ├── sheet/[idx]/page.tsx  # シートプレビュー
│       │   │   ├── scores/page.tsx    # 採点一覧
│       │   │   └── scores/[id]/page.tsx  # 採点詳細
│       │   ├── components/
│       │   └── lib/api.ts         # API クライアント
│       ├── Dockerfile
│       ├── next.config.ts
│       └── package.json
├── infra/
│   └── nginx.conf           # リバースプロキシ設定
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## セットアップ（ローカル開発）

### 前提条件

- Docker & Docker Compose v2

### 1. リポジトリをクローン

```bash
git clone <repo-url> checker-next
cd checker-next
```

### 2. 環境変数ファイルを作成

```bash
cp .env.example .env
```

> デフォルト値でローカル開発にそのまま使えます。

### 3. コンテナを起動

```bash
docker compose up --build
```

起動後のポート:

| サービス | URL |
|---------|-----|
| Next.js (フロント) | http://localhost:3000 |
| FastAPI (API) | http://localhost:8000 |
| API ドキュメント (Swagger) | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 |

### 4. (任意) nginx リバースプロキシを有効化

```bash
docker compose --profile with-nginx up --build
```

→ http://localhost:8080 で統合アクセス（`/api/*` → FastAPI, `/` → Next.js）

### 5. (任意) pgAdmin を起動

```bash
docker compose --profile tools up --build
```

→ http://localhost:5050 (admin@local.dev / admin)

---

## データベースマイグレーション

API コンテナ起動時に `Base.metadata.create_all()` でテーブルが自動作成されます。  
本番環境では Alembic を使用してください:

```bash
# API コンテナ内で実行
docker compose exec api alembic upgrade head
```

---

## API ルートマッピング

Flask → FastAPI への対応表:

| Flask ルート | FastAPI エンドポイント | 説明 |
|-------------|----------------------|------|
| `GET /` | Next.js `page.tsx` | ホーム画面 |
| `GET /admin` | Next.js `admin/page.tsx` | 設定管理 |
| `GET /api/config` | `GET /api/config` | 設定取得 |
| `POST /api/config` | `PUT /api/config` | 設定更新 |
| `GET /sheet/<idx>` | Next.js `sheet/[idx]/page.tsx` | シートプレビュー |
| `GET /generate/<idx>` | `GET /api/sheets/{idx}/generate` | PDF 生成 |
| `GET /generated_pdf/<gid>` | `GET /api/generated/{gid}/pdf` | 生成済み PDF 取得 |
| `POST /upload` | `POST /api/upload` | PDF アップロード → 採点 |
| `GET /results` / `GET /scores` | Next.js `scores/page.tsx` | 採点一覧 |
| `GET /scores/<id>` | `GET /api/scores/{id}` | 採点詳細 |
| `GET /sheet_pdf/<idx>` | `GET /api/sheets/{idx}/pdf` | シート PDF ダウンロード |
| `GET /sheet_tex/<idx>` | `GET /api/sheets/{idx}/tex` | LaTeX ソース取得 |
| `POST /print_sheet/<idx>` | `POST /api/sheets/{idx}/print` | サーバー側印刷 |

---

## 本番デプロイ

### データベース: Neon

1. [Neon Console](https://console.neon.tech) でプロジェクト作成
2. `.env` の `DATABASE_URL` を Neon 接続文字列に変更:
   ```
   DATABASE_URL=postgresql+asyncpg://user:pass@ep-xxx.us-east-2.aws.neon.tech/checker?sslmode=require
   ```

### フロントエンド: Vercel

```bash
cd apps/web
vercel --prod
```

環境変数 `NEXT_PUBLIC_API_BASE_URL` に API のデプロイ先 URL を設定。

### バックエンド: Koyeb / Railway / Fly.io

API コンテナの `Dockerfile` (production ターゲット) をそのまま使用。  
環境変数 `DATABASE_URL` を Neon 接続文字列に設定。

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
