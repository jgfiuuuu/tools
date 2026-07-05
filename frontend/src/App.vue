<template>
  <main
    class="workspace"
    :class="{
      'left-collapsed': !leftSidebarOpen,
      'right-collapsed': !rightSidebarOpen
    }"
  >
    <aside class="left-rail">
      <div class="rail-top">
        <div class="brand-lockup" :class="{ compact: !leftSidebarOpen }">
          <div class="brand-mark">MM</div>
          <div v-if="leftSidebarOpen">
            <h1>文献妙妙屋</h1>
            <p class="brand-eyebrow">MIAOWEN LITERATURE WORKBENCH</p>
          </div>
        </div>
        <button
          class="rail-toggle left-handle"
          type="button"
          :aria-label="leftSidebarOpen ? '收起左侧栏' : '展开左侧栏'"
          @click="toggleLeftSidebar"
        >
          <span class="handle-dots" aria-hidden="true">
            <span></span>
            <span></span>
            <span></span>
          </span>
          <span
            class="handle-arrow"
            :class="{ collapsed: !leftSidebarOpen }"
            aria-hidden="true"
          ></span>
        </button>
      </div>

      <div v-if="leftSidebarOpen" class="rail-body">
        <form class="topic-form" @submit.prevent="startResearch">
          <div class="form-head">
            <p class="eyebrow">New Session</p>
            <h2>新建调研</h2>
          </div>
          <label>
            <span>研究问题</span>
            <textarea
              v-model="topicInput"
              rows="5"
              placeholder="例如：How do retrieval augmented language models improve code generation?"
            />
          </label>
          <div class="form-actions">
            <button
              class="primary-btn"
              type="submit"
              :disabled="creating || !topicInput.trim()"
            >
              {{ creating ? "检索中..." : "创建调研会话" }}
            </button>
            <button
              v-if="creating"
              class="ghost-btn"
              type="button"
              @click="cancelCurrentStream"
            >
              取消
            </button>
          </div>
        </form>

        <section class="side-block">
          <div class="section-title">
            <h2>历史会话</h2>
            <button class="text-btn" type="button" @click="loadSessions()">
              刷新
            </button>
          </div>
          <p v-if="!sessions.length" class="muted">暂无历史记录</p>
          <div v-else class="session-list">
            <article
              v-for="session in sessions"
              :key="session.id"
              class="session-item"
              :class="{ active: currentSession?.id === session.id }"
            >
              <button
                class="session-select"
                type="button"
                @click="loadSession(session.id)"
              >
                <div class="session-topline">
                  <h3>{{ session.topic }}</h3>
                  <span :class="['session-status', session.status]">
                    <span class="status-dot" aria-hidden="true"></span>
                    <span>{{ sessionStatusLabel(session.status) }}</span>
                  </span>
                </div>
                <p class="session-meta">
                  {{ session.selected_count }} / {{ session.paper_count }} 篇 ·
                  {{ formatDate(session.updated_at || session.created_at) }}
                </p>
              </button>
              <button
                class="session-delete"
                type="button"
                aria-label="删除历史会话"
                @click.stop="openDeleteDialog(session)"
              >
                <span aria-hidden="true">×</span>
              </button>
            </article>
          </div>
        </section>

        <section class="side-block">
          <div class="section-title">
            <h2>流程记录</h2>
            <div class="side-actions">
              <button
                v-if="progressLogs.length > 5"
                class="text-btn"
                type="button"
                @click="showAllLogs = !showAllLogs"
              >
                {{ showAllLogs ? "收起" : "全部" }}
              </button>
              <button class="text-btn" type="button" @click="progressLogs = []">
                清空
              </button>
            </div>
          </div>
          <ol v-if="visibleProgressLogs.length" class="progress-list">
            <li v-for="(log, index) in visibleProgressLogs" :key="`${log}-${index}`">
              {{ log }}
            </li>
          </ol>
          <p v-else class="muted">等待新的调研任务</p>
        </section>
      </div>
    </aside>

    <section class="center-stage">
      <header class="stage-header">
        <div class="stage-heading">
          <div class="stage-heading-top">
            <p class="eyebrow">Literature Focus</p>
            <span v-if="currentSession" class="status-pill subtle">
              {{ sessionStatusLabel(currentSession.status) }}
            </span>
          </div>
          <h2 :title="currentSession?.topic || ''">
            {{ currentSession?.topic || "请选择或创建一个调研会话" }}
          </h2>
          <div v-if="currentSession" class="stage-meta-stack">
            <p class="stage-meta-line">{{ currentSessionSummaryText }}</p>
          </div>
        </div>

        <div v-if="currentSession" class="stage-actions">
          <button
            class="primary-btn"
            type="button"
            :disabled="reporting || !confirmedCount"
            @click="generateReport"
          >
            {{ reporting ? "生成中..." : "生成研究报告" }}
          </button>
          <button class="secondary-btn" type="button" @click="openReportPanel">
            打开研究报告
          </button>
        </div>
      </header>

      <p v-if="error" class="banner error-banner">{{ error }}</p>

      <section v-if="currentSession" class="process-strip">
        <div class="process-summary" :title="currentSessionSourceText">
          <span class="process-label">Sources</span>
          <span class="process-text">{{ currentSessionSourceText }}</span>
        </div>

        <div
          v-if="frontierStatusText || candidatePoolText || sourceHealthText"
          class="session-summary-grid"
        >
          <article v-if="frontierStatusText" class="session-summary-card">
            <span class="session-summary-label">Frontier</span>
            <strong>{{ frontierStatusText }}</strong>
            <p class="muted">{{ frontierReasonText }}</p>
          </article>

          <article v-if="candidatePoolText" class="session-summary-card">
            <span class="session-summary-label">Candidates</span>
            <strong>{{ candidatePoolText }}</strong>
            <p class="muted">{{ candidatePoolDetailText }}</p>
          </article>

          <article v-if="sourceHealthText" class="session-summary-card">
            <span class="session-summary-label">Source Health</span>
            <strong>{{ sourceHealthText }}</strong>
            <p class="muted">{{ sourceHealthDetailText }}</p>
          </article>
        </div>

        <details v-if="degradationNotices.length" class="process-detail compact-banner warning-banner">
          <summary>
            <span class="process-detail-label">降级提示</span>
            <span class="process-detail-count">{{ degradationNotices.length }}</span>
          </summary>
          <ul>
            <li v-for="notice in degradationNotices" :key="notice">{{ notice }}</li>
          </ul>
        </details>

        <details
          v-if="queryTasks.length"
          class="process-detail query-board"
          :open="queryBoardOpen"
          @toggle="handleQueryBoardToggle"
        >
          <summary>
            <span class="process-detail-label">检索子任务</span>
            <span class="process-detail-count">{{ queryTasks.length }}</span>
          </summary>

          <div class="query-grid">
            <article v-for="task in queryTasks" :key="task.subtask_id" class="query-card">
              <div class="query-card-head">
                <div>
                  <h3>{{ task.concept }}</h3>
                  <p class="muted">{{ task.intent }}</p>
                </div>
                <span class="query-status">{{ queryStatusLabel(task.status) }}</span>
              </div>
              <div class="term-list">
                <span v-for="term in task.base_terms" :key="`${task.subtask_id}-${term}`">
                  {{ term }}
                </span>
              </div>
              <ul class="variant-list">
                <li v-for="variant in task.variants" :key="variant.query_id">
                  <div class="variant-head">
                    <strong>{{ queryTypeLabel(variant.query_type) }}</strong>
                    <span>{{ queryStatusLabel(variant.status) }} · {{ variant.result_count }} 条</span>
                  </div>
                  <code>{{ variant.query_text }}</code>
                  <p class="muted">
                    ✓ {{ formatSources(variant.sources_succeeded) }} ·
                    ⊘ {{ formatSourceReasons(variant.sources_skipped) }} ·
                    ✕ {{ formatSourceReasons(variant.sources_failed) }}
                  </p>
                </li>
              </ul>
            </article>
          </div>
        </details>
      </section>

      <section v-if="currentSession" class="filter-bar">
        <label class="search-control">
          <span>搜索</span>
          <input
            v-model="filters.keyword"
            type="search"
            placeholder="标题、摘要、作者"
          />
        </label>
        <label>
          <span>相关性</span>
          <select v-model="filters.label">
            <option value="">全部</option>
            <option value="must_read">核心</option>
            <option value="frontier">前沿</option>
            <option value="background">背景</option>
            <option value="adjacent">旁支</option>
            <option value="candidate">候选</option>
          </select>
        </label>
        <label>
          <span>状态</span>
          <select v-model="filters.status">
            <option value="">全部</option>
            <option value="included">已确认</option>
            <option value="to_read">待读</option>
            <option value="saved">收藏</option>
            <option value="candidate">候选</option>
            <option value="excluded">已排除</option>
          </select>
        </label>
        <label>
          <span>年份</span>
          <select v-model="filters.year">
            <option value="">全部</option>
            <option value="2025">2025+</option>
            <option value="2024">2024+</option>
            <option value="2022">2022+</option>
            <option value="2020">2020+</option>
          </select>
        </label>
      </section>

      <section class="paper-stage">
        <div class="section-title">
          <div>
            <h2>参考文献</h2>
            <p class="muted" v-if="currentSession">
              {{ filteredPapers.length }} / {{ papers.length }} 篇
            </p>
          </div>
        </div>

        <div v-if="currentSession && filteredPapers.length" class="paper-list">
          <article
            v-for="paper in filteredPapers"
            :key="paper.id"
            class="paper-row"
            :class="{
              active: activePaper?.id === paper.id,
              excluded: paper.user_status === 'excluded'
            }"
            @click="selectPaper(paper.id)"
          >
            <div class="paper-rank">{{ String(paper.rank).padStart(2, '0') }}</div>
            <div class="paper-main">
              <div class="paper-title-row">
                <h3>{{ paper.title }}</h3>
                <span class="paper-year">{{ paper.year || "n.d." }}</span>
              </div>
              <p class="paper-authors">{{ compactAuthors(paper.authors) }}</p>
              <div class="paper-tags">
                <span :class="['label-chip', paper.relevance_label]">
                  {{ relevanceLabel(paper.relevance_label) }}
                </span>
                <span v-for="tag in paper.tags" :key="`${paper.id}-${tag}`">
                  {{ tag }}
                </span>
                <span>{{ paper.source || "unknown" }}</span>
              </div>
              <p class="paper-summary">{{ paper.ai_reason }}</p>
            </div>
            <div class="paper-side" @click.stop>
              <button class="text-btn" type="button" @click="selectPaper(paper.id)">
                查看
              </button>
              <label class="toggle-select">
                <input
                  type="checkbox"
                  :checked="paper.selected && paper.user_status !== 'excluded'"
                  @change="togglePaperSelection(paper)"
                />
                纳入
              </label>
            </div>
          </article>
        </div>

        <div v-else-if="currentSession" class="empty-state">
          <p>当前筛选条件下没有文献。</p>
          <p class="muted">放宽年份、状态或关键词后再看一轮。</p>
        </div>

        <div v-else class="empty-state">
          <p>先创建一个调研会话。</p>
          <p class="muted">文献妙妙屋会把检索、筛选、精读和研究报告集中到同一工作台里。</p>
        </div>
      </section>
    </section>

    <aside class="right-rail">
      <div class="rail-top right-top">
        <div v-if="rightSidebarOpen" class="panel-switch">
          <button
            type="button"
            :class="{ active: rightPanelTab === 'detail' }"
            @click="showDetailTab"
          >
            文献详情
          </button>
          <button
            type="button"
            :class="{ active: rightPanelTab === 'report' }"
            @click="showReportTab"
          >
            研究报告
          </button>
        </div>
        <button
          class="rail-toggle right-handle"
          type="button"
          :aria-label="rightSidebarOpen ? '收起右侧栏' : '展开右侧栏'"
          @click="toggleRightSidebar"
        >
          <span class="handle-dots" aria-hidden="true">
            <span></span>
            <span></span>
            <span></span>
          </span>
          <span
            class="handle-arrow"
            :class="{ collapsed: !rightSidebarOpen }"
            aria-hidden="true"
          ></span>
        </button>
      </div>

      <div v-if="rightSidebarOpen" class="right-body">
        <section
          v-if="rightPanelTab === 'detail'"
          ref="detailScrollRef"
          class="panel-scroll"
        >
          <template v-if="activePaper">
            <div class="detail-hero">
              <div class="detail-heading">
                <div class="detail-heading-top">
                  <p class="eyebrow">Paper Detail</p>
                  <span class="score-pill">{{ Math.round(activePaper.final_score * 100) }}</span>
                </div>
                <h2>{{ activePaper.title }}</h2>
                <p class="detail-authors">{{ compactAuthors(activePaper.authors) }}</p>
                <div class="detail-meta-line">
                  <span>{{ activePaper.year || "n.d." }}</span>
                  <span>{{ activePaper.venue || "Unknown venue" }}</span>
                  <span>{{ activePaper.citation_count }} citations</span>
                  <span>{{ activePaper.source || "unknown" }}</span>
                </div>
              </div>
            </div>

            <div class="detail-actions">
              <a
                v-if="activePaperLink"
                class="primary-link"
                :href="activePaperLink"
                target="_blank"
                rel="noopener noreferrer"
              >
                打开论文
              </a>
              <a
                v-if="currentSession"
                class="secondary-link"
                :href="exportBibtexHref"
                target="_blank"
                rel="noopener noreferrer"
              >
                导出 BibTeX
              </a>
            </div>

            <div class="status-actions">
              <button
                type="button"
                :class="{ active: activePaper.user_status === 'included' }"
                @click="setPaperStatus(activePaper, 'included')"
              >
                确认
              </button>
              <button
                type="button"
                :class="{ active: activePaper.user_status === 'to_read' }"
                @click="setPaperStatus(activePaper, 'to_read')"
              >
                待读
              </button>
              <button
                type="button"
                :class="{ active: activePaper.user_status === 'saved' }"
                @click="setPaperStatus(activePaper, 'saved')"
              >
                收藏
              </button>
              <button
                type="button"
                :class="{ danger: activePaper.user_status === 'excluded' }"
                @click="setPaperStatus(activePaper, 'excluded')"
              >
                排除
              </button>
            </div>

            <section class="detail-block detail-block-primary">
              <div class="section-title detail-section-title">
                <h3>摘要</h3>
                <span :class="['label-chip', activePaper.relevance_label]">
                  {{ relevanceLabel(activePaper.relevance_label) }}
                </span>
              </div>
              <p class="reading-copy">
                {{ activePaper.abstract || "暂无摘要。请打开论文链接进一步确认。" }}
              </p>
              <div class="ai-note">
                <span class="ai-note-label">AI 判断</span>
                <p>{{ activePaper.ai_reason }}</p>
              </div>
            </section>

            <section class="detail-block detail-block-secondary">
              <div class="section-title detail-section-title">
                <h3>引用</h3>
              </div>
              <div class="cite-box">
                <p class="cite-text">{{ activePaperCitation }}</p>
                <div class="cite-actions">
                  <button class="text-btn" type="button" @click="copyCitation(activePaper)">
                    复制参考格式
                  </button>
                  <a
                    class="secondary-link"
                    :href="exportBibtexHref"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    BibTeX
                  </a>
                </div>
              </div>
            </section>

            <section v-if="activePaper.query_matches.length" class="detail-block">
              <div class="section-title detail-section-title">
                <h3>检索命中</h3>
              </div>
              <ul class="match-list">
                <li
                  v-for="match in activePaper.query_matches"
                  :key="`${activePaper.id}-${match.subtask_id}-${match.query_type}-${match.source}`"
                >
                  <strong>{{ match.concept }}</strong>
                  <span>{{ queryTypeLabel(match.query_type) }} · {{ match.source }}</span>
                  <code>{{ match.query_text }}</code>
                </li>
              </ul>
            </section>

            <form class="derive-form" @submit.prevent="deriveFromActivePaper">
              <label>
                <span>派生新会话</span>
                <input
                  v-model="deriveTopic"
                  type="text"
                  :placeholder="`围绕 ${activePaper.title.slice(0, 28)}... 继续深挖`"
                />
              </label>
              <button class="secondary-btn" type="submit" :disabled="!deriveTopic.trim()">
                派生
              </button>
            </form>
          </template>

          <div v-else class="empty-state inset">
            <p>选择一篇论文查看详情。</p>
            <p class="muted">右侧会显示摘要、引用、命中的检索子任务和派生入口。</p>
          </div>
        </section>

        <section
          v-else
          ref="reportScrollRef"
          class="panel-scroll"
        >
          <div class="report-hero">
            <div>
              <p class="eyebrow">Research Report</p>
              <h2>{{ reportHeading }}</h2>
              <p class="muted report-summary">基于当前已确认文献的研究备忘录</p>
            </div>
            <span v-if="confirmedCount" class="memo-badge">{{ confirmedCount }} 篇已确认</span>
          </div>

          <template v-if="reportSections.length">
            <nav class="report-toc">
              <button
                v-for="section in reportSections"
                :key="section.id"
                type="button"
                @click="scrollReportTo(section.id)"
              >
                {{ section.title }}
              </button>
            </nav>

            <article class="report-article">
              <section
                v-for="section in reportSections"
                :id="section.id"
                :key="section.id"
                :data-section-id="section.id"
                class="report-section"
              >
                <h3>{{ section.title }}</h3>
                <div class="report-items">
                  <div
                    v-for="(item, index) in section.items"
                    :key="`${section.id}-${index}`"
                    class="report-item"
                    :class="[item.kind, item.tone ?? 'plain']"
                  >
                    <span v-if="item.kind === 'ordered'" class="report-order">
                      {{ item.order }}
                    </span>
                    <span v-if="item.tone" class="tone-chip">
                      {{ reportToneLabel(item.tone) }}
                    </span>
                    <p>{{ item.text }}</p>
                  </div>
                </div>
              </section>
            </article>
          </template>

          <pre v-else-if="currentReportMarkdown" class="report-draft">{{ currentReportMarkdown }}</pre>

          <div v-else class="empty-state inset">
            <p>研究报告会基于已确认文献生成。</p>
            <p class="muted">先确认论文，再生成一版可供判断方向、空白和下一步动作的报告。</p>
          </div>
        </section>
      </div>
    </aside>

    <div
      v-if="deleteTargetSession"
      class="dialog-backdrop"
      @click.self="closeDeleteDialog"
    >
      <section class="dialog-panel">
        <p class="eyebrow">Delete Session</p>
        <h2>确认删除这个历史会话？</h2>
        <p class="dialog-copy">
          <strong>{{ deleteTargetSession.topic }}</strong>
          的论文选择、标签和报告记录都会一起删除，且无法恢复。
        </p>
        <div class="dialog-actions">
          <button class="ghost-btn" type="button" @click="closeDeleteDialog">
            取消
          </button>
          <button
            class="danger-btn"
            type="button"
            :disabled="deletingSessionId === deleteTargetSession.id"
            @click="confirmDeleteSession"
          >
            {{ deletingSessionId === deleteTargetSession.id ? "删除中..." : "确认删除" }}
          </button>
        </div>
      </section>
    </div>
  </main>
