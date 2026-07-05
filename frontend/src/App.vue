<template>
  <main
    class="workspace"
    :class="{
      'left-collapsed': !leftSidebarOpen,
      'report-mode': workspaceMode === 'report'
    }"
  >
    <aside class="left-rail">
      <div class="rail-top" :class="{ compact: !leftSidebarOpen }">
        <div v-if="leftSidebarOpen" class="brand-lockup">
          <div class="brand-mark">MM</div>
          <div v-if="leftSidebarOpen">
            <h1>文献妙妙屋</h1>
            <p class="brand-eyebrow">MIAOWEN LITERATURE WORKBENCH</p>
          </div>
        </div>
        <button
          class="rail-toggle icon-frame"
          type="button"
          :aria-label="leftSidebarOpen ? '收起左侧栏' : '展开左侧栏'"
          @click="toggleLeftSidebar"
        >
          <svg
            viewBox="0 0 24 24"
            class="toggle-icon"
            :class="{ collapsed: !leftSidebarOpen }"
            aria-hidden="true"
          >
            <path
              d="M14.5 6 9 12l5.5 6M19 6l-5.5 6L19 18"
              fill="none"
              stroke="currentColor"
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="1.8"
            />
          </svg>
        </button>
      </div>

      <nav v-if="!leftSidebarOpen" class="rail-quicklinks" aria-label="左栏快捷入口">
        <button
          class="quicklink-btn"
          type="button"
          aria-label="输入研究"
          title="输入研究"
          @click="openLeftRailSection('research')"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path
              d="M7 4.5h7l4 4V19a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 6 19V6A1.5 1.5 0 0 1 7.5 4.5Z"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
            />
            <path
              d="M14 4.5V9h4.5M9 15.5l2.2 2.2 4.8-4.9"
              fill="none"
              stroke="currentColor"
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="1.6"
            />
          </svg>
        </button>
        <button
          class="quicklink-btn"
          type="button"
          aria-label="History"
          title="History"
          @click="openLeftRailSection('history')"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path
              d="M5 12a7 7 0 1 0 2.1-5M5 4v4h4M12 8.5V12l2.8 1.8"
              fill="none"
              stroke="currentColor"
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="1.6"
            />
          </svg>
        </button>
        <button
          class="quicklink-btn"
          type="button"
          aria-label="当前流程"
          title="当前流程"
          @click="openLeftRailSection('logs')"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path
              d="M4.5 16h3l2.2-6 3.6 10 2.2-6h4"
              fill="none"
              stroke="currentColor"
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="1.8"
            />
          </svg>
        </button>
      </nav>

      <div v-else ref="leftRailBodyRef" class="rail-body">
        <form ref="researchSectionRef" class="topic-form" @submit.prevent="startResearch">
          <div class="form-head">
            <p class="eyebrow">New Session</p>
            <h2>新建调研</h2>
          </div>
          <label>
            <span>研究问题</span>
            <textarea
              ref="topicTextareaRef"
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

        <section ref="historySectionRef" class="side-block">
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

        <section ref="logsSectionRef" class="side-block">
          <div class="section-title">
            <h2>当前流程</h2>
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

    <section class="stage-shell">
      <header class="utility-bar">
        <div class="utility-copy">
          <h2 :title="currentSession?.topic || ''">{{ currentSessionShortTitle }}</h2>
          <div v-if="currentSession" class="utility-meta">
            <span
              v-for="item in utilityMetaItems"
              :key="item"
              class="utility-meta-item"
            >
              {{ item }}
            </span>
          </div>
          <p v-else class="muted">选择或创建一个调研会话，主舞台只保留论文工作台。</p>
        </div>
      </header>

      <p v-if="error" class="banner error-banner">{{ error }}</p>

      <section v-if="currentSession" class="tool-layer">
        <div class="tool-strip">
          <div class="source-pill" :title="currentSessionSourceText">
            <span class="process-label">Sources</span>
            <span class="process-text">{{ currentSessionSourceText }}</span>
          </div>

          <div v-if="metricRings.length" class="metric-ring-group">
            <button
              v-for="ring in metricRings"
              :key="ring.id"
              type="button"
              class="metric-ring"
              :class="`tone-${ring.tone}`"
              :style="{ '--ring-progress': `${ring.progress}%` }"
              :aria-label="buildMetricRingAriaLabel(ring)"
              :title="buildMetricRingTitle(ring)"
            >
              <span class="metric-ring-core" aria-hidden="true"></span>
              <span class="sr-only">{{ buildMetricRingAriaLabel(ring) }}</span>
              <span class="metric-tooltip">
                <strong>{{ ring.label }}</strong>
                <span
                  v-if="ring.value || ring.caption"
                  class="metric-tooltip-summary"
                >
                  {{ [ring.value, ring.caption].filter(Boolean).join(" | ") }}
                </span>
                <span class="metric-tooltip-detail">{{ ring.detail }}</span>
              </span>
            </button>
          </div>

          <div class="tool-actions">
            <button
              v-if="hasRuntimeDetails"
              class="runtime-trigger"
              :class="{ open: runtimeTrayOpen }"
              type="button"
              :aria-expanded="runtimeTrayOpen"
              @click="runtimeTrayOpen = !runtimeTrayOpen"
            >
              <span class="runtime-trigger-label">&#x8fd0;&#x884c;&#x8be6;&#x60c5;</span>
              <span class="runtime-badges">
                <span
                  v-if="degradationNotices.length"
                  class="runtime-badge runtime-badge-warning"
                >
                  &#x964d;&#x7ea7; {{ degradationNotices.length }}
                </span>
                <span v-if="queryTasks.length" class="runtime-badge">
                  &#x5b50;&#x4efb;&#x52a1; {{ queryTasks.length }}
                </span>
              </span>
            </button>

            <button
              class="report-entry icon-frame"
              type="button"
              :aria-label="reportEntryTitle"
              :title="reportEntryTitle"
              @click="openReportDrawer"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path
                  d="M14.5 6 9 12l5.5 6M19 6l-5.5 6L19 18"
                  fill="none"
                  stroke="currentColor"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="1.8"
                />
              </svg>
              <span v-if="reportEntryBadge" class="report-entry-count">
                {{ reportEntryBadge }}
              </span>
              <span class="sr-only">{{ reportEntryTitle }}</span>
            </button>
          </div>
        </div>

        <div v-if="runtimeTrayOpen && hasRuntimeDetails" class="runtime-tray">
          <section
            v-if="degradationNotices.length"
            class="process-subpanel warning-banner"
          >
            <div class="process-subpanel-head">
              <span class="process-subpanel-title">降级提示</span>
              <span class="process-detail-count">{{ degradationNotices.length }}</span>
            </div>
            <ul>
              <li v-for="notice in degradationNotices" :key="notice">{{ notice }}</li>
            </ul>
          </section>

          <section v-if="queryTasks.length" class="process-subpanel query-board">
            <div class="process-subpanel-head">
              <span class="process-subpanel-title">检索子任务</span>
              <span class="process-detail-count">{{ queryTasks.length }}</span>
            </div>

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
          </section>
        </div>
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

        <div v-if="currentSession && filteredPapers.length" ref="paperListRef" class="paper-list">
          <div
            v-for="paper in filteredPapers"
            :key="paper.id"
            class="paper-stack"
            :data-paper-stack-id="paper.id"
          >
            <article
              class="paper-row"
              :class="{
                active: activePaper?.id === paper.id,
                excluded: paper.user_status === 'excluded'
              }"
              @click="togglePaperExpansion(paper.id)"
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
                <button class="text-btn" type="button" @click.stop="togglePaperExpansion(paper.id)">
                  {{ activePaper?.id === paper.id ? "收起" : "查看" }}
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

            <transition name="inline-detail">
              <section
                v-if="activePaper?.id === paper.id"
                class="inline-detail-panel"
              >
                <div class="inline-detail-top">
                  <div class="inline-detail-heading">
                    <div class="inline-heading-top">
                      <p class="eyebrow">Paper Detail</p>
                      <span class="score-pill">{{ Math.round(paper.final_score * 100) }}</span>
                    </div>
                    <h3>{{ paper.title }}</h3>
                    <p class="detail-authors">{{ compactAuthors(paper.authors) }}</p>
                    <div class="detail-meta-line">
                      <span>{{ paper.year || "n.d." }}</span>
                      <span>{{ paper.venue || "Unknown venue" }}</span>
                      <span>{{ paper.citation_count }} citations</span>
                      <span>{{ paper.source || "unknown" }}</span>
                    </div>
                  </div>

                  <div class="detail-actions">
                    <a
                      v-if="resolvePaperLink(paper)"
                      class="primary-link"
                      :href="resolvePaperLink(paper) || undefined"
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
                      BibTeX
                    </a>
                  </div>
                </div>

                <section class="detail-block">
                  <div class="section-title detail-section-title">
                    <h3>摘要</h3>
                    <span :class="['label-chip', paper.relevance_label]">
                      {{ relevanceLabel(paper.relevance_label) }}
                    </span>
                  </div>
                  <p class="reading-copy">
                    {{ paper.abstract || "暂无摘要。请打开论文链接进一步确认。" }}
                  </p>
                  <div class="ai-note">
                    <span class="ai-note-label">AI 判断</span>
                    <p>{{ paper.ai_reason }}</p>
                  </div>
                </section>

                <section class="detail-block">
                  <div class="section-title detail-section-title">
                    <h3>引用 / BibTeX</h3>
                  </div>
                  <div class="cite-box">
                    <p class="cite-text">{{ buildCitationText(paper) }}</p>
                    <div class="cite-actions">
                      <button class="text-btn" type="button" @click="copyCitation(paper)">
                        复制参考格式
                      </button>
                      <a
                        class="secondary-link"
                        :href="exportBibtexHref"
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        导出 BibTeX
                      </a>
                    </div>
                  </div>
                </section>

                <section class="detail-block">
                  <div class="section-title detail-section-title">
                    <h3>状态操作</h3>
                  </div>
                  <div class="status-actions">
                    <button
                      type="button"
                      :class="{ active: paper.user_status === 'included' }"
                      @click="setPaperStatus(paper, 'included')"
                    >
                      确认
                    </button>
                    <button
                      type="button"
                      :class="{ active: paper.user_status === 'to_read' }"
                      @click="setPaperStatus(paper, 'to_read')"
                    >
                      待读
                    </button>
                    <button
                      type="button"
                      :class="{ active: paper.user_status === 'saved' }"
                      @click="setPaperStatus(paper, 'saved')"
                    >
                      收藏
                    </button>
                    <button
                      type="button"
                      :class="{
                        active: paper.user_status === 'excluded',
                        danger: paper.user_status === 'excluded'
                      }"
                      @click="setPaperStatus(paper, 'excluded')"
                    >
                      排除
                    </button>
                  </div>
                </section>

                <section v-if="paper.query_matches.length" class="detail-block">
                  <div class="section-title detail-section-title">
                    <h3>检索命中</h3>
                  </div>
                  <ul class="match-list">
                    <li
                      v-for="match in paper.query_matches"
                      :key="`${paper.id}-${match.subtask_id}-${match.query_type}-${match.source}`"
                    >
                      <strong>{{ match.concept }}</strong>
                      <span>{{ queryTypeLabel(match.query_type) }} · {{ match.source }}</span>
                      <code>{{ match.query_text }}</code>
                    </li>
                  </ul>
                </section>

                <form class="derive-form detail-block" @submit.prevent="deriveFromActivePaper">
                  <label>
                    <span>派生会话</span>
                    <input
                      v-model="deriveTopic"
                      type="text"
                      :placeholder="`围绕 ${paper.title.slice(0, 28)}... 继续深挖`"
                    />
                  </label>
                  <button class="secondary-btn" type="submit" :disabled="!deriveTopic.trim()">
                    派生
                  </button>
                </form>
              </section>
            </transition>
          </div>
        </div>

        <div v-else-if="currentSession" class="empty-state">
          <p>当前筛选条件下没有文献。</p>
          <p class="muted">放宽年份、状态或关键词后再看一轮。</p>
        </div>

        <div v-else class="empty-state">
          <p>先创建一个调研会话。</p>
          <p class="muted">主舞台会把检索、筛选、精读和报告都收拢到同一个工作台里。</p>
        </div>
      </section>

      <transition name="report-drawer">
        <div
          v-if="workspaceMode === 'report'"
          class="report-drawer-shell"
          @click.self="closeReportDrawer"
        >
          <aside class="report-drawer">
            <header class="report-drawer-header">
              <button
                class="report-back icon-frame"
                type="button"
                aria-label="&#x8fd4;&#x56de;&#x8bba;&#x6587;&#x5de5;&#x4f5c;&#x53f0;"
                title="&#x8fd4;&#x56de;&#x8bba;&#x6587;&#x5de5;&#x4f5c;&#x53f0;"
                @click="closeReportDrawer"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    d="M9.5 6 15 12l-5.5 6M5 6l5.5 6L5 18"
                    fill="none"
                    stroke="currentColor"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="1.8"
                  />
                </svg>
                <span class="sr-only">&#x8fd4;&#x56de;&#x5de5;&#x4f5c;&#x53f0;</span>
              </button>

              <div class="report-drawer-copy">
                <p class="eyebrow">Report Mode</p>
                <h2>{{ currentSession?.topic || "研究报告" }}</h2>
                <p class="muted">&#x8986;&#x76d6;&#x4e2d;&#x592e;&#x5de5;&#x4f5c;&#x53f0;&#x7684;&#x62a5;&#x544a;&#x9605;&#x8bfb;&#x6a21;&#x5f0f;</p>
              </div>

              <div class="report-drawer-actions">
                <button
                  class="secondary-btn"
                  type="button"
                  :disabled="reporting || !confirmedCount"
                  @click="generateReport"
                >
                  {{ reporting ? "生成中..." : reportActionLabel }}
                </button>
                <a
                  v-if="currentSession && hasReportContent"
                  class="text-btn report-export-link"
                  :href="exportMarkdownHref"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  导出
                </a>
              </div>
            </header>

            <section ref="reportScrollRef" class="report-body">
              <div class="report-hero">
                <div class="report-heading">
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

              <div v-else-if="reporting" class="empty-state inset">
                <p>正在生成报告草稿。</p>
                <p class="muted">SSE 流会把内容逐段写入这个抽屉，列表上下文不会丢失。</p>
              </div>

              <div v-else class="empty-state inset">
                <p>还没有研究报告。</p>
                <p class="muted">基于当前已纳入文献生成一份可供最终阅读和判断的报告。</p>
                <button
                  class="secondary-btn empty-action"
                  type="button"
                  :disabled="reporting || !confirmedCount"
                  @click="generateReport"
                >
                  生成报告
                </button>
              </div>
            </section>
          </aside>
        </div>
      </transition>
    </section>

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
  type ScholarlyPaper,
  type SessionMetadata,
  type SessionMetrics,
  type StreamEvent
} from "./services/api";

