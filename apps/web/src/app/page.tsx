"use client";

import { useEffect, useState, useRef } from "react";
import {
  getConfig,
  uploadPdf,
  type ConfigData,
  type SubjectData,
  type UploadResult,
} from "@/lib/api";

export default function HomePage() {
  const [config, setConfig] = useState<ConfigData | null>(null);
  const [subjects, setSubjects] = useState<SubjectData[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getConfig()
      .then((cfg) => {
        setConfig(cfg);
        setSubjects(cfg.subjects || []);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  async function handleUpload(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    if (!fd.get("pdf") || !(fd.get("pdf") as File).size) {
      alert("PDFファイルを選択してください");
      return;
    }
    setUploading(true);
    setResult(null);
    try {
      const res = await uploadPdf(fd);
      setResult(res);
    } catch (err: unknown) {
      alert("アップロードに失敗しました: " + (err instanceof Error ? err.message : err));
    } finally {
      setUploading(false);
    }
  }

  function handleDrag(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") setDragActive(true);
    else if (e.type === "dragleave") setDragActive(false);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files?.[0] && fileRef.current) {
      const dt = new DataTransfer();
      dt.items.add(e.dataTransfer.files[0]);
      fileRef.current.files = dt.files;
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="space-y-10 animate-fade-in">
      {/* Hero */}
      <section className="text-center py-12 hero-gradient rounded-2xl">
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-[var(--success-light)] text-[var(--success)] text-xs font-semibold mb-6 border border-[var(--success)]/20">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--success)] animate-pulse" />
          システム稼働中
        </div>
        <h1 className="text-[2.75rem] font-bold tracking-tight leading-[1.15] mb-4">
          マークシート
          <br />
          <span className="bg-clip-text text-transparent" style={{ backgroundImage: "var(--gradient-brand)" }}>
            自動採点
          </span>
        </h1>
        <p className="text-[var(--text-secondary)] text-base max-w-md mx-auto leading-relaxed">
          PDFをアップロードするだけで、
          <br className="sm:hidden" />
          OMR解析による高精度な自動採点を実行します
        </p>
      </section>

      {/* Upload Card */}
      <section className="card max-w-2xl mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: "var(--gradient-brand)" }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
          </div>
          <div>
            <h2 className="text-lg font-semibold tracking-tight">採点を開始</h2>
            <p className="text-sm text-[var(--text-secondary)]">スキャンしたPDFをアップロードしてください</p>
          </div>
        </div>

        <form onSubmit={handleUpload} className="space-y-5">
          {/* Drop Zone */}
          <div
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            className={`relative rounded-xl border-2 border-dashed p-8 text-center transition-all cursor-pointer
              ${dragActive
                ? "border-[var(--accent)] bg-[var(--accent-light)]"
                : "border-[var(--border-strong)] hover:border-[var(--accent)] hover:bg-[var(--accent-light)]"
              }`}
            onClick={() => fileRef.current?.click()}
          >
            <input
              ref={fileRef}
              type="file"
              name="pdf"
              accept="application/pdf"
              className="hidden"
            />
            <div className="text-3xl mb-2 opacity-50">
              {dragActive ? "📥" : "📄"}
            </div>
            <p className="text-sm font-medium text-[var(--text)]">
              {dragActive ? "ここにドロップ" : "クリックまたはドラッグ&ドロップ"}
            </p>
            <p className="text-xs text-[var(--text-tertiary)] mt-1">PDF ファイル</p>
          </div>

          {subjects.length > 0 && (
            <div>
              <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">
                教科
              </label>
              <select name="subject_idx" className="w-full">
                {subjects.map((s, i) => (
                  <option key={i} value={i}>
                    {s.name || `教科 ${i + 1}`}
                  </option>
                ))}
              </select>
            </div>
          )}

          <details className="group">
            <summary className="text-sm font-medium text-[var(--text-secondary)] cursor-pointer hover:text-[var(--accent)] transition-colors select-none">
              詳細オプション
            </summary>
            <div className="mt-3 space-y-4 animate-fade-in">
              <div>
                <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1.5">
                  生成済みPDFメタ GID（任意）
                </label>
                <input
                  type="text"
                  name="generated_gid_manual"
                  placeholder="GID を入力"
                  className="w-full"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1.5">
                    dx_mm オフセット
                  </label>
                  <input type="text" name="dx_mm" placeholder="0.0" className="w-full" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1.5">
                    dy_mm オフセット
                  </label>
                  <input type="text" name="dy_mm" placeholder="16.0" className="w-full" />
                </div>
              </div>
            </div>
          </details>

          <button
            type="submit"
            disabled={uploading}
            className="btn btn-primary w-full py-3"
          >
            {uploading ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                採点中...
              </>
            ) : (
              "アップロードして採点"
            )}
          </button>
        </form>
      </section>

      {/* Result */}
      {result && <ResultView result={result} />}

      {/* Subjects Grid */}
      {subjects.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-xl font-semibold tracking-tight">登録教科</h2>
            <a href="/admin" className="btn btn-ghost text-sm">
              管理 →
            </a>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {subjects.map((s, i) => (
              <a
                key={i}
                href={`/sheet/${i}`}
                className="card group flex items-center gap-4 hover:border-[var(--accent)] cursor-pointer transition-all hover:translate-y-[-2px]"
              >
                <div className="w-11 h-11 rounded-xl flex items-center justify-center font-bold text-white text-sm group-hover:scale-110 transition-transform" style={{ background: "var(--gradient-brand)" }}>
                  {i + 1}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium truncate">{s.name || `教科 ${i + 1}`}</p>
                  <p className="text-xs text-[var(--text-tertiary)] mt-0.5">
                    {s.questions?.length || 0} 問
                  </p>
                </div>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" strokeWidth="2" className="group-hover:translate-x-1 transition-transform">
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              </a>
            ))}
          </div>
        </section>
      )}

      {subjects.length === 0 && !result && (
        <div className="empty-state card">
          <div className="empty-state__icon">📋</div>
          <p className="empty-state__title">教科が未登録です</p>
          <p className="empty-state__description">
            管理画面で教科と問題を追加して、マークシートの採点を始めましょう。
          </p>
          <a href="/admin" className="btn btn-primary mt-4 inline-flex">
            管理画面へ
          </a>
        </div>
      )}
    </div>
  );
}

/* ── Result display ────────────────────────────────────────── */

function ResultView({ result }: { result: UploadResult }) {
  const { result: grading, csv_data, subject, saved_score_id } = result;
  const score = grading.score;
  const pct = score.total > 0 ? Math.round((score.correct / score.total) * 100) : 0;

  function downloadCSV() {
    const blob = new Blob([csv_data], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "result.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="max-w-4xl mx-auto space-y-6 animate-fade-in">
      {/* Score Summary */}
      <div className="card">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold tracking-tight">採点結果</h2>
            {subject && (
              <p className="text-sm text-[var(--text-secondary)] mt-1">教科: {subject}</p>
            )}
          </div>
          <div className="flex items-center gap-5">
            <div className="text-right">
              <p className="text-3xl font-bold tracking-tight">
                {score.correct}
                <span className="text-base text-[var(--text-secondary)] font-normal"> / {score.total}</span>
              </p>
            </div>
            <ScoreRing pct={pct} size={60} />
          </div>
        </div>
      </div>

      {/* Per-page details */}
      {grading.pages.map((page, pidx) => {
        const pageCorrect = page.questions.filter((q) => q.correct).length;
        return (
          <div key={pidx} className="card space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">
                ページ {pidx + 1}
                <span className="text-[var(--text-secondary)] font-normal ml-2">
                  {pageCorrect}/{page.questions.length}
                </span>
              </h3>
              {saved_score_id && (
                <a
                  href={`/api/scores/${saved_score_id}/annotated/${pidx + 1}`}
                  target="_blank"
                  className="text-sm btn btn-ghost"
                >
                  注釈画像
                </a>
              )}
            </div>
            <div className="overflow-x-auto -mx-1.5">
              <table>
                <thead>
                  <tr>
                    <th>問題</th>
                    <th>選択</th>
                    <th>スコア</th>
                    <th>結果</th>
                  </tr>
                </thead>
                <tbody>
                  {page.questions.map((q, qi) => (
                    <tr key={qi}>
                      <td className="font-medium">{q.label || q.id || qi + 1}</td>
                      <td>
                        {q.selected_index !== null && q.selected_index !== undefined
                          ? q.choices[q.selected_index]?.label || q.selected_index + 1
                          : "—"}
                      </td>
                      <td className="tabular-nums">{q.selected_score != null ? (q.selected_score * 100).toFixed(1) + "%" : "—"}</td>
                      <td>
                        {q.correct ? (
                          <span className="badge badge-success">正解</span>
                        ) : q.selected_index != null ? (
                          <span className="badge badge-danger">不正解</span>
                        ) : (
                          <span className="badge badge-warning">未選択</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}

      <div className="flex gap-3">
        <button onClick={downloadCSV} className="btn btn-secondary text-sm">
          CSV ダウンロード
        </button>
        {saved_score_id && (
          <a href={`/scores/${saved_score_id}`} className="btn btn-secondary text-sm">
            詳細を表示
          </a>
        )}
      </div>
    </section>
  );
}

/* ── Score Ring ─────────────────────────────────────────────── */

function ScoreRing({ pct, size = 56 }: { pct: number; size?: number }) {
  const r = (size - 8) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (pct / 100) * circ;
  const color =
    pct >= 80 ? "var(--success)" : pct >= 50 ? "var(--warning)" : "var(--danger)";

  return (
    <svg width={size} height={size} className="progress-ring">
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="var(--border)"
        strokeWidth="4"
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth="4"
        strokeLinecap="round"
        strokeDasharray={circ}
        strokeDashoffset={offset}
        className="progress-ring__circle"
      />
      <text
        x="50%"
        y="50%"
        textAnchor="middle"
        dominantBaseline="central"
        fill={color}
        fontSize="0.8rem"
        fontWeight="700"
        style={{ transform: "rotate(90deg)", transformOrigin: "center" }}
      >
        {pct}%
      </text>
    </svg>
  );
}