</template>

<script lang="ts" setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";

import {
  createSessionStream,
  deleteSession as deleteSessionRequest,
  deriveSession,
  exportUrl,
  generateReportStream,
  getSession,
  listSessions,
  updateSessionPaper,
  type ResearchQueryTask,
  type ResearchReport,
  type ResearchSession,
  type SessionMetadata,
  type SessionMetrics,
  type ScholarlyPaper,
  type StreamEvent
} from "./services/api";

type RightPanelTab = "detail" | "report";
type ReportTone = "evidence" | "judgment" | "speculation" | "action" | "note";
type ReportItemKind = "paragraph" | "bullet" | "ordered";

interface ReportItem {
  kind: ReportItemKind;
  text: string;
  order?: string;
  tone?: ReportTone;
}

interface ReportSection {
  id: string;
  title: string;
  items: ReportItem[];
}

const APP_TITLE = "文献妙妙屋";
const LEFT_PANEL_KEY = "miaowen:left-panel";
const RIGHT_PANEL_KEY = "miaowen:right-panel";
const QUERY_BOARD_KEY = "miaowen:query-board";

const sessions = ref<ResearchSession[]>([]);
const currentSession = ref<ResearchSession | null>(null);
const activePaperId = ref<string | null>(null);
const topicInput = ref("");
const deriveTopic = ref("");
const progressLogs = ref<string[]>([]);
const error = ref("");
const creating = ref(false);
const reporting = ref(false);
const reportText = ref("");
const showAllLogs = ref(false);
const leftSidebarOpen = ref(readStoredBoolean(LEFT_PANEL_KEY, true));
const rightSidebarOpen = ref(readStoredBoolean(RIGHT_PANEL_KEY, true));
const queryBoardOpen = ref(readStoredBoolean(QUERY_BOARD_KEY, false));
const rightPanelTab = ref<RightPanelTab>("detail");
const deleteTargetSession = ref<ResearchSession | null>(null);
const deletingSessionId = ref<string | null>(null);

