<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { ArrowRight, Check, Connection, Document, Search, Close } from '@element-plus/icons-vue'
import BrandLogo from '@/components/layout/BrandLogo.vue'
import AppContainer from '@/components/ui/AppContainer.vue'
import AppSection from '@/components/ui/AppSection.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppCard from '@/components/ui/AppCard.vue'
import AppTypography from '@/components/ui/AppTypography.vue'
import { useReveal } from '@/composables/useReveal'

const root = useReveal()
const scrolled = ref(false)
const menuOpen = ref(false)
const menuToggle = ref<HTMLButtonElement>()
const activeTab = ref<'clause' | 'risk' | 'suggestion'>('risk')
const accepted = ref(false)
const tabs = [
  { id: 'clause', label: '条款原文' },
  { id: 'risk', label: '风险分析' },
  { id: 'suggestion', label: '修改建议' },
] as const
const features = [
  { icon: Connection, number: '01', title: '多智能体编排', description: 'LangGraph 意图识别 / 专家并行 / 仲裁' },
  { icon: Search, number: '02', title: '混合检索 RAG', description: '法规 / 校内制度 / 合同模板三层知识库' },
  { icon: Document, number: '03', title: '流式审阅', description: 'SSE 实时输出风险点与修改建议' },
]
const swatches = [
  { name: '画布', value: '#FFFFFF', token: 'canvas' },
  { name: '分区', value: '#FAFAFA', token: 'surface' },
  { name: '主文本', value: '#0A0A0A', token: 'text' },
  { name: '强调色', value: '#2563EB', token: 'accent' },
]
function updateScroll() { scrolled.value = window.scrollY > 16 }
function closeMenu(event: KeyboardEvent) {
  if (event.key === 'Escape' && menuOpen.value) {
    menuOpen.value = false
    menuToggle.value?.focus()
  }
}
onMounted(() => {
  updateScroll()
  window.addEventListener('scroll', updateScroll, { passive: true })
  window.addEventListener('keydown', closeMenu)
})
onUnmounted(() => {
  window.removeEventListener('scroll', updateScroll)
  window.removeEventListener('keydown', closeMenu)
})
</script>

