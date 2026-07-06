const baseURL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export interface ScholarlyPaper {
  id: string;
  title: string;
  abstract: string;
  year: number | null;
  authors: string[];
  venue: string | null;
  doi: string | null;
  arxiv_id: string | null;
  semantic_scholar_id: string | null;
  openalex_id: string | null;
  url: string | null;
  pdf_url: string | null;
  source: string | null;
  citation_count: number;
  rank: number;
  selected: boolean;
  relevance_score: number;
  novelty_score: number;
  final_score: number;
  relevance_label: string;
  ai_reason: string;
  query_matches: QueryMatch[];
  user_status: string;
  tags: string[];
  fulltext_source: string | null;
  fulltext_status: string;
  fulltext_original_filename: string | null;
  fulltext_text_char_count: number;
  fulltext_updated_at: string | null;
}

export interface QueryMatch {
  subtask_id: string;
  concept: string;
  intent: string;
  query_type: string;
  query_text: string;
  source: string;
  frontier_expansion?: string | null;
  parent_subtask_id?: string | null;
}

export interface ResearchQueryVariant {
  query_id: string;
  query_type: string;
  query_text: string;
  result_count: number;
  status: string;
  frontier_expansion?: string | null;
  parent_subtask_id?: string | null;
  sources_attempted?: string[];
  sources_succeeded?: string[];
  sources_failed?: Array<{ source: string; reason: string }>;
  sources_skipped?: Array<{ source: string; reason: string }>;
}

export interface ResearchQueryTask {
  subtask_id: string;
  concept: string;
  intent: string;
  base_terms: string[];
  query_types: string[];
  variants: ResearchQueryVariant[];
  result_count: number;
  status: string;
  frontier_expansion?: string | null;
  parent_subtask_id?: string | null;
}

export interface ResearchReport {
  id: string;
  session_id: string;
  content_markdown: string;
  created_at: string;
}

export type ReportFitTier = "core" | "adjacent_transfer" | "off_target";
export type ReportTone = "evidence" | "judgment" | "speculation" | "action" | "note";
export type ReportItemKind = "paragraph" | "bullet" | "ordered";

export interface ReportContext {
  session_id?: string;
  topic?: string;
  evidence_count?: number;
  evidence_limit?: number;
  evidence_limited?: boolean;
  year_range?: {
    start?: number | null;
    end?: number | null;
  };
  year_range_text?: string;
  main_sources?: Array<{ source: string; count: number }>;
  main_sources_text?: string;
  query_summary?: string;
  fulltext_count?: number;
  abstract_only_count?: number;
  uploaded_pdf_count?: number;
  evidence_mix?: Record<string, number>;
  topic_boundary?: string;
  topic_axes?: string[];
  synthesis_mode?: "llm" | "fallback" | string;
  evidence_bucket_counts?: Record<string, number>;
}

export interface ReportTaskArtifact {
  id: number;
  title: string;
  intent: string;
  summary: string;
  note_id?: string | null;
}

export interface ReportSupportingNote {
  id: string;
  title: string;
  type: string;
  created_at: string;
}

export interface ReportPaperCard {
  paper_id: string;
  title: string;
  year: number | null;
  source: string | null;
  evidence_level: string;
  fulltext_source: string;
  problem: string;
  setting: string;
  method: string;
  key_claims: string[];
  evidence: string[];
  datasets_metrics: string[];
  limitations: string[];
  open_questions: string[];
  source_excerpt_refs: string[];
  fit_tier: ReportFitTier;
  fit_reason: string;
  task_family: string;
  modality_family: string;
  conditioning_family: string;
  prediction_family: string;
}

export interface ReportEvidenceBuckets {
  core: string[];
  adjacent_transfer: string[];
  off_target: string[];
}

export interface ReportMemoItem {
  kind?: ReportItemKind;
  tone?: ReportTone;
  text: string;
  order?: string;
  evidence_paper_ids?: string[];
}

export interface ReportMemoEvidenceCard {
  paper_id: string;
  title: string;
  fit_tier: ReportFitTier;
  evidence_level: string;
  task_family: string;
  modality_family: string;
  conditioning_family: string;
  prediction_family: string;
  key_claims: string[];
  limitations: string[];
}

export interface ReportMemoSection {
  id: string;
  title: string;
  icon?: string;
  summary?: string;
  items: ReportMemoItem[];
  evidence_cards?: ReportMemoEvidenceCard[];
  appendix?: boolean;
}

export interface ReportReviewSection {
  id: string;
  title: string;
  icon?: string;
  summary?: string;
  narrative_paragraphs?: string[];
  insight_items?: ReportMemoItem[];
  evidence_cards?: ReportMemoEvidenceCard[];
  appendix?: boolean;
}

export interface ReportSectionGeneration {
  section_id: string;
  title?: string;
  mode: "llm" | "fallback" | string;
  appendix?: boolean;
}

export interface ReportArtifacts {
  tasks?: ReportTaskArtifact[];
  supporting_notes?: ReportSupportingNote[];
  paper_cards?: ReportPaperCard[];
  memo_sections?: ReportMemoSection[];
  review_sections?: ReportReviewSection[];
  section_generation?: ReportSectionGeneration[];
  evidence_buckets?: ReportEvidenceBuckets;
}

export interface SessionMetrics {
  raw_paper_count?: number;
  deduped_paper_count?: number;
  coarse_candidate_count?: number;
  final_candidate_count?: number;
  selected_count?: number;
  high_relevance_count?: number;
  strict_relevance_count?: number;
  average_top_coarse_score?: number;
  core_task_hits?: number;
  core_task_total?: number;
  direct_query_count?: number;
  direct_core_query_count?: number;
  frontier_query_count?: number;
  frontier_adjacent_query_count?: number;
  frontier_broader_query_count?: number;
  frontier_recent_query_count?: number;
  frontier_added_raw_count?: number;
  candidate_pool_purity?: number;
  candidate_drift_score?: number;
  direct_hit_coverage?: number;
  frontier_contribution_rate?: number;
  frontier_selected_count?: number;
  dedupe_ratio?: number;
}