const filters = reactive({
  keyword: "",
  label: "",
  status: "",
  year: ""
});

let currentController: AbortController | null = null;
const detailScrollRef = ref<HTMLElement | null>(null);
const reportScrollRef = ref<HTMLElement | null>(null);

const papers = computed(() => currentSession.value?.papers ?? []);
const latestReport = computed<ResearchReport | null>(
  () => currentSession.value?.reports?.[0] ?? null
);
const queryTasks = computed(() =>
  normalizeQueryTasks(currentSession.value?.queries ?? [])
);
const sessionMetadata = computed<SessionMetadata>(() =>
  normalizeSessionMetadata(currentSession.value?.metadata)
);
const sessionMetrics = computed<SessionMetrics>(() =>
  normalizeSessionMetrics(
    currentSession.value?.metrics ?? sessionMetadata.value.metrics
  )
);
const degradationNotices = computed(
  () => currentSession.value?.degradation_notices ?? []
);
const confirmedCount = computed(
  () =>
    papers.value.filter(
      (paper) => paper.selected && paper.user_status !== "excluded"
    ).length
);
const activePaper = computed(() => {
  if (!papers.value.length) {
    return null;
  }
  return (
    papers.value.find((paper) => paper.id === activePaperId.value) ??
    papers.value[0]
  );
});
const activePaperLink = computed(() =>
  activePaper.value ? resolvePaperLink(activePaper.value) : null
);
const activePaperCitation = computed(() =>
  activePaper.value ? buildCitationText(activePaper.value) : ""
);
const currentReportMarkdown = computed(
  () => reportText.value || latestReport.value?.content_markdown || ""
);
const parsedReport = computed(() => parseReportMarkdown(currentReportMarkdown.value));
const reportHeading = computed(() => parsedReport.value.title || "研究报告");
const reportSections = computed(() => parsedReport.value.sections);
const currentSessionSummaryText = computed(() => {
  if (!currentSession.value) {
    return "";
  }
  const parts = [
    `${confirmedCount.value} / ${currentSession.value.paper_count} 已纳入`,
    `${currentSession.value.report_count} 份报告`
  ];
  if (degradationNotices.value.length) {
    parts.push(`${degradationNotices.value.length} 项降级`);
  }
  return parts.join(" · ");
});
const currentSessionSourceText = computed(() => {
  if (!currentSession.value) {
    return "以文献筛选、精读和判断为中心，而不是一次性回答。";
  }
  const parts = Object.entries(currentSession.value.source_statuses ?? {}).map(
    ([source, status]) => `${source}=${status}`
  );
  if (!parts.length) {
    return "正在等待本次会话的检索与筛选元数据。";
  }
  return parts.join(" · ");
});

const frontierStatusText = computed(() => {
  if (!currentSession.value) {
    return "";
  }
  if (
    !["ready", "reported"].includes(currentSession.value.status) &&
    !sessionMetadata.value.frontier_mode &&
    !sessionMetrics.value.final_candidate_count
  ) {
    return "";
  }
  return sessionMetadata.value.frontier_mode ? "Triggered" : "Not triggered";
});

const frontierReasonText = computed(() => {
  if (!currentSession.value) {
    return "";
  }
  const metrics = sessionMetrics.value;
  const expansionMix = metrics.frontier_query_count
    ? `Queries: adj ${metrics.frontier_adjacent_query_count ?? 0} / recent ${metrics.frontier_recent_query_count ?? 0} / broader ${metrics.frontier_broader_query_count ?? 0}.`
    : "";
  const frontierSelected = metrics.frontier_selected_count
    ? `Selected frontier papers: ${metrics.frontier_selected_count}.`
    : "";
  if (sessionMetadata.value.frontier_mode) {
    return [formatFrontierReason(sessionMetadata.value.frontier_reason), expansionMix, frontierSelected]
      .filter(Boolean)
      .join(" ");
  }
  return [ "Direct high-relevance coverage was sufficient.", expansionMix ]
    .filter(Boolean)
    .join(" ");
});

const candidatePoolText = computed(() => {
  if (!currentSession.value) {
    return "";
  }
  const metrics = sessionMetrics.value;
  return [
    `raw ${metrics.raw_paper_count ?? 0}`,
    `deduped ${metrics.deduped_paper_count ?? 0}`,
    `final ${metrics.final_candidate_count ?? 0}`,
    `selected ${metrics.selected_count ?? 0}`
  ].join(" -> ");
});

const candidatePoolDetailText = computed(() => {
  if (!currentSession.value) {
    return "";
  }
  const metrics = sessionMetrics.value;
  const parts = [
    `queries direct ${metrics.direct_query_count ?? 0}`,
    metrics.frontier_query_count
      ? `frontier ${metrics.frontier_query_count}`
      : "",
    `purity ${formatPercent(metrics.candidate_pool_purity)}`,
    `drift ${formatPercent(metrics.candidate_drift_score)}`,
    `coverage ${formatPercent(metrics.direct_hit_coverage)}`,
    metrics.core_task_total
      ? `core hits ${metrics.core_task_hits ?? 0}/${metrics.core_task_total}`
      : "",
    metrics.dedupe_ratio !== undefined
      ? `dedupe ${formatPercent(metrics.dedupe_ratio)}`
      : ""
  ].filter(Boolean);
  return parts.join(" | ");
});

const sourceHealthText = computed(() => {
  if (!currentSession.value) {
    return "";
  }
  const statuses = Object.values(currentSession.value.source_statuses ?? {});
  if (!statuses.length) {
    return "";
  }
  const healthy = statuses.filter((status) => status === "ok").length;
  const degraded = statuses.filter((status) =>
    ["failed", "partial_failure"].includes(status)
  ).length;
  const skipped = statuses.filter((status) => status.startsWith("skipped")).length;
  return `healthy ${healthy} | degraded ${degraded} | skipped ${skipped}`;
});

const sourceHealthDetailText = computed(() => {
  if (!currentSession.value) {
    return "";
  }
  const contributions = Object.entries(
    sessionMetadata.value.source_contributions ?? {}
  )
    .sort((left, right) => {
      const leftScore =
        (left[1]?.selected_hits ?? 0) * 10 + (left[1]?.top_pool_hits ?? 0);
      const rightScore =
        (right[1]?.selected_hits ?? 0) * 10 + (right[1]?.top_pool_hits ?? 0);
      return rightScore - leftScore;
    })
    .slice(0, 3)
    .map(
      ([source, payload]) =>
        `${source} ${payload.top_pool_hits ?? 0}/${payload.selected_hits ?? 0}`
    );
  if (currentSession.value.skipped_sources.length && contributions.length) {
    return `${contributions.join(" | ")} | Skipped: ${currentSession.value.skipped_sources.join(", ")}`;
  }
  if (contributions.length) {
    return `Top contributors top/selected: ${contributions.join(" | ")}`;
  }
  if (currentSession.value.skipped_sources.length) {
    return `Skipped: ${currentSession.value.skipped_sources.join(", ")}`;
  }
  return "Session detail metadata is available for all active sources.";
});

