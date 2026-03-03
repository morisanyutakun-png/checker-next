"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getScore, annotatedPageUrl, type ScoreDetail } from "@/lib/api";

export default function ScoreDetailPage() {
  const params = useParams();
  const scoreId = params.id as string;
  const [score, setScore] = useState<ScoreDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getScore(scoreId)
      .then(setScore)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [scoreId]);

  function downloadCSV() {
    if (!score) return;
    const lines = ["page,question,selected,score,correct"];
    score.result.pages.forEach((page, pidx) => {
      page.questions.forEach((q) => {
        lines.push(
          [
            pidx + 1,
            q.label || q.id || "",
            q.selected_index ?? "",
            q.selected_score ?? "",
            q.correct ?? "",
          ].join(",")
        );
      });
    });
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `score-${scoreId}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (loading)
    return (
      <div className="flex items-center justify-center py-24">
        <div className="spinner" />
      </div>
    );

  if (!score)
    return (
      <div className="text-center py-24 animate-fade-in">
        <div className="text-4xl mb-4 opacity-50">🔍</div>
        <h1 className="text-xl font-semibold">採点結果が見つかりません</h1>
        <a href="/scores" className="btn btn-primary mt-4 inline-flex">一覧に戻る</a>
      </div>
    );

  const { result } = score;
  const s = result.score;
  const pct = s.total > 0 ? Math.round((s.correct / s.total) * 100) : 0;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">採点結果</h1>
          <p className="text-sm text-[var(--text-secondary)] mt-0.5">
            {score.subject_name && `${score.subject_name} — `}
            {score.created_at && new Date(score.created_at).toLocaleString("ja-JP", {
              year: "numeric",
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </p>
        </div>
        <a href="/scores" className="btn btn-ghost text-sm">
          ← 一覧へ
        </a>
      </div>

      {/* Score summary cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="stat-card">
          <p className="stat-card__value" style={{ color: "var(--accent)" }}>{s.correct}</p>
          <p className="stat-card__label">正解数</p>
        </div>
        <div className="stat-card">
          <p className="stat-card__value">{s.total}</p>
          <p className="stat-card__label">問題数</p>
        </div>
        <div className="stat-card">
          <p
            className="stat-card__value"
            style={{
              color: pct >= 80 ? "var(--success)" : pct >= 50 ? "var(--warning)" : "var(--danger)",
            }}
          >
            {pct}%
          </p>
          <p className="stat-card__label">正答率</p>
        </div>
      </div>

      {/* Pages */}
      {result.pages.map((page, pidx) => {
        const pc = page.questions.filter((q) => q.correct).length;
        return (
          <div key={pidx} className="card space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-lg">
                ページ {pidx + 1}
                <span className="text-[var(--text-secondary)] font-normal ml-2">
                  {pc}/{page.questions.length}
                </span>
              </h2>
              <a
                href={annotatedPageUrl(scoreId, pidx + 1)}
                target="_blank"
                className="btn btn-ghost text-sm"
              >
                注釈画像
              </a>
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
                        {q.selected_index != null
                          ? q.choices?.[q.selected_index]?.label || q.selected_index + 1
                          : "—"}
                      </td>
                      <td className="tabular-nums">
                        {q.selected_score != null ? (q.selected_score * 100).toFixed(1) + "%" : "—"}
                      </td>
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
      </div>
    </div>
  );
}