export interface SourceContribution {
  status?: string;
  raw_hits?: number;
  deduped_hits?: number;
  top_pool_hits?: number;
  selected_hits?: number;
  direct_top_hits?: number;
  frontier_top_hits?: number;
}

export interface LlmUsageStage {
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
}

export interface LlmUsageSummary {
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  by_stage?: Record<string, LlmUsageStage>;
}

export interface SessionMetadata {
  source_statuses?: Record<string, string>;
  skipped_sources?: string[];
  degradation_notices?: string[];
  frontier_mode?: boolean;
  frontier_reason?: string | null;
  metrics?: SessionMetrics;
  source_contributions?: Record<string, SourceContribution>;
  llm_usage?: LlmUsageSummary;
  report_context?: ReportContext;
  report_artifacts?: ReportArtifacts;
  [key: string]: unknown;
}

export interface ResearchSession {
  id: string;
  topic: string;
  status: string;
  queries: Array<string | ResearchQueryTask>;
  metadata?: SessionMetadata;
  source_statuses: Record<string, string>;
  skipped_sources: string[];
  degradation_notices: string[];
  frontier_mode?: boolean;
  frontier_reason?: string | null;
  metrics?: SessionMetrics;
  parent_session_id: string | null;
  created_at: string;
  updated_at: string;
  paper_count: number;
  selected_count: number;
  report_count: number;
  papers?: ScholarlyPaper[];
  reports?: ResearchReport[];
}

export interface StreamEvent {
  type: string;
  [key: string]: unknown;
}

export interface StreamOptions {
  signal?: AbortSignal;
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${baseURL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers || {})
    }
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `请求失败，状态码：${response.status}`);
  }

  return (await response.json()) as T;
}

export async function streamRequest(
  path: string,
  payload: Record<string, unknown>,
  onEvent: (event: StreamEvent) => void,
  options: StreamOptions = {}
): Promise<void> {
  const response = await fetch(`${baseURL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream"
    },
    body: JSON.stringify(payload),
    signal: options.signal
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `流式请求失败，状态码：${response.status}`);
  }

  if (!response.body) {
    throw new Error("浏览器不支持流式响应");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const rawEvent = buffer.slice(0, boundary).trim();
      buffer = buffer.slice(boundary + 2);
      parseSseEvent(rawEvent, onEvent);
      boundary = buffer.indexOf("\n\n");
    }

    if (done) {
      if (buffer.trim()) {
        parseSseEvent(buffer.trim(), onEvent);
      }
      break;
    }
  }
}

function parseSseEvent(
  rawEvent: string,
  onEvent: (event: StreamEvent) => void
) {
  if (!rawEvent.startsWith("data:")) {
    return;
  }

  const dataPayload = rawEvent.slice(5).trim();
  if (!dataPayload) {
    return;
  }

  try {
    onEvent(JSON.parse(dataPayload) as StreamEvent);
  } catch (error) {
    console.error("解析流式事件失败：", error, dataPayload);
  }
}

export function listSessions(): Promise<ResearchSession[]> {
  return requestJson<ResearchSession[]>("/research/sessions");
}

export function getSession(sessionId: string): Promise<ResearchSession> {
  return requestJson<ResearchSession>(`/research/sessions/${sessionId}`);
}

export function deleteSession(sessionId: string): Promise<{ deleted: boolean; session_id: string }> {
  return requestJson<{ deleted: boolean; session_id: string }>(
    `/research/sessions/${sessionId}`,
    {
      method: "DELETE"
    }
  );
}

export function createSessionStream(
  topic: string,
  onEvent: (event: StreamEvent) => void,
  options: StreamOptions = {}
): Promise<void> {
  return streamRequest("/research/sessions/stream", { topic }, onEvent, options);
}

export function updateSessionPaper(
  sessionId: string,
  paperId: string,
  payload: {
    user_status?: string;
    selected?: boolean;
    tags?: string[];
  }
): Promise<ScholarlyPaper> {
  return requestJson<ScholarlyPaper>(
    `/research/sessions/${sessionId}/papers/${paperId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload)
    }
  );
}

export function uploadPaperPdf(
  sessionId: string,
  paperId: string,
  payload: {
    filename: string;
    content_base64: string;
  }
): Promise<ScholarlyPaper> {
  return requestJson<ScholarlyPaper>(
    `/research/sessions/${sessionId}/papers/${paperId}/pdf`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

export function resolvePaperFulltext(
  sessionId: string,
  paperId: string
): Promise<ScholarlyPaper> {
  return requestJson<ScholarlyPaper>(
    `/research/sessions/${sessionId}/papers/${paperId}/fulltext/resolve`,
    {
      method: "POST"
    }
  );
}

export function generateReportStream(
  sessionId: string,
  onEvent: (event: StreamEvent) => void,
  options: StreamOptions = {}
): Promise<void> {
  return streamRequest(
    `/research/sessions/${sessionId}/report/stream`,
    {},
    onEvent,
    options
  );
}

export function deriveSession(
  sessionId: string,
  topic: string
): Promise<ResearchSession> {
  return requestJson<ResearchSession>(`/research/sessions/${sessionId}/derive`, {
    method: "POST",
    body: JSON.stringify({ topic })
  });
}

export function exportUrl(sessionId: string, format: "md" | "bib"): string {
  return `${baseURL}/research/sessions/${sessionId}/export.${format}`;
}
