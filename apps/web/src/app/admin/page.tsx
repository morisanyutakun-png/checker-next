"use client";

import { useEffect, useState, useCallback } from "react";
import {
  getConfig,
  saveConfig,
  type ConfigData,
  type SubjectData,
} from "@/lib/api";

// ── Default layout values ─────────────────────────────────
const DEFAULT_LAYOUT = {
  cols: 4,
  row_height: 6.0,
  header_offset_mm: 20.0,
  bubble_rx: 2.0,
  bubble_ry: 1.8,
  label_width: 10.0,
  col_gap: 3.0,
};

type LayoutConfig = typeof DEFAULT_LAYOUT;

function getLayout(subject: SubjectData): LayoutConfig {
  const raw = (subject as Record<string, unknown>).layout as Partial<LayoutConfig> | undefined;
  return { ...DEFAULT_LAYOUT, ...raw };
}

// ── Presets ───────────────────────────────────────────────
const LAYOUT_PRESETS: { label: string; description: string; layout: Partial<LayoutConfig> }[] = [
  {
    label: "標準 (4択×40問)",
    description: "4列・4択向け。最もバランスの良い標準配置",
    layout: { cols: 4, row_height: 6.0, bubble_rx: 2.0, bubble_ry: 1.8, label_width: 10.0, col_gap: 3.0, header_offset_mm: 20.0 },
  },
  {
    label: "多択 (10択×30問)",
    description: "3列・10択以上向け。バブルが小さくなるが見やすい",
    layout: { cols: 3, row_height: 5.5, bubble_rx: 1.6, bubble_ry: 1.5, label_width: 9.0, col_gap: 2.5, header_offset_mm: 20.0 },
  },
  {
    label: "大問数 (5択×60問)",
    description: "5列・大量問題向け。コンパクト配置",
    layout: { cols: 5, row_height: 5.0, bubble_rx: 1.8, bubble_ry: 1.6, label_width: 8.0, col_gap: 2.0, header_offset_mm: 18.0 },
  },
  {
    label: "少数精鋭 (15択×20問)",
    description: "2列・15択対応。幅広い解答欄",
    layout: { cols: 2, row_height: 7.0, bubble_rx: 1.4, bubble_ry: 1.3, label_width: 10.0, col_gap: 4.0, header_offset_mm: 20.0 },
  },
  {
    label: "ゆったり (4択×20問)",
    description: "2列・大きめのバブルで見やすい",
    layout: { cols: 2, row_height: 8.0, bubble_rx: 2.5, bubble_ry: 2.2, label_width: 12.0, col_gap: 4.0, header_offset_mm: 20.0 },
  },
];