const filteredPapers = computed(() => {
  const keyword = filters.keyword.trim().toLowerCase();
  const minYear = filters.year ? Number(filters.year) : null;

  return papers.value.filter((paper) => {
    if (filters.label && paper.relevance_label !== filters.label) {
      return false;
    }
    if (filters.status && paper.user_status !== filters.status) {
      return false;
    }
    if (minYear && (!paper.year || paper.year < minYear)) {
      return false;
    }
    if (keyword) {
      const haystack = [
        paper.title,
        paper.abstract,
        paper.ai_reason,
        paper.authors.join(" ")
      ]
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(keyword)) {
        return false;
      }
    }
    return true;
  });
});
const visibleProgressLogs = computed(() =>
  showAllLogs.value ? progressLogs.value : progressLogs.value.slice(-5)
);

const exportBibtexHref = computed(() =>
  currentSession.value ? exportUrl(currentSession.value.id, "bib") : "#"
);

watch(leftSidebarOpen, (value) => persistBoolean(LEFT_PANEL_KEY, value));
watch(rightSidebarOpen, (value) => persistBoolean(RIGHT_PANEL_KEY, value));
watch(queryBoardOpen, (value) => persistBoolean(QUERY_BOARD_KEY, value));
watch(
  currentSession,
  (session) => {
    if (typeof document !== "undefined") {
      document.title = session ? `${session.topic} · ${APP_TITLE}` : APP_TITLE;
    }
  },
  { immediate: true }
);

onMounted(async () => {
  await loadSessions();
});

onBeforeUnmount(() => {
  cancelCurrentStream();
});