<template>
  <div ref="root" class="design-system demo">
    <a href="#main" class="skip-link">跳转到主要内容</a>
    <header class="demo-nav" :class="{ 'is-scrolled': scrolled }">
      <AppContainer class="nav-inner">
        <a class="brand" href="#main" aria-label="高校合同智能审阅系统 · 设计预览">
          <span class="brand-symbol" aria-hidden="true"><BrandLogo /></span>
          <span>Contract Review<span class="brand-caption">设计预览 / 阶段 02</span></span>
        </a>
        <nav class="desktop-nav" aria-label="预览导航">
          <a href="#capabilities">核心能力</a><a href="#workbench">审阅工作台</a><a href="#components">基础组件</a>
        </nav>
        <AppButton class="nav-cta" size="small" href="#components" variant="secondary">查看组件 <ArrowRight class="inline-icon" /></AppButton>
        <button ref="menuToggle" class="menu-toggle" type="button" :aria-expanded="menuOpen" aria-controls="mobile-navigation" :aria-label="menuOpen ? '关闭导航' : '打开导航'" @click="menuOpen = !menuOpen"><Close v-if="menuOpen" /><span v-else class="menu-lines" aria-hidden="true"><i /><i /><i /></span></button>
      </AppContainer>
      <nav v-if="menuOpen" id="mobile-navigation" class="mobile-nav" aria-label="移动端预览导航" @click="menuOpen = false">
        <a href="#capabilities">核心能力</a><a href="#workbench">审阅工作台</a><a href="#components">基础组件</a>
      </nav>
    </header>

    <main id="main" tabindex="-1">
      <AppSection class="hero" aria-labelledby="hero-title">
        <AppContainer>
          <div class="hero-layout">
            <div class="hero-copy">
              <AppTypography variant="eyebrow" tone="secondary" class="hero-eyebrow"><span class="accent-dot" /> Contract Review Agent</AppTypography>
              <AppTypography id="hero-title" as="h1" variant="hero">高校合同<br />智能审阅系统</AppTypography>
              <AppTypography class="hero-description" variant="lead" tone="secondary">流式审阅 · SSE 实时输出<br class="desktop-break" />风险点与修改建议</AppTypography>
              <div class="hero-actions">
                <AppButton size="large" href="#workbench">智能审阅 <ArrowRight class="inline-icon" /></AppButton>
                <AppButton size="large" variant="secondary" href="#components">查看设计系统</AppButton>
              </div>
              <AppTypography variant="caption" tone="muted" class="hero-note">采购合同管理场景</AppTypography>
            </div>
            <div class="hero-art" role="img" aria-label="合同审阅界面示意，非真实审阅结果">
              <div class="art-grid" aria-hidden="true" />
              <div class="art-orbit" aria-hidden="true" />
              <div class="art-index" aria-hidden="true">合同 / 审阅</div>
              <div class="document-sheet">
                <div class="document-meta"><span><Document class="inline-icon" /> 合同文件</span><span>示例</span></div>
                <div class="document-title">采购合同</div>
                <div class="document-rule" />
                <div class="document-lines" aria-hidden="true"><i /><i /><i class="short" /></div>
                <div class="document-highlight"><span>付款条款</span><div class="document-lines" aria-hidden="true"><i /><i class="short" /></div></div>
                <div class="document-lines" aria-hidden="true"><i /><i /><i class="short" /></div>
                <div class="document-signature"><span>甲方</span><span>乙方</span></div>
              </div>
              <div class="floating-insight">
                <span class="insight-icon"><Search /></span>
                <div><strong>风险点与证据</strong><span>条款原文 · 修改建议</span></div>
                <span class="insight-number" aria-hidden="true">↗</span>
              </div>
              <div class="art-label"><span class="accent-dot" /> 多智能体并行审阅 <span class="art-label-line" /></div>
            </div>
          </div>
          <div class="preview-disclaimer"><span>独立设计预览</span><p>示例内容，不连接业务接口。现有页面、路由与数据流保持不变。</p><span class="disclaimer-index" aria-hidden="true">01 — 03</span></div>
        </AppContainer>
      </AppSection>

      <AppSection id="capabilities" tone="muted" aria-labelledby="capabilities-title">
        <AppContainer>
          <div class="section-heading" data-reveal>
            <AppTypography variant="eyebrow" tone="muted">01 / 核心能力</AppTypography>
            <AppTypography id="capabilities-title" as="h2" variant="section">合同智能审阅</AppTypography>
            <AppTypography tone="secondary">多智能体编排 · 混合检索 RAG · 流式审阅</AppTypography>
          </div>
          <div class="feature-grid">
            <AppCard v-for="(feature, index) in features" :key="feature.number" padding="large" class="feature-card" data-reveal :style="{ '--reveal-order': index }">
              <div class="feature-top"><span class="feature-icon"><component :is="feature.icon" /></span><span class="feature-number">{{ feature.number }}</span></div>
              <AppTypography as="h3" variant="card">{{ feature.title }}</AppTypography>
              <AppTypography tone="secondary">{{ feature.description }}</AppTypography>
              <div class="feature-rule" aria-hidden="true" />
            </AppCard>
          </div>
        </AppContainer>
      </AppSection>

      <AppSection id="workbench" tone="inverse" class="workbench-section" aria-labelledby="workbench-title">
        <AppContainer>
          <div class="section-heading workbench-heading" data-reveal>
            <AppTypography variant="eyebrow" tone="muted">02 / 产品交互</AppTypography>
            <AppTypography id="workbench-title" as="h2" variant="section">智能审阅工作台</AppTypography>
            <AppTypography tone="secondary">业务信息保留密度，视觉层次更加清晰。</AppTypography>
          </div>
          <div class="workbench" data-reveal>
            <aside class="workbench-sidebar" aria-label="示例合同">
              <div class="workbench-brand"><BrandLogo class="inline-icon" /> 合同审阅</div>
              <span class="sidebar-label">合同文件</span>
              <div class="sidebar-file"><Document class="inline-icon" /><span>采购合同<small>示例文件</small></span></div>
              <div class="sidebar-bottom"><span class="accent-dot" /> 设计系统预览</div>
            </aside>
            <div class="workbench-content">
              <div class="workbench-topbar"><span>智能审阅 <span class="breadcrumb-divider">/</span> 采购合同</span><span class="sample-badge">示例</span></div>
              <div class="workbench-body">
                <div class="review-heading"><div><AppTypography as="h3" variant="card">风险点与修改建议</AppTypography><AppTypography variant="small" tone="secondary">违约责任 · 示例风险点</AppTypography></div><span class="review-index">01</span></div>
                <div class="review-tabs" role="group" aria-label="风险点内容">
                  <button v-for="tab in tabs" :key="tab.id" type="button" :aria-pressed="activeTab === tab.id" :class="{ active: activeTab === tab.id }" aria-controls="review-detail" @click="activeTab = tab.id">{{ tab.label }}</button>
                </div>
                <div id="review-detail" class="review-detail" aria-live="polite">
                  <template v-if="activeTab === 'clause'"><span class="detail-label">条款原文 · 示例</span><p>乙方逾期付款按日万分之五支付违约金。</p></template>
                  <template v-else-if="activeTab === 'risk'"><span class="detail-label">风险分析 · 示例</span><p>违约金计算基数不明确。</p><div class="evidence-row"><Document class="inline-icon" /><span>付款条款</span><span class="evidence-caption">条款原文</span></div></template>
                  <template v-else><span class="detail-label">修改建议 · 示例</span><p>明确违约金计算基数。</p></template>
                </div>
                <div class="review-footer"><AppTypography variant="caption" tone="muted">仅演示组件状态，不保存数据</AppTypography><AppButton size="small" :variant="accepted ? 'secondary' : 'primary'" :aria-pressed="accepted" @click="accepted = !accepted"><Check v-if="accepted" class="inline-icon" />{{ accepted ? '已采纳' : '采纳建议' }}</AppButton></div>
              </div>
            </div>
          </div>
        </AppContainer>
      </AppSection>

      <AppSection id="components" aria-labelledby="components-title">
        <AppContainer>
          <div class="section-heading" data-reveal>
            <AppTypography variant="eyebrow" tone="muted">03 / 设计地基</AppTypography>
            <AppTypography id="components-title" as="h2" variant="section">统一，而不单调。</AppTypography>
            <AppTypography tone="secondary">颜色、排版、间距与交互，共用一套设计语言。</AppTypography>
          </div>
          <div class="foundation-grid">
            <AppCard padding="large" class="foundation-card" data-reveal>
              <div class="card-heading"><AppTypography as="h3" variant="card">色彩</AppTypography><AppTypography variant="caption" tone="muted">中性色 + 一个强调色</AppTypography></div>
              <div class="swatches"><div v-for="swatch in swatches" :key="swatch.token" class="swatch"><span class="swatch-color" :class="`swatch-color--${swatch.token}`" /><span>{{ swatch.name }}</span><code>{{ swatch.value }}</code></div></div>
            </AppCard>
            <AppCard padding="large" class="foundation-card" data-reveal>
              <div class="card-heading"><AppTypography as="h3" variant="card">按钮</AppTypography><AppTypography variant="caption" tone="muted">160ms · 轻微上移</AppTypography></div>
              <div class="button-samples"><AppButton href="#workbench">主要操作</AppButton><AppButton variant="secondary" href="#workbench">次要操作</AppButton><AppButton variant="ghost" href="#workbench">文字操作 <ArrowRight class="inline-icon" /></AppButton><AppButton loading>处理中</AppButton><AppButton disabled>暂不可用</AppButton></div>
              <AppTypography variant="caption" tone="muted">支持键盘焦点、加载态与禁用态。</AppTypography>
            </AppCard>
            <AppCard padding="large" class="type-card foundation-card" data-reveal>
              <div class="card-heading"><AppTypography as="h3" variant="card">排版</AppTypography><AppTypography variant="caption" tone="muted">Inter / 中文系统字体</AppTypography></div>
              <div class="type-specimen"><span class="type-specimen-large">Aa<span>字</span></span><div><AppTypography variant="lead">高校合同智能审阅系统</AppTypography><AppTypography variant="small" tone="secondary">Contract Review Agent</AppTypography><span class="numeric-specimen">0123456789</span></div></div>
              <div class="type-scale"><span>标题 72 / 44 / 24</span><span>正文 18 / 16 / 14</span><span>等宽数字 · tnum</span></div>
            </AppCard>
            <AppCard padding="large" class="foundation-card" tone="soft" data-reveal>
              <div class="card-heading"><AppTypography as="h3" variant="card">空间与层次</AppTypography><AppTypography variant="caption" tone="muted">4px 基准</AppTypography></div>
              <div class="space-specimen" aria-hidden="true"><span /><span /><span /><span /><span /></div>
              <div class="space-labels"><span>8</span><span>16</span><span>24</span><span>32</span><span>48</span></div>
              <AppTypography variant="caption" tone="muted">圆角 8 / 16 / 24 · 轻边框 · 单次渐入</AppTypography>
            </AppCard>
          </div>
        </AppContainer>
      </AppSection>
    </main>

    <AppContainer as="footer" class="demo-footer"><span class="footer-brand"><BrandLogo class="inline-icon" /> 高校合同智能审阅系统</span><AppTypography variant="caption" tone="muted">阶段 02 · 设计 token 与基础组件预览</AppTypography><a href="#main">返回顶部 ↑</a></AppContainer>
  </div>