export default function AdminPage() {
  const [config, setConfig] = useState<ConfigData | null>(null);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [saving, setSaving] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [layoutOpen, setLayoutOpen] = useState(false);

  useEffect(() => {
    getConfig()
      .then((cfg) => {
        setConfig(cfg);
        if (cfg.subjects.length > 0) setCurrentIdx(0);
      })
      .catch(console.error);
  }, []);

  const showFlash = useCallback((msg: string) => {
    setFlash(msg);
    setTimeout(() => setFlash(null), 3000);
  }, []);

  if (!config)
    return (
      <div className="flex items-center justify-center py-24">
        <div className="spinner" />
      </div>
    );

  const subjects = config.subjects || [];
  const current = subjects[currentIdx] || null;

  function updateSubject(idx: number, patch: Partial<SubjectData>) {
    if (!config) return;
    const next = { ...config };
    next.subjects = [...next.subjects];
    next.subjects[idx] = { ...next.subjects[idx], ...patch };
    setConfig(next);
  }

  function updateLayout(idx: number, layoutPatch: Partial<LayoutConfig>) {
    if (!config) return;
    const subj = config.subjects[idx];
    const currentLayout = getLayout(subj);
    const merged = { ...currentLayout, ...layoutPatch };
    updateSubject(idx, { layout: merged } as Partial<SubjectData>);
  }

  function applyPreset(idx: number, preset: Partial<LayoutConfig>) {
    updateLayout(idx, preset);
    showFlash("プリセットを適用しました");
  }

  function addSubject() {
    if (!config) return;
    const name = prompt("教科名を入力してください", `Subject ${subjects.length + 1}`);
    if (name === null) return;
    const next = { ...config };
    next.subjects = [
      ...next.subjects,
      { name: name.trim() || `Subject ${subjects.length + 1}`, questions: [], sheet_template: "default" },
    ];
    setConfig(next);
    setCurrentIdx(next.subjects.length - 1);
  }

  function removeSubject() {
    if (!config || !current) return;
    if (!confirm(`「${current.name}」を削除しますか？`)) return;
    const next = { ...config };
    next.subjects = next.subjects.filter((_, i) => i !== currentIdx);
    setConfig(next);
    setCurrentIdx(Math.max(0, currentIdx - 1));
  }

  function addQuestion() {
    if (!config || !current) return;
    const qs = [...(current.questions || [])];
    qs.push({ id: qs.length + 1, label: `Q${qs.length + 1}`, choices: [], answer: null });
    updateSubject(currentIdx, { questions: qs });
  }

  function bulkGenerate(count: number, choicesPer: number) {
    if (!config || !current) return;
    const qs: Record<string, unknown>[] = [];
    for (let i = 0; i < count; i++) {
      qs.push({
        id: i + 1,
        label: `Q${i + 1}`,
        choices: [],
        answer: null,
        num_choices: choicesPer > 0 ? choicesPer : undefined,
      });
    }
    updateSubject(currentIdx, { questions: qs });
  }

  async function handleSave() {
    if (!config) return;
    setSaving(true);
    try {
      const saved = await saveConfig(config);
      setConfig(saved);
      showFlash("設定を保存しました");
    } catch (err: unknown) {
      showFlash("保存に失敗しました: " + (err instanceof Error ? err.message : err));
    } finally {
      setSaving(false);
    }
  }

  // ── Compute sheet capacity info ──
  const layout = current ? getLayout(current) : DEFAULT_LAYOUT;
  const usableH = 210 - layout.header_offset_mm - 12;
  const maxRowsPerCol = Math.max(1, Math.floor(usableH / layout.row_height));
  const sheetCapacity = maxRowsPerCol * layout.cols;
  const questionCount = current?.questions?.length || 0;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">管理設定</h1>
          <p className="text-sm text-[var(--text-secondary)] mt-0.5">
            教科・問題・レイアウトの設定を管理
          </p>
        </div>
        <div className="flex gap-2">
          <a href={current ? `/sheet/${currentIdx}` : "#"} className="btn btn-ghost text-sm">
            プレビュー
          </a>
          <button onClick={handleSave} disabled={saving} className="btn btn-primary text-sm">
            {saving ? (
              <>
                <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                保存中
              </>
            ) : (
              "保存"
            )}
          </button>
        </div>
      </div>

      {flash && (
        <div className="toast toast-success">
          {flash}
        </div>
      )}

      {/* Threshold */}
      <div className="card">
        <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">
          閾値 (threshold)
        </label>
        <input
          type="number"
          step="0.01"
          min="0"
          max="1"
          value={config.threshold}
          onChange={(e) => setConfig({ ...config, threshold: parseFloat(e.target.value) || 0.35 })}
          className="w-48"
        />
      </div>

      {/* Subject selector */}
      <div className="card">
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <select
            value={currentIdx}
            onChange={(e) => setCurrentIdx(Number(e.target.value))}
            className="flex-1 min-w-40"
          >
            {subjects.length === 0 && <option value={-1}>（教科がありません）</option>}
            {subjects.map((s, i) => (
              <option key={i} value={i}>
                {s.name || `Subject ${i + 1}`}
              </option>
            ))}
          </select>
          <button onClick={addSubject} className="btn btn-secondary text-sm">
            + 教科追加
          </button>
          {current && (
            <button onClick={removeSubject} className="btn btn-danger text-sm">
              削除
            </button>
          )}
        </div>

        {current && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">教科名</label>
                <input
                  type="text"
                  value={current.name}
                  onChange={(e) => updateSubject(currentIdx, { name: e.target.value })}
                  className="w-full"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">テンプレート</label>
                <select
                  value={current.sheet_template || "default"}
                  onChange={(e) => updateSubject(currentIdx, { sheet_template: e.target.value })}
                  className="w-full"
                >
                  <option value="default">片面（default）</option>
                  <option value="math_double">数学（2ページ）</option>
                </select>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── Layout Settings ── */}
      {current && (
        <div className="card">
          <button
            onClick={() => setLayoutOpen(!layoutOpen)}
            className="flex items-center justify-between w-full text-left"
          >
            <div className="flex items-center gap-2">
              <span className="text-lg">{layoutOpen ? "▼" : "▶"}</span>
              <div>
                <h3 className="font-semibold">マークシート レイアウト設定</h3>
                <p className="text-xs text-[var(--text-secondary)] mt-0.5">
                  列数・行の高さ・バブルサイズなどを細かく調整
                </p>
              </div>
            </div>
            <div className="text-sm text-[var(--text-secondary)]">
              {layout.cols}列 / 行高{layout.row_height}mm / 最大{sheetCapacity}問
            </div>
          </button>

          {layoutOpen && (
            <div className="mt-4 pt-4 border-t border-[var(--border)] space-y-5">
              {/* Capacity indicator */}
              <div className={`px-4 py-3 rounded-xl text-sm ${questionCount > sheetCapacity ? 'bg-red-100 text-red-700 dark:bg-red-900/20 dark:text-red-400' : 'bg-indigo-50 text-indigo-700 dark:bg-indigo-900/20 dark:text-indigo-300'}`}>
                <div className="flex items-center justify-between">
                  <span>📄 1ページ収容量: <strong>{sheetCapacity}問</strong>（{layout.cols}列 × {maxRowsPerCol}行）</span>
                  <span>現在の問題数: <strong>{questionCount}問</strong></span>
                </div>
                {questionCount > sheetCapacity && (
                  <p className="mt-1 text-xs">⚠️ 問題数がページ容量を超えています。列数を増やすか行高さを減らしてください。</p>
                )}
              </div>

              {/* Presets */}
              <div>
                <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2">プリセット</label>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                  {LAYOUT_PRESETS.map((p, pi) => (
                    <button
                      key={pi}
                      onClick={() => applyPreset(currentIdx, p.layout)}
                      className="text-left px-3 py-2.5 rounded-xl border border-[var(--border)] hover:border-[var(--accent)] hover:bg-[var(--accent)]/5 transition-colors"
                    >
                      <div className="text-sm font-medium">{p.label}</div>
                      <div className="text-xs text-[var(--text-secondary)] mt-0.5">{p.description}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Manual controls */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
                <LayoutSlider
                  label="列数"
                  hint="問題を何列に分けるか"
                  value={layout.cols}
                  min={1} max={8} step={1}
                  unit="列"
                  onChange={(v) => updateLayout(currentIdx, { cols: v })}
                />
                <LayoutSlider
                  label="行の高さ"
                  hint="各問の縦幅"
                  value={layout.row_height}
                  min={4.0} max={10.0} step={0.5}
                  unit="mm"
                  onChange={(v) => updateLayout(currentIdx, { row_height: v })}
                />
                <LayoutSlider
                  label="ヘッダー余白"
                  hint="上端からの開始位置"
                  value={layout.header_offset_mm}
                  min={16.0} max={30.0} step={1.0}
                  unit="mm"
                  onChange={(v) => updateLayout(currentIdx, { header_offset_mm: v })}
                />
                <LayoutSlider
                  label="バブル横半径"
                  hint="マーク丸の横幅"
                  value={layout.bubble_rx}
                  min={1.0} max={3.0} step={0.1}
                  unit="mm"
                  onChange={(v) => updateLayout(currentIdx, { bubble_rx: v })}
                />
                <LayoutSlider
                  label="バブル縦半径"
                  hint="マーク丸の縦幅"
                  value={layout.bubble_ry}
                  min={0.8} max={2.8} step={0.1}
                  unit="mm"
                  onChange={(v) => updateLayout(currentIdx, { bubble_ry: v })}
                />
                <LayoutSlider
                  label="ラベル幅"
                  hint="問番号の列幅"
                  value={layout.label_width}
                  min={6.0} max={16.0} step={0.5}
                  unit="mm"
                  onChange={(v) => updateLayout(currentIdx, { label_width: v })}
                />
                <LayoutSlider
                  label="列間スペース"
                  hint="列と列の間隔"
                  value={layout.col_gap}
                  min={1.0} max={6.0} step={0.5}
                  unit="mm"
                  onChange={(v) => updateLayout(currentIdx, { col_gap: v })}
                />
              </div>

              {/* Visual preview diagram */}
              <LayoutPreview layout={layout} questionCount={questionCount} maxRowsPerCol={maxRowsPerCol} />
            </div>
          )}
        </div>
      )}

      {/* Bulk actions */}
      {current && (
        <div className="card">
          <h3 className="font-semibold mb-3">一括操作</h3>
          <BulkControls onGenerate={bulkGenerate} questionCount={current.questions.length} />
        </div>
      )}

      {/* Questions */}
      {current && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold">問題一覧（{current.questions.length}問）</h3>
            <button onClick={addQuestion} className="btn btn-secondary text-sm">
              + 問題追加
            </button>
          </div>

          {current.questions.length === 0 ? (
            <p className="text-[var(--text-secondary)] text-center py-6">
              問題がありません。「一括生成」または「+ 問題追加」で作成してください。
            </p>
          ) : (
            <div className="space-y-2">
              {current.questions.map((q, qi) => (
                <QuestionRow
                  key={qi}
                  q={q as Record<string, unknown>}
                  idx={qi}
                  onUpdate={(patch) => {
                    const qs = [...current.questions];
                    qs[qi] = { ...qs[qi], ...patch };
                    updateSubject(currentIdx, { questions: qs });
                  }}
                  onRemove={() => {
                    const qs = current.questions.filter((_, i) => i !== qi);
                    updateSubject(currentIdx, { questions: qs });
                  }}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Layout Slider ─────────────────────────────────────── */

function LayoutSlider({
  label,
  hint,
  value,
  min,
  max,
  step,
  unit,
  onChange,
}: {
  label: string;
  hint: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit: string;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1">
        <label className="text-sm font-medium">{label}</label>
        <span className="text-xs font-mono text-[var(--accent)]">{value}{unit}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-1.5 rounded-lg appearance-none cursor-pointer accent-[var(--accent)]"
      />
      <p className="text-xs text-[var(--text-secondary)] mt-0.5">{hint}</p>
    </div>
  );
}

/* ── Layout Preview ─────────────────────────────────────── */

function LayoutPreview({
  layout,
  questionCount,
  maxRowsPerCol,
}: {
  layout: LayoutConfig;
  questionCount: number;
  maxRowsPerCol: number;
}) {
  const cols = layout.cols;
  const rowsPerCol = questionCount > 0
    ? Math.min(Math.ceil(questionCount / cols), maxRowsPerCol)
    : Math.min(10, maxRowsPerCol);
  const displayRows = Math.min(rowsPerCol, 12);
  const sheetCapacity = maxRowsPerCol * cols;

  const previewChoices = Math.min(Math.floor(60 / cols), 15);

  return (
    <div>
      <label className="block text-sm font-medium text-[var(--text-secondary)] mb-2">レイアウト イメージ</label>
      <div className="border border-[var(--border)] rounded-xl p-3 bg-[var(--bg-secondary)] overflow-x-auto">
        {/* Mini header bar */}
        <div className="bg-[#1a1a2e] rounded-md px-3 py-1.5 mb-2 flex items-center justify-between">
          <span className="text-[10px] text-white font-bold">マークシート解答用紙</span>
          <div className="flex gap-3">
            <span className="text-[9px] text-white/60">受験番号 ___</span>
            <span className="text-[9px] text-white/60">氏名 ___</span>
          </div>
        </div>
        {/* Columns */}
        <div className="flex gap-1" style={{ minWidth: cols * 100 }}>
          {Array.from({ length: cols }, (_, ci) => (
            <div key={ci} className={`flex-1 ${ci > 0 ? 'border-l border-[var(--border)]' : ''} pl-1`}>
              {Array.from({ length: displayRows }, (_, ri) => {
                const qNum = ci * rowsPerCol + ri + 1;
                const isOver = qNum > questionCount && questionCount > 0;
                return (
                  <div
                    key={ri}
                    className={`flex items-center gap-0.5 py-0.5 ${isOver ? 'opacity-20' : ''}`}
                  >
                    <span className="text-[8px] font-mono w-5 text-right text-[var(--text-secondary)]">
                      {qNum}
                    </span>
                    <div className="flex gap-px">
                      {Array.from({ length: Math.min(previewChoices, 10) }, (_, bi) => (
                        <div
                          key={bi}
                          className="w-2 h-2 rounded-full border border-[var(--text-secondary)]/40"
                        />
                      ))}
                      {previewChoices > 10 && (
                        <span className="text-[6px] text-[var(--text-secondary)] ml-0.5">+{previewChoices - 10}</span>
                      )}
                    </div>
                  </div>
                );
              })}
              {rowsPerCol > displayRows && (
                <div className="text-[8px] text-[var(--text-secondary)] text-center py-0.5">
                  … +{rowsPerCol - displayRows}行
                </div>
              )}
            </div>
          ))}
        </div>
        <div className="text-[10px] text-[var(--text-secondary)] mt-2 text-center">
          {cols}列 × {maxRowsPerCol}行 = 最大 {sheetCapacity}問 | 実際: {questionCount}問
        </div>
      </div>
    </div>
  );
}

/* ── Bulk Controls ───────────────────────────────────────── */

function BulkControls({
  onGenerate,
  questionCount,
}: {
  onGenerate: (count: number, choices: number) => void;
  questionCount: number;
}) {
  const [count, setCount] = useState(questionCount || 10);
  const [choices, setChoices] = useState(5);

  return (
    <div className="flex flex-wrap items-end gap-3">
      <div>
        <label className="block text-sm text-[var(--text-secondary)] mb-1">問題数</label>
        <input
          type="number"
          min={0}
          value={count}
          onChange={(e) => setCount(Number(e.target.value))}
          className="w-24"
        />
      </div>
      <div>
        <label className="block text-sm text-[var(--text-secondary)] mb-1">選択肢/問</label>
        <input
          type="number"
          min={2}
          max={15}
          value={choices}
          onChange={(e) => setChoices(Number(e.target.value))}
          className="w-24"
        />
        <p className="text-xs text-[var(--text-secondary)] mt-0.5">2〜15</p>
      </div>
      <button onClick={() => onGenerate(count, choices)} className="btn btn-secondary text-sm">
        一括生成
      </button>
    </div>
  );
}

/* ── Question Row ──────────────────────────────────────── */

function QuestionRow({
  q,
  idx,
  onUpdate,
  onRemove,
}: {
  q: Record<string, unknown>;
  idx: number;
  onUpdate: (patch: Record<string, unknown>) => void;
  onRemove: () => void;
}) {
  const [open, setOpen] = useState(false);
  const numChoices = (q.num_choices as number) || (q.choices as unknown[])?.length || 0;
  const answer = q.answer as number | null | undefined;

  return (
    <div className="border border-[var(--border)] rounded-xl px-4 py-2.5">
      <div className="flex items-center justify-between">
        <button onClick={() => setOpen(!open)} className="flex items-center gap-2 text-left flex-1">
          <span className="text-xs font-mono text-[var(--text-secondary)] w-6">
            {open ? "▼" : "▶"}
          </span>
          <span className="font-medium text-sm">{(q.label as string) || `Q${idx + 1}`}</span>
          <span className="text-xs text-[var(--text-secondary)]">
            — {numChoices}択 {answer != null ? `(正解: ${answer + 1})` : ""}
          </span>
        </button>
        <button onClick={onRemove} className="text-xs text-[var(--danger)] hover:underline ml-4">
          削除
        </button>
      </div>

      {open && (
        <div className="mt-3 pt-3 border-t border-[var(--border)] grid grid-cols-2 sm:grid-cols-3 gap-3">
          <div>
            <label className="text-xs text-[var(--text-secondary)]">Label</label>
            <input
              type="text"
              value={(q.label as string) || ""}
              onChange={(e) => onUpdate({ label: e.target.value })}
              className="w-full text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-[var(--text-secondary)]">選択肢数</label>
            <input
              type="number"
              min={2}
              max={15}
              value={numChoices}
              onChange={(e) => onUpdate({ num_choices: Number(e.target.value) })}
              className="w-full text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-[var(--text-secondary)]">正解 (0-based)</label>
            <input
              type="number"
              min={0}
              value={answer ?? ""}
              onChange={(e) => onUpdate({ answer: e.target.value ? Number(e.target.value) : null })}
              className="w-full text-sm"
            />
          </div>
        </div>
      )}
    </div>
  );
}