type WorkspaceMode = "papers" | "report";
type LeftRailSection = "research" | "history" | "logs";
type ReportTone = "evidence" | "judgment" | "speculation" | "action" | "note";
type ReportItemKind = "paragraph" | "bullet" | "ordered";
type MetricRingTone = "warning" | "success" | "neutral";

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

interface MetricRing {
  id: string;
  label: string;
  value: string;
  caption: string;
  detail: string;
  progress: number;
  tone: MetricRingTone;
}

const APP_TITLE = "文献妙妙屋";
const LEFT_PANEL_KEY = "miaowen:left-panel";
const RUNTIME_TRAY_KEY = "miaowen:runtime-tray";

const sessions = ref<ResearchSession[]>([]);
const currentSession = ref<ResearchSession | null>(null);
const activePaperId = ref<string | null>(null);
const workspaceMode = ref<WorkspaceMode>("papers");
const topicInput = ref("");
const deriveTopic = ref("");
const progressLogs = ref<string[]>([]);
const error = ref("");
const creating = ref(false);
const reporting = ref(false);
const reportText = ref("");
const showAllLogs = ref(false);
const leftSidebarOpen = ref(readStoredBoolean(LEFT_PANEL_KEY, true));
const runtimeTrayOpen = ref(readStoredBoolean(RUNTIME_TRAY_KEY, false));
const savedPaperListScrollTop = ref(0);
const deleteTargetSession = ref<ResearchSession | null>(null);
const deletingSessionId = ref<string | null>(null);

