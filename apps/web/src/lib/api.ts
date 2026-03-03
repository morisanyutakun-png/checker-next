/**
 * API client – centralised fetch wrapper.
 * All API calls go through Next.js rewrites → /api/* → FastAPI.
 */

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BASE}${path}`;
  const res = await fetch(url, {
    ...init,
    headers: {
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

/* ─── Config ────────────────────────────────────────────────── */

export interface SubjectData {
  id?: number;
  name: string;
  sort_order?: number;
  sheet_template?: string;
  questions: Record<string, unknown>[];
  extra?: Record<string, unknown>;
  layout?: {
    cols?: number;
    row_height?: number;
    header_offset_mm?: number;
    bubble_rx?: number;
    bubble_ry?: number;
    label_width?: number;
    col_gap?: number;
  };
  [key: string]: unknown;
}

export interface ConfigData {
  threshold: number;
  subjects: SubjectData[];
}

export async function getConfig(): Promise<ConfigData> {
  return request<ConfigData>("/api/config");
}

export async function saveConfig(data: ConfigData): Promise<ConfigData> {
  return request<ConfigData>("/api/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

/* ─── Sheets ────────────────────────────────────────────────── */

export interface GenerateResult {
  success: boolean;
  pdf_url?: string;
  meta_url?: string;
  error?: string;
  logs?: string;
}

export async function generatePdf(
  subjectIdx: number,
  params: { name?: string; exam_number?: string } = {}
): Promise<GenerateResult> {
  const qs = new URLSearchParams();
  if (params.name) qs.set("name", params.name);
  if (params.exam_number) qs.set("exam_number", params.exam_number);
  return request<GenerateResult>(`/api/sheets/${subjectIdx}/generate?${qs}`);
}

/* ─── Upload ────────────────────────────────────────────────── */

export interface UploadResult {
  result: {
    pages: PageResult[];
    score: { correct: number; total: number };
  };
  csv_data: string;
  subject?: string;
  saved_score_id?: string;
  gen_debug?: Record<string, unknown>;
}

export interface PageResult {
  questions: QuestionResult[];
  omr_offsets_debug?: Record<string, unknown>;
}

export interface QuestionResult {
  label?: string;
  id?: string;
  selected_index?: number | null;
  selected_score?: number;
  correct?: boolean;
  answer?: number | null;
  choices: ChoiceResult[];
}

export interface ChoiceResult {
  index: number;
  label?: string;
  score: number;
  dark_pixels?: number;
  total_pixels?: number;
  bbox_px?: number[];
  thumb_b64?: string;
}

export async function uploadPdf(formData: FormData): Promise<UploadResult> {
  const url = `${BASE}/api/upload`;
  const res = await fetch(url, { method: "POST", body: formData });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json();
}

/* ─── Scores ────────────────────────────────────────────────── */

export interface ScoreEntry {
  id: string;
  subject_name?: string;
  timestamp?: string;
  created_at?: string;
}

export interface ScoreDetail {
  id: string;
  subject_name?: string;
  result: {
    pages: PageResult[];
    score: { correct: number; total: number };
  };
  gen_debug?: Record<string, unknown>;
  created_at?: string;
}

export async function getScores(): Promise<ScoreEntry[]> {
  return request<ScoreEntry[]>("/api/scores");
}

export async function getScore(id: string): Promise<ScoreDetail> {
  return request<ScoreDetail>(`/api/scores/${id}`);
}

export function annotatedPageUrl(scoreId: string, pageIdx: number): string {
  return `${BASE}/api/scores/${scoreId}/annotated/${pageIdx}`;
}

export function generatedPdfUrl(gid: string): string {
  return `${BASE}/api/generated/${gid}/pdf`;
}
