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

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-8 h-8 border-3 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Hero */}
      <section className="text-center py-6">
        <h1 className="text-4xl font-bold tracking-tight mb-3">OMR 採点システム</h1>
        <p className="text-[var(--text-secondary)] text-lg">
          マークシートをアップロードして自動採点
        </p>
      </section>

      {/* Upload */}
      <section className="card max-w-2xl mx-auto">
        <h2 className="text-xl font-semibold mb-4">採点を開始</h2>
        <form onSubmit={handleUpload} className="space-y-5">
          <div>
            <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">
              PDFファイル
            </label>
            <input
              ref={fileRef}
              type="file"
              name="pdf"
              accept="application/pdf"
              className="w-full"
            />
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

          <div>
            <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">
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
              <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">
                dx_mm オフセット
              </label>
              <input type="text" name="dx_mm" placeholder="0.0" className="w-full" />
            </div>
            <div>
              <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">
                dy_mm オフセット
              </label>
              <input type="text" name="dy_mm" placeholder="16.0" className="w-full" />
            </div>
          </div>

          <button
            type="submit"
            disabled={uploading}
            className="btn btn-primary w-full"
          >
            {uploading ? "採点中..." : "アップロードして採点"}
          </button>
        </form>
      </section>

      {/* Result */}
      {result && <ResultView result={result} />}

      {/* Subjects */}
      <section className="card">
        <h2 className="text-xl font-semibold mb-4">教科一覧</h2>
        {subjects.length === 0 ? (
          <p className="text-[var(--text-secondary)]">
            教科が登録されていません。
            <a href="/admin" className="underline">管理画面</a>で追加してください。
          </p>
        ) : (
          <ul className="divide-y divide-[var(--border)]">
            {subjects.map((s, i) => (
              <li key={i} className="flex items-center justify-between py-3.5">
                <span className="font-medium">{s.name || `教科 ${i + 1}`}</span>
                <div className="flex items-center gap-3">
                  <a href={`/sheet/${i}`} className="btn btn-secondary text-sm py-1.5 px-3">
                    プレビュー
                  </a>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

/* ── Result display ────────────────────────────────────────── */

function ResultView({ result }: { result: UploadResult }) {
  const { result: grading, csv_data, subject, saved_score_id } = result;
  const score = grading.score;

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
    <section className="card max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">採点結果</h2>
          {subject && (
            <p className="text-sm text-[var(--text-secondary)] mt-0.5">教科: {subject}</p>
          )}
        </div>
        <div className="text-right">
          <p className="text-3xl font-bold">
            {score.correct}
            <span className="text-lg text-[var(--text-secondary)] font-normal"> / {score.total}</span>
          </p>
          <p className="text-sm text-[var(--text-secondary)]">
            正答率 {score.total > 0 ? Math.round((score.correct / score.total) * 100) : 0}%
          </p>
        </div>
      </div>

      {grading.pages.map((page, pidx) => {
        const pageCorrect = page.questions.filter((q) => q.correct).length;
        return (
          <div key={pidx} className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">
                ページ {pidx + 1} — {pageCorrect}/{page.questions.length}
              </h3>
              {saved_score_id && (
                <a
                  href={`/api/scores/${saved_score_id}/annotated/${pidx + 1}`}
                  target="_blank"
                  className="text-sm"
                >
                  注釈画像
                </a>
              )}
            </div>
            <div className="overflow-x-auto">
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
                      <td>{q.selected_score != null ? (q.selected_score * 100).toFixed(1) + "%" : "—"}</td>
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