</template>

<style scoped>
.demo { --art-sheet-width: 320px; --art-sheet-height: 360px; --art-insight-width: 296px; --workbench-sidebar-width: 200px; --font-art-number: 28px; --art-title-size: 28px; --type-specimen-size: 80px; --art-line-color: rgb(10 10 10 / 8%); }
.inline-icon { width: var(--space-4); height: var(--space-4); vertical-align: middle; }
.app-button .inline-icon { margin-left: var(--space-2); }
.demo-nav { position: fixed; inset: 0 0 auto; z-index: 20; min-height: var(--nav-height); transition: background var(--duration-normal) var(--ease-out), border-color var(--duration-normal) var(--ease-out); border-bottom: var(--border-width) solid transparent; }
.demo-nav.is-scrolled { background: var(--color-glass); border-color: var(--color-border); backdrop-filter: blur(var(--blur-glass)); }
.nav-inner { min-height: var(--nav-height); display: flex; align-items: center; justify-content: space-between; gap: var(--space-6); }
.brand { display: flex; align-items: center; gap: var(--space-3); font-size: var(--font-small); font-weight: var(--weight-semibold); line-height: 1.4; white-space: nowrap; }
.brand-symbol { --brand-mark-cutout: var(--color-inverse); width: var(--space-10); height: var(--space-10); border-radius: var(--radius-button); background: var(--color-inverse); color: var(--color-on-inverse); display: grid; place-items: center; }
.brand-symbol svg { width: var(--icon-size); height: var(--icon-size); }
.brand-caption { display: block; color: var(--color-muted); font-size: var(--font-caption); font-weight: var(--weight-regular); margin-top: var(--space-1); }
.desktop-nav, .nav-cta { display: none; }
.menu-toggle { display: grid; place-items: center; width: var(--button-height); height: var(--button-height); color: var(--color-text); background: transparent; border: 0; border-radius: var(--radius-button); cursor: pointer; }
.menu-toggle svg { width: var(--space-6); height: var(--space-6); }
.menu-lines { display: grid; gap: var(--space-1); width: var(--space-6); }
.menu-lines i { display: block; height: 2px; border-radius: var(--radius-pill); background: currentColor; }
.mobile-nav { padding: var(--space-3) var(--gutter) var(--space-6); background: var(--color-canvas); border-bottom: var(--border-width) solid var(--color-border); }
.mobile-nav a { display: block; padding-block: var(--space-3); }
.hero { padding-top: calc(var(--nav-height) + var(--space-12)); padding-bottom: 0; overflow: hidden; }
.hero-layout { display: grid; gap: var(--space-8); }
.hero-copy { position: relative; z-index: 1; }
.hero-eyebrow { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-6); }
.accent-dot { display: inline-block; width: var(--space-2); height: var(--space-2); border-radius: var(--radius-pill); background: var(--color-accent); flex-shrink: 0; }
.hero-description { margin-top: var(--space-6); }
.hero-actions { display: flex; flex-wrap: wrap; gap: var(--space-3); margin-top: var(--space-8); }
.hero-note { margin-top: var(--space-6); }
.hero-eyebrow, .hero-description, .hero-actions, .hero-note, .hero-art { animation: hero-enter var(--duration-enter) var(--ease-out) both; }
.hero-description { animation-delay: var(--stagger-step); }
.hero-actions, .hero-art { animation-delay: calc(var(--stagger-step) * 2); }
.hero-note { animation-delay: calc(var(--stagger-step) * 3); }
@keyframes hero-enter { from { opacity: 0; transform: translateY(var(--reveal-offset)); } to { opacity: 1; transform: none; } }
.hero-art { position: relative; min-width: 0; height: var(--hero-art-height); display: grid; place-items: center; isolation: isolate; }
.hero-art::before { content: ''; position: absolute; inset: 0 calc(-1 * var(--space-10)); z-index: -2; background: radial-gradient(ellipse at 60% 45%, var(--color-accent-glow), transparent 70%); }
.art-grid { position: absolute; inset: 0; z-index: -1; background-image: linear-gradient(var(--color-border) 1px, transparent 1px), linear-gradient(90deg, var(--color-border) 1px, transparent 1px); background-size: var(--grid-size) var(--grid-size); mask-image: radial-gradient(ellipse, black 15%, transparent 72%); }
.art-orbit { position: absolute; width: 88%; aspect-ratio: 1; border: var(--border-width) solid var(--color-border); border-radius: 50%; z-index: -1; }
.art-index { position: absolute; top: var(--space-6); left: var(--space-5); font-size: var(--font-caption); color: var(--color-muted); letter-spacing: var(--tracking-label); }
.document-sheet { width: var(--art-sheet-width); max-width: 85%; height: var(--art-sheet-height); padding: var(--space-6); border: var(--border-width) solid var(--color-border-hover); background: var(--color-canvas); border-radius: var(--radius-card); transform: rotate(-5deg); }
.document-meta { display: flex; justify-content: space-between; align-items: center; color: var(--color-secondary); font-size: var(--font-caption); }
.document-meta > span:first-child { display: flex; align-items: center; gap: var(--space-2); }
.document-title { font-size: var(--art-title-size); letter-spacing: var(--tracking-heading); font-weight: var(--weight-semibold); margin-top: var(--space-6); }
.document-rule { height: 1px; background: var(--color-border); margin-block: var(--space-4); }
.document-lines { display: grid; gap: var(--space-2); }
.document-lines i { height: var(--space-1); width: 100%; border-radius: var(--radius-pill); background: var(--art-line-color); }
.document-lines .short { width: 65%; }
.document-highlight { padding: var(--space-3); margin: var(--space-4) calc(-1 * var(--space-3)); background: var(--color-accent-soft); border-left: 2px solid var(--color-accent); }
.document-highlight > span { display: block; font-size: var(--font-caption); font-weight: var(--weight-medium); margin-bottom: var(--space-3); }
.document-signature { display: flex; justify-content: space-between; margin-top: var(--space-6); font-size: var(--font-caption); color: var(--color-muted); }
.floating-insight { position: absolute; right: 0; bottom: var(--space-20); width: var(--art-insight-width); max-width: 95%; display: flex; align-items: center; gap: var(--space-3); padding: var(--space-5); background: var(--color-inverse); color: var(--color-on-inverse); border: var(--border-width) solid var(--color-border); border-radius: var(--radius-card); box-shadow: var(--shadow-float); }
.insight-icon { display: grid; place-items: center; width: var(--space-10); height: var(--space-10); border-radius: var(--radius-button); background: var(--color-accent); }
.insight-icon svg { width: var(--icon-size); height: var(--icon-size); }
.floating-insight strong { display: block; font-size: var(--font-small); font-weight: var(--weight-medium); }
.floating-insight div > span { display: block; font-size: var(--font-caption); color: var(--color-on-inverse); opacity: .65; margin-top: var(--space-1); }
.insight-number { margin-left: auto; font-size: var(--font-art-number); }
.art-label { position: absolute; bottom: var(--space-5); inset-inline: var(--space-5); display: flex; align-items: center; gap: var(--space-3); font-size: var(--font-caption); color: var(--color-secondary); }
.art-label-line { flex: 1; height: 1px; background: var(--color-border); }
.preview-disclaimer { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-6); align-items: center; padding-block: var(--space-6); border-top: var(--border-width) solid var(--color-border); color: var(--color-muted); font-size: var(--font-caption); margin-top: var(--space-10); }
.preview-disclaimer > span:first-child { color: var(--color-text); font-weight: var(--weight-medium); }
.disclaimer-index { margin-left: auto; display: none; font-family: var(--font-mono); }
.section-heading { display: grid; gap: var(--space-4); margin-bottom: var(--space-12); max-width: var(--reading-width); }
.section-heading > :first-child { margin-bottom: var(--space-2); }
.feature-grid, .foundation-grid { display: grid; gap: var(--space-4); }
.feature-card { display: flex; flex-direction: column; gap: var(--space-4); }
.feature-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-6); }
.feature-icon { width: var(--space-12); height: var(--space-12); display: grid; place-items: center; background: var(--color-accent-soft); color: var(--color-accent); border-radius: var(--radius-button); }
.feature-icon svg { width: var(--space-6); height: var(--space-6); }
.feature-number { font-family: var(--font-mono); font-size: var(--font-caption); color: var(--color-muted); }
.feature-card > .app-type--body { max-width: 24ch; }
.feature-rule { margin-top: var(--space-6); width: var(--space-8); height: 2px; background: var(--color-border-hover); }
.workbench-section { position: relative; overflow: hidden; }
.workbench-section::before { content: ''; position: absolute; inset: 35% 0 0; background: radial-gradient(ellipse at bottom, var(--color-accent-glow), transparent 65%); pointer-events: none; }
.workbench { position: relative; border: var(--border-width) solid var(--color-border-hover); border-radius: var(--radius-panel); background: var(--color-surface); overflow: hidden; display: grid; }
.workbench-sidebar { display: none; padding: var(--space-6); border-right: var(--border-width) solid var(--color-border); }
.workbench-brand { display: flex; align-items: center; gap: var(--space-2); font-weight: var(--weight-medium); font-size: var(--font-small); }
.sidebar-label { display: block; color: var(--color-muted); margin-top: var(--space-10); margin-bottom: var(--space-3); font-size: var(--font-caption); }
.sidebar-file { display: flex; align-items: flex-start; gap: var(--space-2); padding: var(--space-3); border-radius: var(--radius-button); background: var(--color-inset); font-size: var(--font-small); }
.sidebar-file svg { margin-top: var(--space-1); }
.sidebar-file small { display: block; color: var(--color-muted); font-size: var(--font-caption); margin-top: var(--space-1); }
.sidebar-bottom { display: flex; align-items: center; gap: var(--space-2); color: var(--color-muted); font-size: var(--font-caption); margin-top: auto; padding-top: var(--space-16); }
.workbench-content { min-width: 0; }
.workbench-topbar { padding: var(--space-5) var(--space-6); display: flex; justify-content: space-between; align-items: center; gap: var(--space-3); border-bottom: var(--border-width) solid var(--color-border); font-size: var(--font-caption); color: var(--color-secondary); }
.breadcrumb-divider { padding-inline: var(--space-2); color: var(--color-muted); }
.sample-badge { border: var(--border-width) solid var(--color-border-hover); border-radius: var(--radius-button); padding: var(--space-1) var(--space-2); color: var(--color-secondary); white-space: nowrap; }
.workbench-body { padding: var(--space-6); }
.review-heading { display: flex; justify-content: space-between; align-items: center; gap: var(--space-4); }
.review-heading .app-type--small { margin-top: var(--space-2); }
.review-index { color: var(--color-muted); font-size: var(--font-art-number); font-family: var(--font-mono); }
.review-tabs { display: flex; flex-wrap: wrap; gap: var(--space-1); margin-top: var(--space-8); padding: var(--space-1); background: var(--color-canvas); border-radius: var(--radius-button); width: fit-content; }
.review-tabs button { padding: var(--space-2) var(--space-3); border: 0; border-radius: var(--radius-button); background: transparent; color: var(--color-secondary); cursor: pointer; font-size: var(--font-small); transition: background var(--duration-fast) var(--ease-out), color var(--duration-fast) var(--ease-out); }
.review-tabs button.active { background: var(--color-inset); color: var(--color-text); }
.review-detail { margin-top: var(--space-6); min-height: var(--space-40); padding: var(--space-6); border: var(--border-width) solid var(--color-border); border-radius: var(--radius-card); background: var(--color-canvas); }
.detail-label { display: block; font-size: var(--font-caption); color: var(--color-muted); margin-bottom: var(--space-3); }
.review-detail p { font-size: var(--font-body); }
.evidence-row { display: flex; align-items: center; gap: var(--space-2); color: var(--color-secondary); margin-top: var(--space-6); font-size: var(--font-caption); }
.evidence-caption { margin-left: auto; }
.review-footer { margin-top: var(--space-6); display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-4); }
.review-footer .app-button .inline-icon { margin: 0 var(--space-2) 0 0; }
.foundation-card { min-width: 0; }
.card-heading { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: var(--space-3); margin-bottom: var(--space-8); }
.swatches { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-5); }
.swatch { display: grid; gap: var(--space-1); font-size: var(--font-small); }
.swatch-color { display: block; height: var(--space-16); border: var(--border-width) solid var(--color-border); border-radius: var(--radius-button); margin-bottom: var(--space-2); }
.swatch-color--canvas { background: var(--color-canvas); }.swatch-color--surface { background: var(--color-surface); }.swatch-color--text { background: var(--color-text); }.swatch-color--accent { background: var(--color-accent); }
.swatch code { color: var(--color-muted); font-family: var(--font-mono); font-size: var(--font-caption); }
.button-samples { display: flex; flex-wrap: wrap; gap: var(--space-3); margin-bottom: var(--space-6); }
.type-specimen { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-8); }
.type-specimen-large { font-size: var(--type-specimen-size); line-height: var(--leading-heading); font-weight: var(--weight-semibold); letter-spacing: var(--tracking-heading); }
.type-specimen-large > span { color: var(--color-muted); margin-left: var(--space-3); }
.numeric-specimen { display: block; margin-top: var(--space-4); color: var(--color-muted); letter-spacing: var(--tracking-label); }
.type-scale { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-5); margin-top: var(--space-8); padding-top: var(--space-5); border-top: var(--border-width) solid var(--color-border); font-size: var(--font-caption); color: var(--color-secondary); }
.space-specimen { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); align-items: end; gap: var(--space-3); height: var(--space-20); }
.space-specimen > span { display: block; background: var(--color-accent); border-radius: var(--space-1) var(--space-1) 0 0; }
.space-specimen > span:nth-child(1) { height: var(--space-2); opacity: .25; }.space-specimen > span:nth-child(2) { height: var(--space-4); opacity: .4; }.space-specimen > span:nth-child(3) { height: var(--space-6); opacity: .55; }.space-specimen > span:nth-child(4) { height: var(--space-8); opacity: .7; }.space-specimen > span:nth-child(5) { height: var(--space-12); }
.space-labels { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: var(--space-3); margin-block: var(--space-3) var(--space-6); font-size: var(--font-caption); color: var(--color-muted); font-family: var(--font-mono); }
.demo-footer { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-6); padding-block: var(--space-8); border-top: var(--border-width) solid var(--color-border); font-size: var(--font-caption); }
.footer-brand { display: flex; align-items: center; gap: var(--space-2); font-weight: var(--weight-medium); }
@media (min-width: 640px) {
  .nav-cta { display: inline-flex; }.hero-art { --art-sheet-width: 360px; --art-sheet-height: 380px; }.disclaimer-index { display: inline; }.swatches { grid-template-columns: repeat(4, minmax(0, 1fr)); }.review-tabs button { padding-inline: var(--space-5); }.workbench-body { padding: var(--space-8); }
}
@media (min-width: 768px) {
  .foundation-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.workbench { grid-template-columns: var(--workbench-sidebar-width) minmax(0, 1fr); }.workbench-sidebar { display: flex; flex-direction: column; }.hero { padding-top: calc(var(--nav-height) + var(--space-16)); }.workbench-topbar { padding-inline: var(--space-8); }
}
@media (min-width: 1024px) {
  .desktop-nav { display: flex; gap: var(--space-8); color: var(--color-secondary); font-size: var(--font-small); }.menu-toggle { display: none; }.mobile-nav { display: none; }.hero-layout { grid-template-columns: 1fr 1fr; align-items: center; gap: var(--space-10); }.hero-art { --art-sheet-width: 320px; --art-sheet-height: 360px; }.hero { padding-top: calc(var(--nav-height) + var(--space-12)); }.preview-disclaimer { margin-top: var(--space-16); }.feature-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }.workbench-body { padding: var(--space-10); }.workbench-heading { max-width: none; }.feature-card { padding: var(--space-8); }
}
@media (min-width: 1280px) {
  .hero-art { --art-sheet-width: 360px; --art-sheet-height: 380px; }.hero { padding-top: calc(var(--nav-height) + var(--space-16)); }.workbench { --workbench-sidebar-width: 240px; }.foundation-grid { gap: var(--space-6); }
}
@media (max-width: 639px) {
  .hero-art { --hero-art-height: 440px; }.foundation-card, .feature-card { padding: var(--space-6); }.type-specimen { --type-specimen-size: 64px; gap: var(--space-5); }.hero-actions .app-button { flex: 1; padding-inline: var(--space-4); }.review-tabs { width: 100%; }.review-tabs button { flex: 1; padding-inline: var(--space-2); }.review-detail { padding: var(--space-5); }.evidence-caption { display: none; }
}
</style>
