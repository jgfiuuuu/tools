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

export interface SessionMetadata {
  source_statuses?: Record<string, string>;
  skipped_sources?: string[];
  degradation_notices?: string[];
  frontier_mode?: boolean;
  frontier_reason?: string | null;
  metrics?: SessionMetrics;
  source_contributions?: Record<string, SourceContribution>;
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