const filters = reactive({
  keyword: "",
  label: "",
  status: "",
  year: ""
});

let currentController: AbortController | null = null;

const leftRailBodyRef = ref<HTMLElement | null>(null);
const researchSectionRef = ref<HTMLElement | null>(null);
const historySectionRef = ref<HTMLElement | null>(null);
const logsSectionRef = ref<HTMLElement | null>(null);
const topicTextareaRef = ref<HTMLTextAreaElement | null>(null);
const paperListRef = ref<HTMLElement | null>(null);
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
const hasRuntimeDetails = computed(
  () => degradationNotices.value.length > 0 || queryTasks.value.length > 0
);
const confirmedCount = computed(
  () =>
    papers.value.filter(
      (paper) => paper.selected && paper.user_status !== "excluded"
    ).length
);
const activePaper = computed(() => {
  if (!papers.value.length || !activePaperId.value) {
    return null;
  }
  return papers.value.find((paper) => paper.id === activePaperId.value) ?? null;
});
const currentReportMarkdown = computed(
  () => reportText.value || latestReport.value?.content_markdown || ""
);
const hasReportContent = computed(() => Boolean(currentReportMarkdown.value.trim()));
const parsedReport = computed(() => parseReportMarkdown(currentReportMarkdown.value));
const reportHeading = computed(() => parsedReport.value.title || "研究报告");
const reportSections = computed(() => parsedReport.value.sections);
const currentSessionShortTitle = computed(() => {
  if (!currentSession.value) {
    return "选择或创建调研会话";
  }
  return currentSession.value.topic;
});
const utilityMetaItems = computed(() => {
  if (!currentSession.value) {
    return [];
  }
  return [
    `${confirmedCount.value} 已纳入`,
    `${currentSession.value.paper_count} 候选`,
    sessionStatusLabel(currentSession.value.status)
  ];
});
const reportEntryCount = computed(() => currentSession.value?.report_count ?? 0);
const reportEntryBadge = computed(() => {
  if (!reportEntryCount.value) {
    return "";
  }
  return reportEntryCount.value > 9 ? "9+" : String(reportEntryCount.value);
});
const reportEntryTitle = computed(() =>
  reportEntryCount.value
    ? `\u62a5\u544a\u6a21\u5f0f | ${reportEntryCount.value} \u4efd\u62a5\u544a`
    : "\u62a5\u544a\u6a21\u5f0f"
);
const reportActionLabel = computed(() =>
  hasReportContent.value || (currentSession.value?.report_count ?? 0) > 0
    ? "重新生成"
    : "生成"
);
const exportBibtexHref = computed(() =>
  currentSession.value ? exportUrl(currentSession.value.id, "bib") : "#"
);
const exportMarkdownHref = computed(() =>
  currentSession.value ? exportUrl(currentSession.value.id, "md") : "#"
);
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
    return [
      formatFrontierReason(sessionMetadata.value.frontier_reason),
      expansionMix,
      frontierSelected
    ]
      .filter(Boolean)
      .join(" ");
  }
  return ["Direct high-relevance coverage was sufficient.", expansionMix]
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
    metrics.frontier_query_count ? `frontier ${metrics.frontier_query_count}` : "",
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

