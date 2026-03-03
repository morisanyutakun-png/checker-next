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
      <div className="flex items-center justify-center py-20">
        <div className="w-8 h-8 border-3 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
      </div>
    );

  if (!score)
    return (
      <div className="text-center py-20">
        <h1 className="text-xl font-semibold">採点結果が見つかりません</h1>
      </div>
    );

  const { result } = score;
  const s = result.score;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">採点結果</h1>
          <p className="text-sm text-[var(--text-secondary)] mt-0.5">
            {score.subject_name && `教科: ${score.subject_name} — `}
            {score.created_at && new Date(score.created_at).toLocaleString("ja-JP")}
          </p>
        </div>
        <a href="/scores" className="btn btn-secondary text-sm">
          ← 一覧へ
        </a>
      </div>

      {/* Score summary */}
      <div className="card flex items-center justify-between">
        <div>
          <p className="text-sm text-[var(--text-secondary)]">正答数</p>
          <p className="text-4xl font-bold mt-1">
            {s.correct}
            <span className="text-xl text-[var(--text-secondary)] font-normal"> / {s.total}</span>
          </p>
        </div>
        <div
          className="w-20 h-20 rounded-full flex items-center justify-center text-2xl font-bold"
          style={{
            background:
              s.total > 0 && s.correct / s.total >= 0.8
                ? "rgba(52,199,89,0.12)"
                : s.total > 0 && s.correct / s.total >= 0.5
                  ? "rgba(255,149,0,0.12)"
                  : "rgba(255,59,48,0.12)",
            color:
              s.total > 0 && s.correct / s.total >= 0.8
                ? "var(--success)"
                : s.total > 0 && s.correct / s.total >= 0.5
                  ? "var(--warning)"
                  : "var(--danger)",
          }}
        >
          {s.total > 0 ? Math.round((s.correct / s.total) * 100) : 0}%
        </div>
      </div>

      {/* Pages */}
      {result.pages.map((page, pidx) => {
        const pc = page.questions.filter((q) => q.correct).length;
        return (
          <div key={pidx} className="card space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-lg">
                ページ {pidx + 1} — {pc}/{page.questions.length}
              </h2>
              <a
                href={annotatedPageUrl(scoreId, pidx + 1)}
                target="_blank"
                className="text-sm"
              >
                注釈画像を開く
              </a>
            </div>

            <div className="overflow-x-auto -mx-2">
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
                      <td>
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