async function loadSessions(preferredSessionId: string | null = currentSession.value?.id ?? null) {
  try {
    error.value = "";
    const nextSessions = await listSessions();
    sessions.value = nextSessions;

    const targetId =
      preferredSessionId && nextSessions.some((session) => session.id === preferredSessionId)
        ? preferredSessionId
        : nextSessions[0]?.id ?? null;

    if (!targetId) {
      currentSession.value = null;
      activePaperId.value = null;
      reportText.value = "";
      rightPanelTab.value = "detail";
      return;
    }

    if (!currentSession.value || currentSession.value.id !== targetId) {
      await loadSession(targetId, { quiet: true });
      return;
    }

    const summary = nextSessions.find((session) => session.id === targetId);
    if (summary && currentSession.value) {
      currentSession.value = normalizeSession({
        ...summary,
        papers: currentSession.value.papers,
        reports: currentSession.value.reports
      });
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "无法加载历史会话";
  }
}

async function loadSession(sessionId: string, options: { quiet?: boolean } = {}) {
  try {
    error.value = "";
    const detail = await getSession(sessionId);
    applySession(detail);
    if (!options.quiet) {
      pushLog(`已加载历史会话：${detail.topic}`);
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "无法加载会话";
  }
}

async function startResearch() {
  if (!topicInput.value.trim()) {
    return;
  }

  cancelCurrentStream();
  const controller = new AbortController();
  currentController = controller;
  creating.value = true;
  error.value = "";
  reportText.value = "";
  rightSidebarOpen.value = true;
  rightPanelTab.value = "detail";
  progressLogs.value = [];
  showAllLogs.value = false;
  pushLog(`创建调研会话：${topicInput.value.trim()}`);

  try {
    await createSessionStream(topicInput.value.trim(), handleSessionEvent, {
      signal: controller.signal
    });
    await loadSessions(currentSession.value?.id ?? null);
  } catch (err) {
    if (!(err instanceof DOMException && err.name === "AbortError")) {
      error.value = err instanceof Error ? err.message : "创建会话失败";
    }
  } finally {
    creating.value = false;
    if (currentController === controller) {
      currentController = null;
    }
  }
}

function handleSessionEvent(event: StreamEvent) {
  if (event.type === "session_created") {
    applySession(event.session as ResearchSession);
    pushLog("会话已创建");
    return;
  }

  if (event.type === "query_plan_generated" || event.type === "query_generated") {
    const queries = Array.isArray(event.queries) ? event.queries : [];
    if (currentSession.value) {
      currentSession.value.queries = queries as Array<string | ResearchQueryTask>;
    }
    pushLog(`已生成 ${queries.length} 组检索式`);
    return;
  }

  if (event.type === "source_skipped") {
    if (
      currentSession.value &&
      typeof event.source === "string" &&
      typeof event.reason === "string"
    ) {
      currentSession.value.source_statuses[event.source] = event.reason;
      if (!currentSession.value.skipped_sources.includes(event.source)) {
        currentSession.value.skipped_sources.push(event.source);
      }
      const notice = `${event.source} 已跳过：${event.reason}`;
      if (!currentSession.value.degradation_notices.includes(notice)) {
        currentSession.value.degradation_notices.push(notice);
      }
    }
    pushLog(`已跳过数据源：${String(event.source ?? "unknown")}`);
    return;
  }

  if (event.type === "source_failed") {
    if (
      currentSession.value &&
      typeof event.source === "string" &&
      typeof event.reason === "string"
    ) {
      currentSession.value.source_statuses[event.source] = event.reason;
      const notice = `${event.source} 已降级：${event.reason}`;
      if (!currentSession.value.degradation_notices.includes(notice)) {
        currentSession.value.degradation_notices.push(notice);
      }
    }
    pushLog(`数据源降级：${String(event.source ?? "unknown")}`);
    return;
  }

  if (event.type === "status" && typeof event.message === "string") {
    pushLog(event.message);
    return;
  }

  if (event.type === "papers_recalled") {
    pushLog(`已召回 ${event.count ?? 0} 篇候选论文`);
    return;
  }

  if (event.type === "subtask_completed") {
    const subtask = event.subtask as ResearchQueryTask | undefined;
    if (subtask) {
      mergeQueryTask(subtask);
      pushLog(`完成子任务：${subtask.concept}`);
    }
    return;
  }

  if (event.type === "paper_ranked") {
    const paper = event.paper as Partial<ScholarlyPaper> | undefined;
    if (paper?.title) {
      pushLog(`筛选：${paper.title}`);
    }
    return;
  }

  if (event.type === "screening_done") {
    applySession(event.session as ResearchSession);
    pushLog("筛选完成，已进入工作台");
    return;
  }

  if (event.type === "error") {
    error.value = typeof event.detail === "string" ? event.detail : "流程失败";
  }
}

function applySession(session: ResearchSession) {
  const normalized = normalizeSession(session);
  currentSession.value = normalized;
  const hasActivePaper = normalized.papers?.some((paper) => paper.id === activePaperId.value);
  activePaperId.value = hasActivePaper
    ? activePaperId.value
    : normalized.papers?.[0]?.id ?? null;
  reportText.value = normalized.reports?.[0]?.content_markdown ?? reportText.value;
  syncSessionListSummary();
  if (rightPanelTab.value === "detail") {
    scrollRightPanelToTop("detail");
  }
}

function selectPaper(paperId: string) {
  activePaperId.value = paperId;
  rightSidebarOpen.value = true;
  rightPanelTab.value = "detail";
  scrollRightPanelToTop("detail");
}

async function togglePaperSelection(paper: ScholarlyPaper) {
  const selected = !(paper.selected && paper.user_status !== "excluded");
  await patchPaper(paper, {
    selected,
    user_status: selected ? "included" : "candidate"
  });
}

async function setPaperStatus(paper: ScholarlyPaper, status: string) {
  await patchPaper(paper, { user_status: status });
}

async function patchPaper(
  paper: ScholarlyPaper,
  payload: { user_status?: string; selected?: boolean; tags?: string[] }
) {
  if (!currentSession.value) {
    return;
  }

  try {
    const updated = await updateSessionPaper(currentSession.value.id, paper.id, payload);
    const index = papers.value.findIndex((item) => item.id === updated.id);
    if (index >= 0 && currentSession.value.papers) {
      currentSession.value.papers[index] = normalizePaper(updated);
      syncCurrentSessionCounters();
      syncSessionListSummary();
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "更新论文状态失败";
  }
}

async function generateReport() {
  if (!currentSession.value) {
    return;
  }

  const sessionId = currentSession.value.id;
  reporting.value = true;
  error.value = "";
  reportText.value = "";
  rightSidebarOpen.value = true;
  rightPanelTab.value = "report";
  scrollRightPanelToTop("report");
  pushLog("开始生成研究报告");

  try {
    await generateReportStream(sessionId, handleReportEvent);
    const detail = await getSession(sessionId);
    applySession(detail);
    await loadSessions(sessionId);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "生成报告失败";
  } finally {
    reporting.value = false;
  }
}

function handleReportEvent(event: StreamEvent) {
  if (event.type === "report_chunk" && typeof event.content === "string") {
    reportText.value += event.content;
  }
  if (event.type === "report_done") {
    pushLog("研究报告已保存");
  }
  if (event.type === "error") {
    error.value = typeof event.detail === "string" ? event.detail : "生成报告失败";
  }
}

async function deriveFromActivePaper() {
  if (!currentSession.value || !deriveTopic.value.trim()) {
    return;
  }

  try {
    const child = await deriveSession(currentSession.value.id, deriveTopic.value.trim());
    pushLog(`已派生新会话：${child.topic}`);
    deriveTopic.value = "";
    await loadSessions(child.id);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "派生会话失败";
  }
}

function openReportPanel() {
  rightSidebarOpen.value = true;
  rightPanelTab.value = "report";
  scrollRightPanelToTop("report");
}

function showDetailTab() {
  rightPanelTab.value = "detail";
  scrollRightPanelToTop("detail");
}

function showReportTab() {
  rightPanelTab.value = "report";
  scrollRightPanelToTop("report");
}

function toggleLeftSidebar() {
  leftSidebarOpen.value = !leftSidebarOpen.value;
}

function toggleRightSidebar() {
  rightSidebarOpen.value = !rightSidebarOpen.value;
}

function handleQueryBoardToggle(event: Event) {
  queryBoardOpen.value = (event.currentTarget as HTMLDetailsElement).open;
}

function cancelCurrentStream() {
  if (currentController) {
    currentController.abort();
    currentController = null;
  }
}

function openDeleteDialog(session: ResearchSession) {
  deleteTargetSession.value = session;
}

function closeDeleteDialog() {
  if (deletingSessionId.value) {
    return;
  }
  deleteTargetSession.value = null;
}

async function confirmDeleteSession() {
  if (!deleteTargetSession.value) {
    return;
  }

  const session = deleteTargetSession.value;
  deletingSessionId.value = session.id;

  try {
    await deleteSessionRequest(session.id);
    const wasCurrent = currentSession.value?.id === session.id;
    pushLog(`已删除历史会话：${session.topic}`);
    deleteTargetSession.value = null;
    await loadSessions(wasCurrent ? null : currentSession.value?.id ?? null);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "删除会话失败";
  } finally {
    deletingSessionId.value = null;
  }
}

async function copyCitation(paper: ScholarlyPaper) {
  try {
    await copyText(buildCitationText(paper));
    pushLog(`已复制引用：${paper.title}`);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "复制引用失败";
  }
}

function scrollReportTo(sectionId: string) {
  const container = reportScrollRef.value;
  if (!container) {
    return;
  }
  const target = container.querySelector<HTMLElement>(
    `[data-section-id="${sectionId}"]`
  );
  if (target) {
    container.scrollTo({ top: target.offsetTop - 12, behavior: "smooth" });
  }
}

function pushLog(message: string) {
  progressLogs.value = [...progressLogs.value.slice(-79), message];
}

function scrollRightPanelToTop(tab: RightPanelTab) {
  void nextTick(() => {
    const container = tab === "detail" ? detailScrollRef.value : reportScrollRef.value;
    container?.scrollTo({ top: 0, behavior: "auto" });
  });
}

function syncCurrentSessionCounters() {
  if (!currentSession.value) {
    return;
  }
  currentSession.value.paper_count = currentSession.value.papers?.length ?? 0;
  currentSession.value.selected_count = confirmedCount.value;
  currentSession.value.report_count = currentSession.value.reports?.length ?? currentSession.value.report_count;
}

function syncSessionListSummary() {
  if (!currentSession.value) {
    return;
  }
  const index = sessions.value.findIndex((session) => session.id === currentSession.value?.id);
  if (index < 0) {
    return;
  }
  sessions.value[index] = {
    ...sessions.value[index],
    paper_count: currentSession.value.paper_count,
    selected_count: currentSession.value.selected_count,
    report_count: currentSession.value.report_count,
    status: currentSession.value.status,
    updated_at: currentSession.value.updated_at
  };
}

function compactAuthors(authors: string[]) {
  if (!authors.length) {
    return "Unknown authors";
  }
  if (authors.length <= 3) {
    return authors.join(", ");
  }
  return `${authors.slice(0, 3).join(", ")} et al.`;
}

function resolvePaperLink(paper: ScholarlyPaper) {
  if (paper.url) {
    return paper.url;
  }
  if (paper.doi) {
    return `https://doi.org/${paper.doi}`;
  }
  return paper.pdf_url;
}

function buildCitationText(paper: ScholarlyPaper) {
  const authors = paper.authors.length ? compactAuthors(paper.authors) : "Unknown authors";
  const year = paper.year || "n.d.";
  const venue = paper.venue ? ` ${paper.venue}.` : "";
  const doi = paper.doi ? ` DOI: ${paper.doi}.` : "";
  return `${authors} (${year}). ${paper.title}.${venue}${doi}`.trim();
}

async function copyText(value: string) {
  if (!value) {
    throw new Error("没有可复制的内容");
  }
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  throw new Error("当前环境不支持剪贴板写入");
}

function normalizeSession(session: ResearchSession): ResearchSession {
  const metadata = normalizeSessionMetadata(session.metadata);
  return {
    ...session,
    metadata,
    queries: Array.isArray(session.queries) ? session.queries : [],
    source_statuses: session.source_statuses ?? metadata.source_statuses ?? {},
    skipped_sources: session.skipped_sources ?? metadata.skipped_sources ?? [],
    degradation_notices:
      session.degradation_notices ?? metadata.degradation_notices ?? [],
    frontier_mode: session.frontier_mode ?? metadata.frontier_mode ?? false,
    frontier_reason: session.frontier_reason ?? metadata.frontier_reason ?? null,
    metrics: normalizeSessionMetrics(session.metrics ?? metadata.metrics),
    papers: (session.papers ?? []).map(normalizePaper),
    reports: session.reports ?? []
  };
}

function normalizePaper(paper: ScholarlyPaper): ScholarlyPaper {
  return {
    ...paper,
    authors: Array.isArray(paper.authors) ? paper.authors : [],
    tags: Array.isArray(paper.tags) ? paper.tags : [],
    query_matches: Array.isArray(paper.query_matches)
      ? paper.query_matches.map((match) => ({
          ...match,
          frontier_expansion:
            typeof match.frontier_expansion === "string"
              ? match.frontier_expansion
              : null,
          parent_subtask_id:
            typeof match.parent_subtask_id === "string"
              ? match.parent_subtask_id
              : null
        }))
      : []
  };
}

function normalizeQueryTasks(queries: Array<string | ResearchQueryTask>): ResearchQueryTask[] {
  return queries.map((item, index) => {
    if (typeof item === "string") {
      return {
        subtask_id: `legacy_${index}`,
        concept: `检索式 ${index + 1}`,
        intent: "旧格式检索式",
        base_terms: [item],
        query_types: ["core"],
        result_count: 0,
        status: "ok",
        variants: [
          {
            query_id: `legacy_${index}_core`,
            query_type: "core",
            query_text: item,
            result_count: 0,
            status: "ok",
            frontier_expansion: null,
            parent_subtask_id: null
          }
        ],
        frontier_expansion: null,
        parent_subtask_id: null
      };
    }
    return {
      ...item,
      base_terms: Array.isArray(item.base_terms) ? item.base_terms : [],
      query_types: Array.isArray(item.query_types) ? item.query_types : [],
      result_count: typeof item.result_count === "number" ? item.result_count : 0,
      status: typeof item.status === "string" ? item.status : "pending",
      frontier_expansion:
        typeof item.frontier_expansion === "string"
          ? item.frontier_expansion
          : null,
      parent_subtask_id:
        typeof item.parent_subtask_id === "string"
          ? item.parent_subtask_id
          : null,
      variants: Array.isArray(item.variants)
        ? item.variants.map((variant, variantIndex) => ({
            ...variant,
            query_id:
              typeof variant.query_id === "string"
                ? variant.query_id
                : `${item.subtask_id}_${variantIndex}`,
            query_type:
              typeof variant.query_type === "string" ? variant.query_type : "core",
            query_text:
              typeof variant.query_text === "string" ? variant.query_text : "",
            result_count:
              typeof variant.result_count === "number" ? variant.result_count : 0,
            status: typeof variant.status === "string" ? variant.status : "pending",
            frontier_expansion:
              typeof variant.frontier_expansion === "string"
                ? variant.frontier_expansion
                : typeof item.frontier_expansion === "string"
                  ? item.frontier_expansion
                  : null,
            parent_subtask_id:
              typeof variant.parent_subtask_id === "string"
                ? variant.parent_subtask_id
                : typeof item.parent_subtask_id === "string"
                  ? item.parent_subtask_id
                  : null
          }))
        : []
    };
  });
}

function normalizeSessionMetadata(
  metadata: SessionMetadata | undefined
): SessionMetadata {
  return {
    ...(metadata ?? {}),
    source_statuses:
      metadata?.source_statuses && typeof metadata.source_statuses === "object"
        ? metadata.source_statuses
        : {},
    skipped_sources: Array.isArray(metadata?.skipped_sources)
      ? metadata.skipped_sources
      : [],
    degradation_notices: Array.isArray(metadata?.degradation_notices)
      ? metadata.degradation_notices
      : [],
    frontier_mode: Boolean(metadata?.frontier_mode),
    frontier_reason:
      typeof metadata?.frontier_reason === "string"
        ? metadata.frontier_reason
        : null,
    metrics: normalizeSessionMetrics(metadata?.metrics),
    source_contributions:
      metadata?.source_contributions &&
      typeof metadata.source_contributions === "object"
        ? metadata.source_contributions
        : {}
  };
}

function normalizeSessionMetrics(
  metrics: SessionMetrics | undefined
): SessionMetrics {
  return {
    raw_paper_count: 0,
    deduped_paper_count: 0,
    coarse_candidate_count: 0,
    final_candidate_count: 0,
    selected_count: 0,
    high_relevance_count: 0,
    strict_relevance_count: 0,
    average_top_coarse_score: 0,
    core_task_hits: 0,
    core_task_total: 0,
    direct_query_count: 0,
    direct_core_query_count: 0,
    frontier_query_count: 0,
    frontier_adjacent_query_count: 0,
    frontier_broader_query_count: 0,
    frontier_recent_query_count: 0,
    frontier_added_raw_count: 0,
    candidate_pool_purity: 0,
    candidate_drift_score: 0,
    direct_hit_coverage: 0,
    frontier_contribution_rate: 0,
    frontier_selected_count: 0,
    dedupe_ratio: 0,
    ...(metrics ?? {})
  };
}

function formatPercent(value: number | undefined) {
  const ratio = typeof value === "number" ? value : 0;
  return `${Math.round(ratio * 100)}%`;
}

function formatFrontierReason(reason: string | null | undefined) {
  if (!reason) {
    return "Fallback expanded the query frontier for sparse direct matches.";
  }
  const mapping: Record<string, string> = {
    high_relevance_sparse: "High-relevance direct hits were sparse.",
    low_average_coarse_score: "Average coarse score stayed low.",
    weak_core_query_hits: "Core query coverage was weak.",
    empty_candidate_pool: "The direct candidate pool was empty."
  };
  return reason
    .split(",")
    .map((item) => mapping[item.trim()] || item.trim())
    .join(" ");
}

function mergeQueryTask(subtask: ResearchQueryTask) {
  if (!currentSession.value) {
    return;
  }
  const queries = [...queryTasks.value];
  const index = queries.findIndex((item) => item.subtask_id === subtask.subtask_id);
  if (index >= 0) {
    queries[index] = subtask;
  } else {
    queries.push(subtask);
  }
  currentSession.value.queries = queries;
}

function parseReportMarkdown(markdown: string): { title: string; sections: ReportSection[] } {
  if (!markdown.trim()) {
    return { title: "", sections: [] };
  }

  const lines = markdown.split(/\r?\n/);
  const sections: ReportSection[] = [];
  let title = "";
  let currentSection: ReportSection | null = null;

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      continue;
    }
    if (line.startsWith("# ")) {
      title = line.slice(2).trim();
      continue;
    }
    if (line.startsWith("## ")) {
      const heading = line.slice(3).trim();
      currentSection = {
        id: makeSectionId(heading, sections.length),
        title: heading,
        items: []
      };
      sections.push(currentSection);
      continue;
    }
    if (!currentSection) {
      continue;
    }
    const orderedMatch = line.match(/^(\d+)\.\s+(.*)$/);
    if (orderedMatch) {
      currentSection.items.push({
        kind: "ordered",
        order: orderedMatch[1],
        text: orderedMatch[2]
      });
      continue;
    }
    if (line.startsWith("- ")) {
      currentSection.items.push(parseReportBullet(line.slice(2)));
      continue;
    }
    currentSection.items.push({
      kind: "paragraph",
      text: line
    });
  }

  return { title, sections };
}

function parseReportBullet(text: string): ReportItem {
  const toneMap: Array<{ prefix: string; tone: ReportTone }> = [
    { prefix: "证据：", tone: "evidence" },
    { prefix: "判断：", tone: "judgment" },
    { prefix: "推测：", tone: "speculation" },
    { prefix: "行动：", tone: "action" },
    { prefix: "说明：", tone: "note" }
  ];

  for (const entry of toneMap) {
    if (text.startsWith(entry.prefix)) {
      return {
        kind: "bullet",
        tone: entry.tone,
        text: text.slice(entry.prefix.length).trim()
      };
    }
  }

  return {
    kind: "bullet",
    text
  };
}

function makeSectionId(title: string, index: number) {
  const normalized = title
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fff]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return normalized ? `report-${normalized}-${index}` : `report-section-${index}`;
}

