  ---
  文献妙妙屋前端 UI 重构实施文档

  文档说明

  本文档基于 docs/frontend-redesign-yorha-inspired.zh-CN.md 中的设计方案，提供具体的代码修改位置和实施细节。所有修改集中在 frontend/src/App.vue 文件中。

  目标文件: frontend/src/App.vue (共 3254 行)

  ---
  Phase 1: 色彩与材质重构

  1.1 更新 CSS 变量体系

  位置: 第 1702-1733 行 .workspace 样式块

  当前代码:
  .workspace {
    --bg: #e8dfcf;
    --surface: rgba(243, 236, 225, 0.96);
    --surface-strong: rgba(250, 246, 238, 0.98);
    --line: #b2a388;
    --line-soft: rgba(90, 74, 52, 0.18);
    --text: #201a14;
    --muted: #6f6557;
    --accent: #4f4030;
    --accent-strong: #20160f;
    --success: #35573b;
    --warning: #916a28;
    --danger: #923939;
    --left-width: 288px;
    --right-width: 430px;
    height: 100vh;
    min-height: 100vh;
    overflow: hidden;
    display: grid;
    grid-template-columns: var(--left-width) minmax(0, 1fr) var(--right-width);
    color: var(--text);
    background:
      linear-gradient(180deg, rgba(255, 255, 255, 0.25), rgba(255, 255, 255, 0)),
      repeating-linear-gradient(
        0deg,
        rgba(90, 74, 52, 0.05) 0,
        rgba(90, 74, 52, 0.05) 1px,
        transparent 1px,
        transparent 34px
      ),
      var(--bg);
  }

  修改为:
  .workspace {
    /* 温灰色系 */
    --bg: #e8e6e2;
    --surface: #f4f3f0;
    --surface-strong: #fafaf8;

    /* 边框三级 */
    --line: rgba(58, 52, 46, 0.16);
    --line-soft: rgba(58, 52, 46, 0.08);
    --line-strong: rgba(58, 52, 46, 0.32);

    /* 文字 */
    --text: #2a2622;
    --muted: #89837c;

    /* 强调色 */
    --accent: #4a4238;
    --accent-strong: #363026;

    /* 功能色（低饱和） */
    --success: #4a5647;
    --warning: #6b5d45;
    --danger: #6b4a47;

    /* 记忆点色 */
    --ink-mark: #3d3530;
    --paper-edge: #d8d6d2;

    /* 布局 */
    --left-width: 280px;
    --right-width: 420px;

    height: 100vh;
    min-height: 100vh;
    overflow: hidden;
    display: grid;
    grid-template-columns: var(--left-width) minmax(0, 1fr) var(--right-width);
    color: var(--text);

    /* 纸纹理背景 */
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

  1.2 添加全局阴影系统

  位置: 在 <style scoped> 标签后立即添加（第 1701 行之后）

  新增代码:
  <style scoped>
  :root {
    --shadow-subtle: 0 2px 4px rgba(42, 38, 34, 0.08);
    --shadow-medium: 0 4px 12px rgba(42, 38, 34, 0.12);
    --shadow-strong: 0 12px 24px rgba(42, 38, 34, 0.18);
  }

  1.3 左右栏背景与阴影

  位置: 第 1743-1762 行

  当前代码:
  .left-rail,
  .right-rail {
    display: flex;
    flex-direction: column;
    background: rgba(238, 230, 217, 0.94);
    border-right: 1px solid var(--line-soft);
    overflow: hidden;
  }

  .right-rail {
    border-right: none;
    border-left: 1px solid var(--line-soft);
  }

  修改为:
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
    box-shadow: 2px 0 8px rgba(42, 38, 34, 0.04);
  }

  1.4 中栏背景调整

  位置: 第 1764-1772 行

  当前代码:
  .center-stage {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 22px 24px 24px;
    min-height: 0;
    overflow: hidden;
    background: rgba(252, 248, 241, 0.36);
  }

  修改为:
  .center-stage {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 22px 24px 24px;
    min-height: 0;
    overflow: hidden;
    background: transparent;
  }

  ---
  Phase 2: 论文列表记忆点（核心特性）

  2.1 论文行左侧竖线系统

  位置: 第 2689-2721 行 .paper-row

  当前代码:
  .paper-row {
    display: grid;
    grid-template-columns: 64px minmax(0, 1fr) 92px;
    gap: 12px;
    padding: 14px 8px 14px 10px;
    border: none;
    border-bottom: 1px solid var(--line-soft);
    background: transparent;
    cursor: pointer;
    position: relative;
  }

  .paper-row::before {
    content: "";
    position: absolute;
    left: 0;
    top: 10px;
    bottom: 10px;
    width: 2px;
    background: transparent;
  }

  .paper-row:hover {
    background: rgba(255, 248, 236, 0.54);
  }

  .paper-row.active {
    background: rgba(255, 244, 224, 0.78);
  }

  .paper-row.active::before {
    background: var(--accent);
  }

  修改为:
  .paper-row {
    display: grid;
    grid-template-columns: 64px minmax(0, 1fr) 92px;
    gap: 12px;
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

  说明: 移除 ::before 伪元素，改用 border-left 实现竖线，选中时加粗到 3px 并使用墨色。

  2.2 论文编号改造

  位置: 第 2727-2732 行 .paper-rank

  当前代码:
  .paper-rank {
    font-size: 28px;
    line-height: 1;
    font-family: Georgia, "Times New Roman", serif;
    color: var(--accent);
  }

  修改为:
  .paper-rank {
    font-size: 14px;
    line-height: 1.2;
    font-family: var(--font-mono);
    color: var(--ink-mark);
    font-weight: 500;
    min-width: 32px;
  }

  2.3 模板中编号格式化

  位置: 第 285 行左右（模板部分）

  当前代码:
  <div class="paper-rank">{{ paper.rank }}</div>

  修改为:
  <div class="paper-rank">{{ String(paper.rank).padStart(2, '0') }}</div>

  ---
  Phase 3: 右侧详情纸边线

  3.1 Detail Hero 顶部纸边线

  位置: 第 2822-2826 行

  当前代码:
  .detail-hero,
  .report-hero {
    align-items: flex-start;
    margin-bottom: 12px;
  }

  修改为:
  .detail-hero,
  .report-hero {
    align-items: flex-start;
    margin-bottom: 12px;
    border-top: 2px solid var(--paper-edge);
    padding-top: 16px;
  }

  ---
  Phase 4: 左栏历史会话轻量化

  4.1 会话项去背景框

  位置: 第 2202-2215 行

  当前代码:
  .session-item {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 2px;
    align-items: stretch;
    border: none;
    border-left: 2px solid transparent;
    background: transparent;
  }

  .session-item.active {
    border-color: var(--accent);
    background: rgba(255, 245, 229, 0.68);
  }

  修改为:
  .session-item {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 2px;
    align-items: stretch;
    border: none;
    border-left: 2px solid var(--line-soft);
    background: transparent;
    padding-left: 8px;
    transition: all 140ms ease;
  }

  .session-item.active {
    border-left: 3px solid var(--ink-mark);
    background: rgba(250, 250, 248, 0.6);
  }

  4.2 品牌区压缩

  位置: 第 1854-1863 行

  当前代码:
  .brand-lockup h1 {
    font-size: 24px;
    line-height: 1.1;
  }

  .brand-copy {
    font-size: 11px;
    line-height: 1.4;
    max-width: 22ch;
  }

  修改为:
  .brand-lockup h1 {
    font-size: 20px;
    line-height: 1.1;
  }

  .brand-copy {
    font-size: 10px;
    line-height: 1.4;
    max-width: 22ch;
  }

  模板位置: 第 11-17 行

  当前代码:
  <div class="brand-lockup" :class="{ compact: !leftSidebarOpen }">
    <div class="brand-mark">MM</div>
    <div v-if="leftSidebarOpen">
      <p class="eyebrow">Miaowen Workbench</p>
      <h1>文献妙妙屋</h1>
      <p class="brand-copy">以筛选、阅读、判断为中心的 AI/CS 文献工作台。</p>
    </div>
  </div>

  修改为:
  <div class="brand-lockup" :class="{ compact: !leftSidebarOpen }">
    <div class="brand-mark">MM</div>
    <div v-if="leftSidebarOpen">
      <h1>文献妙妙屋</h1>
      <p class="brand-eyebrow">MIAOWEN LITERATURE WORKBENCH</p>
    </div>
  </div>

  新增样式 (在 .brand-copy 后添加):
  .brand-eyebrow {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
    line-height: 1.3;
  }

  ---
  Phase 5: 中栏顶部压缩

  5.1 会话头部压缩

  位置: 第 2412-2442 行

  当前代码:
  .stage-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    border-bottom: 1px solid var(--line-soft);
    padding-bottom: 8px;
    flex-shrink: 0;
  }

  .stage-heading h2 {
    font-size: 22px;
    line-height: 1.15;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  修改为:
  .stage-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    border-bottom: 1px solid var(--line-soft);
    padding-bottom: 12px;
    flex-shrink: 0;
  }

  .stage-heading h2 {
    font-size: 20px;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  5.2 Meta 信息字号

  位置: 第 2454-2458 行

  当前代码:
  .stage-meta-line,
  .stage-subtitle {
    font-size: 12px;
    line-height: 1.4;
  }

  修改为:
  .stage-meta-line,
  .stage-subtitle {
    font-size: 11px;
    line-height: 1.4;
  }

  5.3 Filter Bar 一行化

  位置: 第 2626-2659 行

  当前代码:
  .filter-bar {
    display: grid;
    grid-template-columns: minmax(260px, 1.6fr) repeat(3, minmax(0, 0.72fr));
    gap: 8px;
    padding: 8px 10px;
    flex-shrink: 0;
  }

  .filter-bar label {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: 8px;
    min-height: 42px;
    padding: 0 10px;
    border: 1px solid var(--line-soft);
    background: rgba(255, 249, 240, 0.94);
    font-weight: 500;
  }

  修改为:
  .filter-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    flex-shrink: 0;
    border: none;
    border-bottom: 1px solid var(--line-soft);
    background: transparent;
  }

  .filter-bar label {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 6px;
    min-height: 36px;
    padding: 0;
    border: none;
    background: transparent;
    font-weight: 500;
  }

  .filter-bar label:first-child {
    flex: 1;
  }

  .filter-bar label span {
    color: var(--muted);
    font-size: 11px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    white-space: nowrap;
  }

  .filter-bar select {
    width: auto;
    min-width: 100px;
  }

  ---
  Phase 6: 字体系统完善

  6.1 引入字体栈变量

  位置: 在 :root 块中添加（第 1701 行后）

  新增代码:
  :root {
    --font-sans: 'Inter', -apple-system, 'Helvetica Neue', sans-serif;
    --font-serif: 'Iowan Old Style', 'Palatino', Georgia, serif;
    --font-mono: 'JetBrains Mono', 'SF Mono', Consolas, 'Cascadia Code', monospace;

    --shadow-subtle: 0 2px 4px rgba(42, 38, 34, 0.08);
    --shadow-medium: 0 4px 12px rgba(42, 38, 34, 0.12);
    --shadow-strong: 0 12px 24px rgba(42, 38, 34, 0.18);
  }

  6.2 字号层级变量

  位置: 在 :root 块中继续添加

  :root {
    /* 字体栈 */
    --font-sans: 'Inter', -apple-system, 'Helvetica Neue', sans-serif;
    --font-serif: 'Iowan Old Style', 'Palatino', Georgia, serif;
    --font-mono: 'JetBrains Mono', 'SF Mono', Consolas, 'Cascadia Code', monospace;

    /* 阴影 */
    --shadow-subtle: 0 2px 4px rgba(42, 38, 34, 0.08);
    --shadow-medium: 0 4px 12px rgba(42, 38, 34, 0.12);
    --shadow-strong: 0 12px 24px rgba(42, 38, 34, 0.18);

    /* 字号层级 */
    --text-2xs: 9px;
    --text-xs: 10px;
    --text-sm: 11px;
    --text-base: 13px;
    --text-md: 14px;
    --text-lg: 15px;
    --text-xl: 18px;
    --text-2xl: 20px;
  }

  6.3 应用字体变量

  位置: 第 1847-1852 行附近

  修改已有 Serif 声明:
  .brand-lockup h1,
  .stage-heading h2,
  .detail-hero h2,
  .report-hero h2 {
    font-family: var(--font-serif);
  }

  新增 Mono 应用 (在 Serif 声明后):
  .paper-rank,
  code,
  .query-card code {
    font-family: var(--font-mono);
  }

  6.4 Code 块字体更新

  位置: 第 2615-2624 行

  当前代码:
  code {
    display: block;
    margin: 8px 0 6px;
    padding: 8px 10px;
    border: 1px solid var(--line-soft);
    background: rgba(247, 242, 233, 0.96);
    font-family: "Cascadia Code", Consolas, monospace;
    font-size: 12px;
    overflow-wrap: anywhere;
  }

  修改为:
  code {
    display: block;
    margin: 8px 0 6px;
    padding: 8px 10px;
    border: 1px solid var(--line-soft);
    background: var(--surface-strong);
    font-family: var(--font-mono);
    font-size: 12px;
    overflow-wrap: anywhere;
  }

  ---
  Phase 7: 间距系统规范化

  7.1 建立间距变量

  位置: 在 :root 块中添加

  :root {
    /* 字体栈 */
    --font-sans: 'Inter', -apple-system, 'Helvetica Neue', sans-serif;
    --font-serif: 'Iowan Old Style', 'Palatino', Georgia, serif;
    --font-mono: 'JetBrains Mono', 'SF Mono', Consolas, 'Cascadia Code', monospace;

    /* 阴影 */
    --shadow-subtle: 0 2px 4px rgba(42, 38, 34, 0.08);
    --shadow-medium: 0 4px 12px rgba(42, 38, 34, 0.12);
    --shadow-strong: 0 12px 24px rgba(42, 38, 34, 0.18);

    /* 字号 */
    --text-2xs: 9px;
    --text-xs: 10px;
    --text-sm: 11px;
    --text-base: 13px;
    --text-md: 14px;
    --text-lg: 15px;
    --text-xl: 18px;
    --text-2xl: 20px;

    /* 间距 */
    --space-2xs: 2px;
    --space-xs: 4px;
    --space-sm: 6px;
    --space-md: 8px;
    --space-lg: 12px;
    --space-xl: 16px;
    --space-2xl: 24px;
    --space-3xl: 32px;
  }

  7.2 应用间距变量（示例）

  位置: 多处需要替换

  替换规则：
  - gap: 2px → gap: var(--space-2xs)
  - gap: 6px → gap: var(--space-sm)
  - gap: 8px → gap: var(--space-md)
  - gap: 10px → gap: var(--space-md) 或 gap: var(--space-lg) (视觉调整)
  - gap: 12px → gap: var(--space-lg)
  - gap: 16px → gap: var(--space-xl)
  - margin-top: 12px → margin-top: var(--space-lg)

  关键位置示例:
  - .center-stage (1764 行): gap: 12px → gap: var(--space-xl)
  - .paper-list (2677 行): gap: 0 保持不变
  - .detail-actions (2878 行): gap: 10px → gap: var(--space-md)
  - .side-block + .side-block (2034 行): margin-top: 12px → margin-top: var(--space-lg)

  ---
  Phase 8: 其他细节优化

  8.1 输入框背景统一

  位置: 第 2118-2129 行

  当前代码:
  textarea,
  input,
  select {
    width: 100%;
    border: 1px solid var(--line);
    border-radius: 6px;
    background: rgba(255, 251, 243, 0.92);
    padding: 10px 12px;
    color: var(--text);
    font: inherit;
    box-sizing: border-box;
  }

  修改为:
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

  8.2 按钮背景调整

  位置: 第 1913-1925 行

  当前代码:
  .primary-btn,
  .primary-link {
    padding: 11px 14px;
    background: var(--accent-strong);
    color: #f8f1e5;
    border-color: var(--accent-strong);
  }

  .secondary-btn,
  .secondary-link {
    padding: 11px 14px;
    background: rgba(255, 251, 243, 0.9);
  }

  修改为:
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

  8.3 卡片与面板背景统一

  位置: 多处，搜索 rgba(255, 250, 242 和 rgba(255, 251, 243 并替换为语义化变量

  替换规则：
  - rgba(255, 250, 242, 0.92) → var(--surface-strong)
  - rgba(255, 251, 243, 0.92) → var(--surface-strong)
  - rgba(255, 250, 242, 0.82) → var(--surface)
  - 透明背景酌情保持或改为 transparent

  关键位置:
  - .status-pill (2307 行)
  - .cite-box (2914 行)
  - .match-list li (2976 行)
  - .report-toc button (3014 行)

  ---
  验证清单

  实施完成后，检查以下关键视觉效果：

  视觉验证

  1. 色调: 整体从暖米色变为温灰色，更冷静克制
  2. 纸纹理: 背景有 32px 横向极淡线条
  3. 论文行: 左侧有 2px 灰线，选中时变 3px 墨色粗线
  4. 编号: 14px 等宽字体，双位数补零（01, 02...）
  5. 右侧详情: 顶部有 2px 浅色纸边线
  6. 左栏历史: 无背景框，仅左侧竖线，选中时加粗
  7. 阴影: hover 时卡片有微妙阴影提升
  8. 品牌区: 标题 20px，副标题小写改为大写英文

  功能验证

  1. 点击论文 → 右侧详情正常显示，纸边线出现
  2. 选中/取消论文 → 左侧竖线正常切换粗细
  3. 窄屏（≤1180px） → 右栏抽屉化，样式不崩溃
  4. 移动端（≤960px） → 左栏收起，布局正常

  响应式检查

  - 1360px: 左栏 270px，右栏 380px
  - 1180px: 右栏改为抽屉
  - 960px: 单栏布局

  ---
  风险提示

  1. 色彩接受度: 温灰色比原暖米色更冷静，部分用户可能觉得"不够温暖"
  2. 编号辨识度: 小编号 + 左侧竖线不如大 Serif 编号醒目，但整体更克制
  3. 阴影性能: 大量 box-shadow 在低端设备可能有轻微性能影响
  4. 字体依赖: Inter、JetBrains Mono 等字体需用户系统支持，否则降级到系统默认

  ---
  实施建议

  1. 分阶段提交: 建议按 Phase 1 → 2 → 3 ... 顺序逐步实施，便于回滚
  2. 保留原色彩: 可考虑保留原暖米色方案为"温暖主题"，新温灰色为"克制主题"，未来支持切换
  3. 性能监控: 实施后在低端设备测试，如有性能问题可减少阴影使用
  4. 用户反馈: 收集真实用户对新视觉的反馈，必要时微调色值

  ---
  总结

  本重构方案聚焦视觉升级，不改变任何功能逻辑和数据流。核心改进：

  1. 色彩: 暖米色 → 温灰中性色，