const sourceHealthCounts = computed(() => {
  const statuses = Object.values(currentSession.value?.source_statuses ?? {});
  const healthy = statuses.filter((status) => status === "ok").length;
  const degraded = statuses.filter((status) =>
    ["failed", "partial_failure"].includes(status)
  ).length;
  const skipped = statuses.filter((status) => status.startsWith("skipped")).length;
  return {
    healthy,
    degraded,
    skipped,
    total: statuses.length
  };
});

const sourceHealthText = computed(() => {
  if (!currentSession.value) {
    return "";
  }
  const { healthy, degraded, skipped } = sourceHealthCounts.value;
  if (!healthy && !degraded && !skipped) {
    return "";
  }
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

const metricRings = computed<MetricRing[]>(() => {
  if (!currentSession.value) {
    return [];
  }
  const metrics = sessionMetrics.value;
  const health = sourceHealthCounts.value;
  const rawCount = Math.max(metrics.raw_paper_count ?? 0, 1);
  const finalCount = metrics.final_candidate_count ?? 0;
  const totalSources = Math.max(health.total, 1);

  return [
    {
      id: "frontier",
      label: "Frontier",
      value: sessionMetadata.value.frontier_mode ? "ON" : "OFF",
      caption: sessionMetadata.value.frontier_mode ? "triggered" : "steady",
      detail: [frontierStatusText.value, frontierReasonText.value].filter(Boolean).join("\n"),
      progress: sessionMetadata.value.frontier_mode ? 82 : 18,
      tone: "warning"
    },
    {
      id: "candidates",
      label: "Candidates",
      value: String(finalCount),
      caption: `selected ${confirmedCount.value}`,
      detail: [candidatePoolText.value, candidatePoolDetailText.value].filter(Boolean).join("\n"),
      progress: Math.max(16, Math.min(100, Math.round((finalCount / rawCount) * 100))),
      tone: "neutral"
    },
    {
      id: "health",
      label: "Health",
      value: String(health.healthy),
      caption: `skip ${health.skipped}`,
      detail: [sourceHealthText.value, sourceHealthDetailText.value].filter(Boolean).join("\n"),
      progress: Math.max(14, Math.min(100, Math.round((health.healthy / totalSources) * 100))),
      tone: "success"
    }
  ];
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

watch(leftSidebarOpen, (value) => persistBoolean(LEFT_PANEL_KEY, value));
watch(runtimeTrayOpen, (value) => persistBoolean(RUNTIME_TRAY_KEY, value));
watch(hasRuntimeDetails, (value) => {
  if (!value) {
    runtimeTrayOpen.value = false;
  }
});
watch(
  currentSession,
  (session) => {
    if (typeof document !== "undefined") {
      document.title = session ? `${session.topic} · ${APP_TITLE}` : APP_TITLE;
    }
  },
  { immediate: true }
);
watch(activePaperId, (paperId, previousId) => {
  if (!paperId || paperId === previousId) {
    return;
  }
  deriveTopic.value = "";
  void nextTick(() => scrollExpandedPaperIntoView(paperId));
});

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
      workspaceMode.value = "papers";
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
    workspaceMode.value = "papers";
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
  workspaceMode.value = "papers";
  activePaperId.value = null;
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
    pushLog("筛选完成，已进入论文工作台");
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
  activePaperId.value = hasActivePaper ? activePaperId.value : null;
  deriveTopic.value = "";
  reportText.value = normalized.reports?.[0]?.content_markdown ?? "";
  syncSessionListSummary();
}

function openLeftRailSection(section: LeftRailSection) {
  if (!leftSidebarOpen.value) {
    leftSidebarOpen.value = true;
  }

  void nextTick(() => {
    const target =
      section === "research"
        ? researchSectionRef.value
        : section === "history"
          ? historySectionRef.value
          : logsSectionRef.value;
    target?.scrollIntoView({ block: "start", behavior: "smooth" });
    if (section === "research") {
      topicTextareaRef.value?.focus();
    }
  });
}

function togglePaperExpansion(paperId: string) {
  activePaperId.value = activePaperId.value === paperId ? null : paperId;
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
  openReportDrawer();
  reporting.value = true;
  error.value = "";
  reportText.value = "";
  scrollReportToTop();
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
  if (!currentSession.value || !deriveTopic.value.trim() || !activePaper.value) {
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

function openReportDrawer() {
  savedPaperListScrollTop.value = paperListRef.value?.scrollTop ?? 0;
  workspaceMode.value = "report";
  scrollReportToTop();
}

function closeReportDrawer() {
  workspaceMode.value = "papers";
  void nextTick(() => {
    paperListRef.value?.scrollTo({
      top: savedPaperListScrollTop.value,
      behavior: "auto"
    });
  });
}

function buildMetricRingAriaLabel(ring: MetricRing) {
  return [ring.label, ring.value, ring.caption, ring.detail.replace(/\n/g, ". ")]
    .filter(Boolean)
    .join(". ");
}

function buildMetricRingTitle(ring: MetricRing) {
  const summary = [ring.value, ring.caption].filter(Boolean).join(" | ");
  const detail = ring.detail.replace(/\n/g, " | ");
  return [ring.label, summary, detail].filter(Boolean).join(": ");
}

function toggleLeftSidebar() {
  leftSidebarOpen.value = !leftSidebarOpen.value;
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

function scrollExpandedPaperIntoView(paperId: string) {
  const container = paperListRef.value;
  if (!container) {
    return;
  }
  const target = container.querySelector<HTMLElement>(
    `[data-paper-stack-id="${paperId}"]`
  );
  if (!target) {
    return;
  }

  const containerRect = container.getBoundingClientRect();
  const targetRect = target.getBoundingClientRect();
  const topComfort = 20;
  const bottomComfort = 28;

  if (targetRect.top < containerRect.top + topComfort) {
    container.scrollBy({
      top: targetRect.top - containerRect.top - topComfort,
      behavior: "smooth"
    });
    return;
  }

  if (targetRect.bottom > containerRect.bottom - bottomComfort) {
    container.scrollBy({
      top: targetRect.bottom - containerRect.bottom + bottomComfort,
      behavior: "smooth"
    });
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

function scrollReportToTop() {
  void nextTick(() => {
    reportScrollRef.value?.scrollTo({ top: 0, behavior: "auto" });
  });
}

function pushLog(message: string) {
  progressLogs.value = [...progressLogs.value.slice(-79), message];
}

function syncCurrentSessionCounters() {
  if (!currentSession.value) {
    return;
  }
  currentSession.value.paper_count = currentSession.value.papers?.length ?? 0;
  currentSession.value.selected_count = confirmedCount.value;
  currentSession.value.report_count =
    currentSession.value.reports?.length ?? currentSession.value.report_count;
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
  --surface-muted: rgba(250, 250, 248, 0.72);
  --line: rgba(58, 52, 46, 0.16);
  --line-soft: rgba(58, 52, 46, 0.08);
  --line-strong: rgba(58, 52, 46, 0.3);
  --text: #2a2622;
  --muted: #867f78;
  --accent: #4a4238;
  --accent-strong: #363026;
  --success: #4a5647;
  --warning: #6b5d45;
  --danger: #6b4a47;
  --ink-mark: #3d3530;
  --font-sans: "Avenir Next", "Segoe UI", sans-serif;
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
  --shadow-strong: 0 14px 32px rgba(42, 38, 34, 0.16);
  --left-width: 292px;
  height: 100vh;
  min-height: 100vh;
  overflow: hidden;
  display: grid;
  grid-template-columns: var(--left-width) minmax(0, 1fr);
  color: var(--text);
  font-family: var(--font-sans);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.42), rgba(255, 255, 255, 0)),
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
  --left-width: 88px;
}

.left-rail,
.stage-shell {
  height: 100vh;
  min-height: 0;
}

.left-rail {
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border-right: 1px solid var(--line-soft);
  overflow: hidden;
}

.stage-shell {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
  overflow: hidden;
  padding: 18px 22px 22px;
}

.rail-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 20px 18px 16px;
  border-bottom: 1px solid var(--line-soft);
}

.brand-lockup {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.rail-top.compact {
  justify-content: center;
  padding-inline: 0;
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

.brand-lockup h1,
.utility-copy h2,
.report-drawer-copy h2,
.report-hero h2,
.inline-detail-heading h3,
.dialog-panel h2 {
  font-family: var(--font-serif);
}

.brand-lockup h1 {
  font-size: var(--text-2xl);
  line-height: 1.1;
}

.brand-eyebrow {
  font-size: var(--text-2xs);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
}

.eyebrow {
  color: var(--muted);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.rail-toggle,
.primary-btn,
.secondary-btn,
.ghost-btn,
.danger-btn,
.text-btn,
.primary-link,
.secondary-link,
.report-entry,
.report-back,
.metric-ring,
.quicklink-btn,
.runtime-trigger,
.report-toc button {
  appearance: none;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  font: inherit;
  text-decoration: none;
}

.icon-frame {
  width: 32px;
  height: 32px;
  padding: 0;
  display: inline-grid;
  place-items: center;
  background: rgba(255, 250, 242, 0.76);
}

.rail-toggle {
  background: rgba(255, 250, 242, 0.76);
}

.toggle-icon {
  width: 18px;
  height: 18px;
  transition: transform 160ms ease;
}

.toggle-icon.collapsed {
  transform: rotate(180deg);
}

.rail-quicklinks {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 16px 0 18px;
}

.quicklink-btn {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  background: rgba(255, 255, 255, 0.3);
}

.quicklink-btn svg {
  width: 18px;
  height: 18px;
}

.rail-body {
  min-height: 0;
  flex: 1;
  padding: 18px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.topic-form,
.side-block {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.side-block + .side-block {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--line-soft);
}

.topic-form {
  padding-bottom: 16px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--line-soft);
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

.topic-form label,
.filter-bar label,
.derive-form label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
}

.topic-form label > span,
.filter-bar label > span,
.derive-form label > span {
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
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
.detail-actions,
.dialog-actions,
.report-drawer-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-md);
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
  padding: 10px 14px;
  background: var(--surface-strong);
  transition: all 140ms ease;
}

.secondary-btn:hover,
.secondary-link:hover {
  background: var(--surface);
  box-shadow: var(--shadow-subtle);
}

.ghost-btn,
.danger-btn,
.text-btn {
  padding: 10px 12px;
}

.text-btn {
  background: rgba(255, 255, 255, 0.22);
}

.danger-btn {
  background: var(--danger);
  border-color: var(--danger);
  color: #fff7f7;
}

.primary-link,
.secondary-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.icon-frame svg,
.report-back svg {
  width: 15px;
  height: 15px;
}

.report-entry,
.report-back {
  position: relative;
  flex-shrink: 0;
}

.report-entry-count {
  position: absolute;
  top: -3px;
  right: -3px;
  min-width: 14px;
  height: 14px;
  padding: 0 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--line-soft);
  border-radius: 999px;
  background: rgba(255, 250, 242, 0.96);
  color: var(--muted);
  font-size: 9px;
  line-height: 1;
}

.report-entry:hover,
.report-back:hover,
.rail-toggle:hover,
.quicklink-btn:hover {
  background: rgba(255, 255, 255, 0.7);
  box-shadow: var(--shadow-subtle);
}

.section-title {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-lg);
}

.section-title h2,
.section-title h3 {
  font-size: 14px;
  line-height: 1.2;
}

.side-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.side-block .section-title,
.topic-form .form-head,
.paper-stage .section-title {
  margin-bottom: 0;
}

.side-block .text-btn {
  padding: 4px 6px;
  border: none;
  background: transparent;
  color: var(--muted);
}

.side-block .text-btn:hover {
  color: var(--text);
}

.session-list,
.paper-list,
.match-list,
.variant-list,
.report-items,
.progress-list {
  list-style: none;
  padding: 0;
  margin: 0;
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
  border-left: 2px solid var(--line-soft);
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
  font-size: 16px;
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

.session-meta,
.muted,
.paper-authors,
.paper-summary,
.reading-copy,
.dialog-copy,
.detail-authors,
.detail-meta-line {
  color: var(--muted);
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

.utility-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 2px 2px 8px;
  border-bottom: 1px solid var(--line-soft);
  flex-shrink: 0;
}

.utility-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.utility-copy h2 {
  font-size: 18px;
  line-height: 1.16;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
}

.utility-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
}

.utility-meta-item {
  color: var(--muted);
  font-size: 11px;
}

.utility-meta-item::after {
  content: "\00b7";
  margin-left: 10px;
  color: var(--line);
}

.utility-meta-item:last-child::after {
  display: none;
}

.tool-layer {
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex-shrink: 0;
}

.tool-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.source-pill {
  min-width: 160px;
  max-width: 340px;
  min-height: 32px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 10px;
  border: 1px solid var(--line-soft);
  border-radius: 8px;
  background: rgba(250, 250, 248, 0.42);
  overflow: hidden;
}

.process-label {
  color: var(--muted);
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  white-space: nowrap;
}

.process-text {
  min-width: 0;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.35;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.metric-ring-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.metric-ring {
  --ring-progress: 0%;
  --ring-color: var(--ink-mark);
  position: relative;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid rgba(58, 52, 46, 0.08);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.24);
  display: inline-grid;
  place-items: center;
  flex-shrink: 0;
}

.metric-ring::before {
  content: "";
  position: absolute;
  inset: 3px;
  border-radius: 50%;
  background: conic-gradient(var(--ring-color) var(--ring-progress), rgba(58, 52, 46, 0.08) 0);
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 3px), #000 0);
  mask: radial-gradient(farthest-side, transparent calc(100% - 3px), #000 0);
}

.metric-ring::after {
  content: "";
  position: absolute;
  inset: 8px;
  border-radius: 50%;
  border: 1px solid rgba(58, 52, 46, 0.08);
  background: rgba(255, 250, 242, 0.88);
}

.metric-ring.tone-warning {
  --ring-color: var(--warning);
}

.metric-ring.tone-neutral {
  --ring-color: var(--ink-mark);
}

.metric-ring.tone-success {
  --ring-color: var(--success);
}

.metric-ring-core {
  position: relative;
  z-index: 1;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ring-color);
  opacity: 0.22;
  transition:
    opacity 140ms ease,
    transform 140ms ease;
}

.metric-tooltip {
  position: absolute;
  top: calc(100% + 8px);
  left: 50%;
  z-index: 8;
  min-width: 180px;
  max-width: 260px;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: rgba(250, 250, 248, 0.98);
  box-shadow: var(--shadow-medium);
  color: var(--text);
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-line;
  opacity: 0;
  transform: translateX(-50%) translateY(-4px);
  pointer-events: none;
  transition:
    opacity 140ms ease,
    transform 140ms ease;
}

.metric-tooltip strong,
.metric-tooltip-summary,
.metric-tooltip-detail {
  display: block;
}

.metric-tooltip strong {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.metric-tooltip-summary {
  margin-top: 3px;
  color: var(--muted);
  font-size: 11px;
}

.metric-tooltip-detail {
  margin-top: 4px;
}

.metric-ring:hover .metric-tooltip,
.metric-ring:focus-visible .metric-tooltip {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
}

.metric-ring:hover .metric-ring-core,
.metric-ring:focus-visible .metric-ring-core {
  opacity: 0.42;
  transform: scale(1.08);
}

.tool-actions {
  margin-left: auto;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.runtime-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 32px;
  padding: 0 10px;
  background: rgba(250, 250, 248, 0.42);
  border-color: var(--line-soft);
}

.runtime-trigger::after {
  content: "";
  width: 7px;
  height: 7px;
  border-right: 1px solid var(--accent);
  border-bottom: 1px solid var(--accent);
  transform: rotate(45deg);
  transition: transform 140ms ease;
}

.runtime-trigger.open::after {
  transform: rotate(225deg);
}

.runtime-trigger-label {
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}

.runtime-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.runtime-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px;
  border: 1px solid var(--line-soft);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.56);
  font-size: 11px;
  line-height: 1;
}

.process-detail-count,
.memo-badge,
.tone-chip,
.label-chip,
.query-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border: 1px solid var(--line-soft);
  background: var(--surface-strong);
  font-size: 12px;
}

.runtime-badge-warning {
  color: var(--warning);
  border-color: rgba(145, 106, 40, 0.28);
}

.runtime-tray {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: min(42vh, 420px);
  overflow-y: auto;
  padding-right: 4px;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
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

.process-subpanel {
  border: 1px solid var(--line-soft);
  background: rgba(250, 250, 248, 0.8);
  padding: 12px;
}

.process-subpanel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.process-subpanel-title {
  color: var(--text);
  font-size: 13px;
  font-weight: 600;
}

.process-subpanel ul {
  margin: 0;
  padding-left: 18px;
}

.query-board {
  padding: 12px;
}

.query-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.query-card {
  border: 1px solid var(--line-soft);
  border-left: 2px solid var(--line-soft);
  padding: 12px;
  background: var(--surface-strong);
}

.query-card-head,
.variant-head,
.paper-title-row,
.report-hero,
.inline-detail-top,
.inline-heading-top {
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

code,
.paper-rank,
.metric-value,
.report-draft {
  font-family: var(--font-mono);
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
  padding: 2px 2px 8px;
  flex-shrink: 0;
  overflow-x: auto;
  overflow-y: hidden;
}

.filter-bar .search-control {
  flex: 1 1 280px;
  min-width: 0;
}

.filter-bar label {
  flex: 0 0 auto;
  min-height: 36px;
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
}

.paper-list {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  border-top: 1px solid var(--line-soft);
}

.paper-stack {
  display: flex;
  flex-direction: column;
}

.paper-row {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr) 92px;
  gap: var(--space-lg);
  padding: 14px 8px 14px 14px;
  border-left: 2px solid var(--line-soft);
  border-bottom: 1px solid var(--line-soft);
  background: transparent;
  cursor: pointer;
  position: relative;
  transition: all 160ms ease;
}

.paper-row:hover {
  background: rgba(250, 250, 248, 0.58);
  box-shadow: var(--shadow-subtle);
}

.paper-row.active {
  background: rgba(250, 250, 248, 0.78);
  border-left: 3px solid var(--ink-mark);
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

.inline-detail-panel {
  padding: 0 10px 18px 78px;
  border-left: 3px solid var(--ink-mark);
  border-bottom: 1px solid var(--line-soft);
  background: var(--surface-muted);
}

.inline-detail-top {
  align-items: flex-start;
  padding: 16px 0 0;
}

.inline-detail-heading {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  flex: 1;
}

.inline-detail-heading h3 {
  font-size: 22px;
  line-height: 1.2;
}

.inline-heading-top {
  align-items: center;
}

.detail-meta-line {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  font-size: 12px;
  line-height: 1.45;
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

.detail-actions {
  align-items: flex-start;
}

.detail-actions .primary-link,
.detail-actions .secondary-link,
.cite-actions .secondary-link {
  padding: 8px 10px;
  font-size: 12px;
}

.detail-block {
  padding-top: 14px;
  margin-top: 14px;
  border-top: 1px solid var(--line-soft);
}

.reading-copy {
  line-height: 1.75;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.detail-section-title {
  align-items: center;
  margin-bottom: 10px;
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
  border: 1px solid var(--line-soft);
  background: var(--surface-strong);
  padding: 10px 12px;
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

.status-actions button.danger.active {
  color: #fff7f7;
  background: var(--danger);
  border-color: var(--danger);
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

.report-drawer-shell {
  position: absolute;
  inset: 0;
  display: flex;
  justify-content: flex-end;
  background: rgba(42, 38, 34, 0.08);
  backdrop-filter: blur(1px);
  z-index: 20;
}

.report-drawer {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.24), rgba(255, 255, 255, 0)),
    var(--surface);
  border-left: 1px solid var(--line-soft);
  box-shadow: -16px 0 36px rgba(25, 19, 14, 0.12);
}

.report-drawer-header {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 14px;
  align-items: center;
  padding: 14px 18px 12px;
  border-bottom: 1px solid var(--line-soft);
}

.report-drawer-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.report-drawer-copy h2 {
  font-size: 20px;
  line-height: 1.16;
}

.report-body {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  padding: 16px 18px 20px;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.report-drawer-actions {
  justify-content: flex-end;
  align-items: center;
}

.report-drawer-actions .secondary-btn,
.report-drawer-actions .text-btn {
  padding: 7px 10px;
  font-size: 12px;
}

.report-hero {
  align-items: flex-start;
  margin-bottom: 14px;
}

.report-heading {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.report-hero h2 {
  font-size: 24px;
  line-height: 1.18;
}

.memo-badge {
  color: var(--accent);
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
  background: var(--surface-strong);
}

.report-article {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.report-section {
  padding: 14px 0;
  border-top: 1px solid var(--line-soft);
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
  margin: 0;
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

.empty-action {
  margin-top: 12px;
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
  font-size: 26px;
}

.dialog-copy strong {
  color: var(--text);
}

.report-drawer-enter-active,
.report-drawer-leave-active {
  transition: opacity 180ms ease;
}

.report-drawer-enter-active .report-drawer,
.report-drawer-leave-active .report-drawer {
  transition:
    transform 220ms ease,
    opacity 220ms ease;
}

.report-drawer-enter-from,
.report-drawer-leave-to {
  opacity: 0;
}

.report-drawer-enter-from .report-drawer,
.report-drawer-leave-to .report-drawer {
  opacity: 0;
  transform: translateX(48px);
}

.inline-detail-enter-active,
.inline-detail-leave-active {
  overflow: hidden;
  transition:
    opacity 180ms ease,
    transform 180ms ease,
    max-height 220ms ease;
}

.inline-detail-enter-from,
.inline-detail-leave-to {
  opacity: 0;
  transform: translateY(-6px);
  max-height: 0;
}

.inline-detail-enter-to,
.inline-detail-leave-from {
  opacity: 1;
  transform: translateY(0);
  max-height: 1600px;
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

@media (max-width: 1180px) {
  .stage-shell {
    padding-inline: 18px;
  }
}

@media (max-width: 960px) {
  .workspace {
    display: flex;
    flex-direction: column;
    height: auto;
    min-height: 100vh;
    overflow: visible;
  }

  .left-rail,
  .stage-shell {
    height: auto;
    min-height: 0;
  }

  .left-rail {
    border-right: none;
    border-bottom: 1px solid var(--line-soft);
  }

  .stage-shell {
    overflow: visible;
  }

  .utility-bar,
  .inline-detail-top,
  .report-hero,
  .report-drawer-header {
    flex-direction: column;
    display: flex;
  }

  .query-grid {
    grid-template-columns: 1fr;
  }

  .tool-strip {
    align-items: stretch;
  }

  .source-pill {
    max-width: none;
  }

  .tool-actions {
    margin-left: 0;
    width: 100%;
    justify-content: flex-start;
  }

  .runtime-trigger {
    justify-content: space-between;
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

  .paper-stage {
    min-height: 420px;
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

  .inline-detail-panel {
    padding-left: 18px;
    padding-right: 18px;
  }

  .derive-form {
    grid-template-columns: 1fr;
  }

  .report-drawer-shell {
    position: fixed;
    inset: 0;
    padding-top: 12px;
    z-index: 40;
  }

  .report-drawer {
    width: 100%;
    height: calc(100% - 12px);
    border-left: none;
    border-top: 1px solid var(--line-soft);
  }
}
</style>