function queryTypeLabel(queryType: string) {
  const labels: Record<string, string> = {
    core: "核心",
    survey: "综述",
    recent: "前沿",
    benchmark: "评测"
  };
  return labels[queryType] ?? queryType;
}

function queryStatusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: "等待",
    ok: "成功",
    partial: "部分成功",
    failed: "失败",
    skipped: "跳过",
    idle: "空闲",
    empty: "空"
  };
  return labels[status] ?? status;
}

function reportToneLabel(tone: ReportTone) {
  const labels: Record<ReportTone, string> = {
    evidence: "证据",
    judgment: "判断",
    speculation: "推测",
    action: "行动",
    note: "说明"
  };
  return labels[tone];
}

function formatSources(sources: string[] | undefined) {
  return sources && sources.length ? sources.join(", ") : "无";
}

function formatSourceReasons(items: Array<{ source: string; reason: string }> | undefined) {
  if (!items || !items.length) {
    return "无";
  }
  return items.map((item) => `${item.source}(${item.reason})`).join(", ");
}

function relevanceLabel(label: string) {
  const labels: Record<string, string> = {
    must_read: "核心",
    frontier: "前沿",
    background: "背景",
    adjacent: "旁支",
    candidate: "候选"
  };
  return labels[label] ?? label;
}

function sessionStatusLabel(status: string) {
  const labels: Record<string, string> = {
    created: "已创建",
    searching: "检索中",
    screening: "筛选中",
    ready: "可审查",
    reported: "已生成报告",
    error: "失败"
  };
  return labels[status] ?? status;
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function readStoredBoolean(key: string, fallback: boolean) {
  if (typeof window === "undefined") {
    return fallback;
  }
  const value = window.localStorage.getItem(key);
  if (value === null) {
    return fallback;
  }
  return value === "1";
}

function persistBoolean(key: string, value: boolean) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(key, value ? "1" : "0");
}
</script>

<style scoped>
.workspace {
  --bg: #e8e6e2;
  --surface: #f4f3f0;
  --surface-strong: #fafaf8;
  --line: rgba(58, 52, 46, 0.16);
  --line-soft: rgba(58, 52, 46, 0.08);
  --line-strong: rgba(58, 52, 46, 0.32);
  --text: #2a2622;
  --muted: #89837c;
  --accent: #4a4238;
  --accent-strong: #363026;
  --success: #4a5647;
  --warning: #6b5d45;
  --danger: #6b4a47;
  --ink-mark: #3d3530;
  --paper-edge: #d8d6d2;
  --font-sans: "Inter", -apple-system, "Helvetica Neue", sans-serif;
  --font-serif: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
  --font-mono: "JetBrains Mono", "SF Mono", Consolas, "Cascadia Code", monospace;
  --text-2xs: 9px;
  --text-xs: 10px;
  --text-sm: 11px;
  --text-base: 13px;
  --text-md: 14px;
  --text-lg: 15px;
  --text-xl: 18px;
  --text-2xl: 20px;
  --space-2xs: 2px;
  --space-xs: 4px;
  --space-sm: 6px;
  --space-md: 8px;
  --space-lg: 12px;
  --space-xl: 16px;
  --space-2xl: 24px;
  --space-3xl: 32px;
  --shadow-subtle: 0 2px 4px rgba(42, 38, 34, 0.08);
  --shadow-medium: 0 4px 12px rgba(42, 38, 34, 0.12);
  --shadow-strong: 0 12px 24px rgba(42, 38, 34, 0.18);
  --left-width: 280px;
  --right-width: 420px;
  height: 100vh;
  min-height: 100vh;
  overflow: hidden;
  display: grid;
  grid-template-columns: var(--left-width) minmax(0, 1fr) var(--right-width);
  color: var(--text);
  font-family: var(--font-sans);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.4), rgba(255, 255, 255, 0)),
    repeating-linear-gradient(
      0deg,
      transparent 0,
      transparent 31px,
      rgba(58, 52, 46, 0.02) 31px,
      rgba(58, 52, 46, 0.02) 32px
    ),
    var(--bg);
}

.workspace.left-collapsed {
  --left-width: 74px;
}

.workspace.right-collapsed {
  --right-width: 74px;
}

.left-rail,
.right-rail,
.center-stage {
  height: 100vh;
  min-height: 0;
}

.left-rail,
.right-rail {
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border-right: 1px solid var(--line-soft);
  overflow: hidden;
}

.right-rail {
  border-right: none;
  border-left: 1px solid var(--line-soft);
  box-shadow: -2px 0 8px rgba(42, 38, 34, 0.04);
}

.center-stage {
  display: flex;
  flex-direction: column;
  gap: var(--space-xl);
  padding: 22px 24px 24px;
  min-height: 0;
  overflow: hidden;
  background: transparent;
}

.rail-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 20px 18px 16px;
  border-bottom: 1px solid var(--line-soft);
}

.right-top {
  align-items: center;
}

.rail-body,
.right-body {
  min-height: 0;
  flex: 1;
  padding: 18px;
}

.rail-body {
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.right-body {
  overflow: hidden;
}

.brand-lockup {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.brand-lockup.compact {
  width: 100%;
  justify-content: center;
}

.brand-mark {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border: 1px solid var(--line);
  background: var(--accent-strong);
  color: #f8f1e5;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.eyebrow {
  color: var(--muted);
  font-size: 11px;
  text-transform: uppercase;
}

h1,
h2,
h3,
h4,
p,
ol,
ul,
dl,
dt,
dd,
pre {
  margin: 0;
}

.brand-lockup h1,
.stage-heading h2,
.detail-hero h2,
.report-hero h2 {
  font-family: var(--font-serif);
}

.paper-rank,
code,
.query-card code,
.report-draft {
  font-family: var(--font-mono);
}

.brand-lockup h1 {
  font-size: var(--text-2xl);
  line-height: 1.1;
}

.brand-copy {
  font-size: var(--text-xs);
  line-height: 1.4;
  max-width: 22ch;
}

.brand-eyebrow {
  font-size: var(--text-2xs);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  line-height: 1.3;
}

.form-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-head h2 {
  font-size: 17px;
  line-height: 1.15;
  font-family: var(--font-serif);
}

.brand-copy,
.muted,
.paper-authors,
.paper-summary,
.session-meta,
.stage-subtitle,
.reading-copy,
.dialog-copy {
  color: var(--muted);
}

.rail-toggle,
.primary-btn,
.secondary-btn,
.ghost-btn,
.danger-btn,
.text-btn,
.primary-link,
.secondary-link,
.panel-switch button {
  appearance: none;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  font: inherit;
  text-decoration: none;
}

.rail-toggle,
.text-btn {
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.22);
}

.primary-btn,
.primary-link {
  padding: 11px 14px;
  background: var(--accent-strong);
  color: #fafaf8;
  border-color: var(--accent-strong);
  transition: all 140ms ease;
}

.primary-btn:hover,
.primary-link:hover {
  background: var(--ink-mark);
}

.secondary-btn,
.secondary-link {
  padding: 11px 14px;
  background: var(--surface-strong);
  transition: all 140ms ease;
}

.secondary-btn:hover,
.secondary-link:hover {
  background: var(--surface);
  box-shadow: var(--shadow-subtle);
}

.primary-link,
.secondary-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.ghost-btn,
.danger-btn {
  padding: 11px 14px;
}

.danger-btn {
  background: var(--danger);
  border-color: var(--danger);
  color: #fff7f7;
}

.panel-switch {
  display: inline-flex;
  align-items: center;
  gap: 18px;
  width: 100%;
  border-bottom: 1px solid var(--line-soft);
}

.panel-switch button {
  padding: 0 0 10px;
  border: none;
  border-bottom: 2px solid transparent;
  border-radius: 0;
  background: transparent;
  color: var(--muted);
}

.panel-switch button.active {
  background: transparent;
  border-color: var(--accent-strong);
  color: var(--accent-strong);
}

.rail-toggle {
  width: 36px;
  min-width: 36px;
  height: 76px;
  padding: 0;
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border-radius: 4px;
  background: rgba(255, 250, 242, 0.76);
}

.handle-dots {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.handle-dots span {
  width: 12px;
  height: 1px;
  background: var(--accent);
}

.handle-arrow {
  width: 8px;
  height: 8px;
  border-right: 1px solid var(--accent);
  border-bottom: 1px solid var(--accent);
}

.left-handle .handle-arrow {
  transform: rotate(135deg);
}

.left-handle .handle-arrow.collapsed {
  transform: rotate(-45deg);
}

.right-handle .handle-arrow {
  transform: rotate(-45deg);
}

.right-handle .handle-arrow.collapsed {
  transform: rotate(135deg);
}

.topic-form,
.side-block,
.query-board,
.filter-bar,
.paper-stage,
.detail-block,
.report-section {
  border: 1px solid var(--line-soft);
  background: var(--surface-strong);
}

.topic-form,
.side-block,
.paper-stage {
  padding: 12px;
}

.side-block + .side-block {
  margin-top: var(--space-lg);
}

.side-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.left-rail .topic-form,
.left-rail .side-block {
  background: transparent;
  border: none;
  padding: 0;
}

.left-rail .topic-form {
  padding-bottom: 16px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--line-soft);
}

.left-rail .side-block + .side-block {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--line-soft);
}

.left-rail .section-title {
  align-items: center;
  margin-bottom: 8px;
}

.left-rail .section-title h2 {
  color: var(--muted);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.left-rail .topic-form .primary-btn {
  width: 100%;
}

.left-rail .topic-form .form-actions {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
}

.left-rail .text-btn {
  padding: 4px 6px;
  border: none;
  background: transparent;
  color: var(--muted);
}

.left-rail .text-btn:hover {
  color: var(--text);
}

.left-rail textarea {
  min-height: 112px;
}

.left-rail label > span {
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
}

.topic-form label,
.filter-bar label,
.derive-form label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
}

textarea,
input,
select {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface-strong);
  padding: 10px 12px;
  color: var(--text);
  font: inherit;
  box-sizing: border-box;
}

textarea {
  resize: vertical;
  min-height: 120px;
}

textarea:focus,
input:focus,
select:focus,
button:focus,
a:focus {
  outline: 2px solid var(--line-strong);
  outline-offset: 2px;
}

.form-actions,
.stage-actions,
.detail-actions,
.dialog-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-md);
}

.stage-actions .primary-btn,
.stage-actions .secondary-btn {
  padding: 9px 12px;
}

.detail-actions .primary-link,
.detail-actions .secondary-link,
.cite-actions .secondary-link {
  padding: 8px 10px;
  font-size: 12px;
}

.topic-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.section-title {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-lg);
  margin-bottom: 10px;
}

.section-title h2,
.section-title h3 {
  font-size: 14px;
  line-height: 1.2;
}

.session-list,
.paper-list,
.match-list,
.variant-list,
.report-items,
.progress-list {
  list-style: none;
  padding: 0;
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.session-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--space-2xs);
  align-items: stretch;
  border: none;
  border-left: 2px solid var(--line-soft);
  background: transparent;
  padding-left: var(--space-md);
  transition: all 140ms ease;
}

.session-item:hover {
  background: rgba(250, 250, 248, 0.42);
}

.session-item.active {
  border-left: 3px solid var(--ink-mark);
  background: rgba(250, 250, 248, 0.6);
}

.session-select {
  padding: 8px 9px;
  border: none;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.session-delete {
  width: 28px;
  border: none;
  background: transparent;
  color: var(--danger);
  padding: 6px 4px;
  cursor: pointer;
  display: grid;
  place-items: center;
  font-size: 14px;
  line-height: 1;
  opacity: 0.22;
}

.session-item:hover .session-delete,
.session-delete:hover {
  opacity: 1;
}

.session-topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 2px;
}

.session-topline h3 {
  font-size: 12px;
  line-height: 1.2;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
}

.session-meta {
  font-size: 11px;
  line-height: 1.3;
}

.session-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--muted);
  font-size: 11px;
  white-space: nowrap;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--line);
}

.session-status.searching .status-dot,
.session-status.screening .status-dot {
  background: var(--warning);
}

.session-status.ready .status-dot,
.session-status.reported .status-dot {
  background: var(--success);
}

.session-status.error .status-dot {
  background: var(--danger);
}

.session-status.created .status-dot {
  background: var(--accent);
}

.status-pill,
.query-status,
.memo-badge,
.tone-chip,
.label-chip,
.stat-chip {
  border: 1px solid var(--line-soft);
  background: var(--surface-strong);
}

.status-pill,
.query-status,
.memo-badge,
.tone-chip,
.label-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  font-size: 12px;
}

.progress-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.5;
}

.progress-list li {
  padding-left: 14px;
  position: relative;
}

.progress-list li::before {
  content: "";
  position: absolute;
  left: 0;
  top: 8px;
  width: 6px;
  height: 6px;
  background: var(--accent);
}

.process-strip {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}

.process-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 6px 2px 0;
}

.process-label {
  color: var(--muted);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  white-space: nowrap;
}

.process-text {
  min-width: 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.session-summary-card {
  border: 1px solid var(--line-soft);
  background: var(--surface-strong);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.session-summary-label {
  color: var(--muted);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.session-summary-card strong {
  font-size: 13px;
  line-height: 1.4;
}

.session-summary-card p {
  font-size: 12px;
  line-height: 1.5;
}

.stage-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-lg);
  border-bottom: 1px solid var(--line-soft);
  padding-bottom: var(--space-lg);
  flex-shrink: 0;
}

.stage-heading {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
  flex: 1;
}

.stage-heading-top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stage-heading h2 {
  font-size: var(--text-2xl);
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.detail-hero h2,
.report-hero h2 {
  font-size: 22px;
  line-height: 1.2;
}

.stage-meta-stack {
  display: block;
}

.stage-meta-line,
.stage-subtitle {
  font-size: var(--text-sm);
  line-height: 1.4;
}

.stage-meta-line {
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stage-subtitle {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-pill.subtle {
  padding: 3px 8px;
  font-size: 11px;
}

.banner {
  border: 1px solid var(--line-soft);
  padding: 10px 12px;
  background: var(--surface-strong);
  flex-shrink: 0;
}

.error-banner {
  color: var(--danger);
  border-color: rgba(146, 57, 57, 0.28);
}

.warning-banner {
  color: var(--warning);
  border-color: rgba(145, 106, 40, 0.28);
}

.warning-banner ul {
  margin-top: 8px;
  padding-left: 18px;
}

.process-detail {
  border: 1px solid var(--line-soft);
  background: var(--surface);
}

.compact-banner {
  padding: 0;
}

.compact-banner summary {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  cursor: pointer;
  list-style: none;
}

.compact-banner summary::-webkit-details-marker {
  display: none;
}

.process-detail summary::after {
  content: "";
  margin-left: auto;
  width: 7px;
  height: 7px;
  border-right: 1px solid var(--accent);
  border-bottom: 1px solid var(--accent);
  transform: rotate(45deg);
  transition: transform 140ms ease;
}

.process-detail[open] summary::after {
  transform: rotate(225deg);
}

.process-detail-label {
  color: var(--text);
  font-weight: 600;
}

.process-detail-count {
  color: var(--muted);
  font-size: 11px;
}

.compact-banner ul {
  margin: 0;
  padding: 0 18px 12px 32px;
}

.query-board {
  padding: 0;
}

.query-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 0 12px 12px;
}

.query-card {
  border-top: 1px solid var(--line-soft);
  border-right: none;
  border-bottom: none;
  border-left: none;
  padding: 12px;
  background: rgba(250, 250, 248, 0.6);
}

.query-card-head,
.variant-head,
.paper-title-row,
.detail-hero,
.report-hero {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.query-card-head h3,
.paper-title-row h3 {
  font-size: 15px;
  line-height: 1.35;
}

.term-list,
.paper-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.term-list span,
.paper-tags span {
  padding: 4px 8px;
  border: 1px solid var(--line-soft);
  font-size: 12px;
  background: var(--surface-strong);
}

.variant-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 10px;
}

.variant-list li {
  border-top: 1px dashed var(--line-soft);
  padding-top: 10px;
}

code {
  display: block;
  margin: 8px 0 6px;
  padding: 8px 10px;
  border: 1px solid var(--line-soft);
  background: var(--surface-strong);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: 8px 12px;
  flex-shrink: 0;
  border: none;
  border-bottom: 1px solid var(--line-soft);
  background: transparent;
  overflow-x: auto;
  overflow-y: hidden;
}

.filter-bar label {
  display: flex;
  flex: 0 0 auto;
  flex-direction: row;
  align-items: center;
  gap: var(--space-sm);
  min-height: 36px;
  padding: 0;
  border: none;
  background: transparent;
  font-weight: 500;
}

.filter-bar .search-control {
  flex: 1 1 280px;
  min-width: 0;
}

.filter-bar label span {
  color: var(--muted);
  font-size: var(--text-sm);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  white-space: nowrap;
}

.filter-bar input,
.filter-bar select {
  min-height: 36px;
}

.filter-bar .search-control input {
  min-width: 0;
}

.filter-bar select {
  width: auto;
  min-width: 100px;
}

.paper-stage {
  min-height: 0;
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  border: none;
  background: transparent;
  padding: 0;
}

.paper-stage .section-title {
  padding: 0 2px 8px;
  margin-bottom: 0;
}

.paper-list {
  display: flex;
  flex-direction: column;
  gap: 0;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  border-top: 1px solid var(--line-soft);
}

.paper-row {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr) 92px;
  gap: var(--space-lg);
  padding: 14px 8px 14px 14px;
  border: none;
  border-left: 2px solid var(--line-soft);
  border-bottom: 1px solid var(--line-soft);
  background: transparent;
  cursor: pointer;
  position: relative;
  transition: all 160ms ease;
}

.paper-row:hover {
  background: var(--surface-strong);
  box-shadow: var(--shadow-subtle);
}

.paper-row.active {
  background: var(--surface-strong);
  border-left: 3px solid var(--ink-mark);
  box-shadow: var(--shadow-medium);
}

.paper-row.excluded {
  opacity: 0.58;
}

.paper-rank {
  min-width: 32px;
  color: var(--ink-mark);
  font-size: var(--text-md);
  line-height: 1.2;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.paper-main {
  min-width: 0;
}

.paper-title-row {
  align-items: flex-start;
  margin-bottom: 4px;
}

.paper-title-row h3 {
  overflow-wrap: anywhere;
}

.paper-year {
  color: var(--muted);
  font-size: 12px;
  white-space: nowrap;
}

.paper-summary {
  line-height: 1.65;
  font-size: 12px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.paper-side {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: center;
  gap: 8px;
  opacity: 0.16;
  transform: translateY(2px);
  transition:
    opacity 140ms ease,
    transform 140ms ease;
}

.paper-row:hover .paper-side,
.paper-row.active .paper-side,
.paper-row:focus-within .paper-side {
  opacity: 1;
  transform: none;
}

.toggle-select {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  color: var(--muted);
  font-size: 12px;
}

.toggle-select input {
  width: 18px;
  height: 18px;
}

.label-chip.must_read {
  color: var(--success);
}

.label-chip.frontier {
  color: var(--warning);
}

.label-chip.adjacent {
  color: #6c4a87;
}

.right-body {
  display: flex;
  flex-direction: column;
}

.panel-scroll {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  padding-right: 4px;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.detail-hero,
.report-hero {
  align-items: flex-start;
  margin-bottom: var(--space-lg);
  border-top: 2px solid var(--paper-edge);
  padding-top: var(--space-xl);
}

.detail-heading {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.detail-heading-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.detail-authors,
.detail-meta-line {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.45;
}

.detail-meta-line {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
}

.detail-meta-line span::after {
  content: "·";
  margin-left: 10px;
  color: var(--line);
}

.detail-meta-line span:last-child::after {
  display: none;
}

.score-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 42px;
  padding: 4px 8px;
  border: 1px solid var(--line-soft);
  background: var(--surface-strong);
  color: var(--ink-mark);
  font-size: 12px;
  font-weight: 700;
}

.detail-actions,
.status-actions {
  margin-bottom: 12px;
}

.detail-actions {
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line-soft);
}

.status-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.status-actions button {
  padding: 7px 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface-strong);
  cursor: pointer;
  font-size: 12px;
}

.status-actions button.active {
  background: var(--accent-strong);
  border-color: var(--accent-strong);
  color: #fafaf8;
}

.status-actions button.danger {
  color: var(--danger);
}

.cite-box {
  border: 1px solid var(--line-soft);
  background: var(--surface-strong);
  padding: 10px 12px;
}

.detail-block {
  padding: 12px;
  margin-bottom: 12px;
}

.reading-copy {
  line-height: 1.75;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.detail-section-title {
  align-items: center;
}

.ai-note {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--line-soft);
  color: var(--muted);
  display: flex;
  flex-direction: column;
  gap: 6px;
  line-height: 1.7;
}

.ai-note-label {
  color: var(--text);
  font-size: 12px;
  font-weight: 700;
}

.cite-box {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.cite-text {
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.cite-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.match-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.match-list li {
  border: 1px solid var(--line-soft);
  background: var(--surface-strong);
  padding: 10px;
}

.match-list li span {
  display: block;
  color: var(--muted);
  font-size: 12px;
  margin-top: 4px;
}

.derive-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: end;
}

.memo-badge {
  color: var(--accent);
  padding: 3px 8px;
  font-size: 11px;
}

.report-summary {
  margin-top: 4px;
}

.report-toc {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.report-toc button {
  padding: 8px 10px;
  border: 1px solid var(--line-soft);
  background: var(--surface-strong);
  cursor: pointer;
}

.report-article {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.report-section {
  padding: 14px 0;
  border: none;
  border-top: 1px solid var(--line-soft);
  background: transparent;
}

.report-section h3 {
  font-size: 16px;
  margin-bottom: 12px;
}

.report-items {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.report-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  line-height: 1.75;
  padding-left: 10px;
  border-left: 2px solid var(--line-soft);
}

.report-item p {
  flex: 1;
  overflow-wrap: anywhere;
}

.report-item.paragraph {
  display: block;
}

.report-order {
  min-width: 28px;
  color: var(--accent);
  font-weight: 700;
}

.tone-chip {
  min-width: 36px;
  justify-content: center;
  border: none;
  background: transparent;
  padding: 0;
  font-size: 11px;
}

.report-item.evidence .tone-chip {
  color: var(--success);
}

.report-item.evidence {
  border-left-color: rgba(53, 87, 59, 0.5);
}

.report-item.judgment .tone-chip {
  color: var(--accent);
}

.report-item.judgment {
  border-left-color: rgba(79, 64, 48, 0.45);
}

.report-item.speculation .tone-chip {
  color: #6c4a87;
}

.report-item.speculation {
  border-left-color: rgba(108, 74, 135, 0.45);
}

.report-item.action .tone-chip {
  color: var(--warning);
}

.report-item.action {
  border-left-color: rgba(145, 106, 40, 0.48);
}

.report-item.note {
  border-left-color: rgba(90, 74, 52, 0.26);
}

.report-draft {
  white-space: pre-wrap;
  line-height: 1.75;
  border: 1px solid var(--line-soft);
  background: var(--surface-strong);
  padding: 14px;
}

.empty-state {
  border: 1px dashed var(--line);
  background: var(--surface);
  padding: 22px;
  text-align: center;
  line-height: 1.8;
}

.empty-state.inset {
  margin-top: 10px;
}

.dialog-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(24, 18, 14, 0.44);
  display: grid;
  place-items: center;
  padding: 20px;
  z-index: 30;
}

.dialog-panel {
  width: min(520px, 100%);
  border: 1px solid var(--line);
  background: var(--surface-strong);
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.dialog-panel h2 {
  font-family: var(--font-serif);
  font-size: 26px;
}

.dialog-copy strong {
  color: var(--text);
}

@media (max-width: 1360px) {
  .workspace {
    --left-width: 270px;
    --right-width: 380px;
  }
}

@media (max-width: 1180px) {
  .workspace {
    grid-template-columns: var(--left-width) minmax(0, 1fr);
  }

  .right-rail {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: min(400px, 100vw);
    z-index: 20;
    box-shadow: -10px 0 30px rgba(25, 19, 14, 0.14);
  }

  .workspace.right-collapsed .right-rail {
    transform: translateX(calc(100% - 74px));
  }

  .workspace:not(.right-collapsed) .right-rail {
    transform: translateX(0);
  }
}

@media (max-width: 960px) {
  .workspace {
    display: flex;
    flex-direction: column;
    height: auto;
    min-height: auto;
    overflow: visible;
  }

  .left-rail,
  .center-stage {
    min-height: auto;
    height: auto;
  }

  .left-rail {
    border-right: none;
    border-bottom: 1px solid var(--line-soft);
  }

  .center-stage {
    overflow: visible;
  }

  .right-rail {
    height: 100vh;
  }

  .stage-header,
  .detail-hero,
  .report-hero {
    flex-direction: column;
  }

  .query-grid,
  .session-summary-grid {
    grid-template-columns: 1fr;
  }

  .filter-bar {
    align-items: stretch;
    flex-direction: column;
    overflow: visible;
  }

  .filter-bar label,
  .filter-bar .search-control,
  .filter-bar select {
    width: 100%;
  }

  .derive-form {
    grid-template-columns: 1fr;
  }

  .detail-meta-line {
    gap: 4px 8px;
  }

  .paper-row {
    grid-template-columns: 1fr;
  }

  .paper-side {
    flex-direction: row;
    justify-content: space-between;
    align-items: center;
    opacity: 1;
    transform: none;
  }
}
</style>
