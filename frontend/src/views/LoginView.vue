<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Connection, DocumentChecked, Search } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useReveal } from '@/composables/useReveal'
import BrandLogo from '@/components/layout/BrandLogo.vue'
import AuthProductVisual from '@/components/auth/AuthProductVisual.vue'
import AuthPasswordInput from '@/components/auth/AuthPasswordInput.vue'
import AuthUsernameInput from '@/components/auth/AuthUsernameInput.vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppCard from '@/components/ui/AppCard.vue'
import AppContainer from '@/components/ui/AppContainer.vue'
import AppSection from '@/components/ui/AppSection.vue'
import AppTypography from '@/components/ui/AppTypography.vue'

const router = useRouter()
const auth = useAuthStore()
const tab = ref('login')
const identifier = ref('')
const password = ref('')
const reg = reactive({ username: '', password: '' })
const loading = ref(false)
const root = useReveal()
const scrolled = ref(false)
const features = [
  { icon: Connection, title: '多智能体编排', description: 'LangGraph 意图识别 / 专家并行 / 仲裁' },
  { icon: Search, title: '混合检索 RAG', description: '法规 / 校内制度 / 合同模板三层知识库' },
  { icon: DocumentChecked, title: '流式审阅', description: 'SSE 实时输出风险点与修改建议' },
]

function updateScroll() { scrolled.value = window.scrollY > 0 }
onMounted(() => {
  updateScroll()
  window.addEventListener('scroll', updateScroll, { passive: true })
})
onUnmounted(() => { window.removeEventListener('scroll', updateScroll) })

async function onLogin() {
  loading.value = true
  try {
    await auth.login(identifier.value, password.value)
    ElMessage.success('登录成功')
    router.push('/dashboard')
  } finally {
    loading.value = false
  }
}

async function onRegister() {
  if (!reg.username.trim()) return ElMessage.warning('请输入用户名')
  if (reg.password.length < 6) return ElMessage.warning('密码至少需要 6 位')
  loading.value = true
  try {
    await auth.register(reg.username, reg.password)
    ElMessage.success('注册成功，请登录')
    tab.value = 'login'
    identifier.value = reg.username
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div ref="root" class="design-system auth-page">
    <a class="auth-skip-link" href="#auth-form">跳转到登录 / 注册</a>
    <header class="auth-header" :class="{ 'is-scrolled': scrolled }">
      <AppContainer class="auth-header-inner">
        <a class="auth-brand" href="#auth-main" aria-label="高校合同智能审阅系统">
          <BrandLogo />
          <span>
            <span class="auth-brand-title">高校合同智能审阅系统</span>
            <span class="auth-brand-sub">Contract Review Agent</span>
          </span>
        </a>
        <AppTypography as="span" variant="small" tone="secondary" class="auth-context">采购合同管理场景</AppTypography>
      </AppContainer>
    </header>

    <main id="auth-main">
      <AppContainer class="auth-main">
        <div class="auth-grid">
          <div class="auth-intro">
            <AppTypography variant="eyebrow" tone="secondary" class="auth-eyebrow">Contract Review Agent</AppTypography>
            <AppTypography as="h1" variant="hero">高校合同<br />智能审阅系统</AppTypography>
            <AppTypography variant="lead" tone="secondary" class="auth-subtitle">流式审阅 · SSE 实时输出风险点与修改建议</AppTypography>
            <AuthProductVisual class="auth-product-visual" />
          </div>

          <AppCard id="auth-form" as="div" padding="none" class="auth-card" tabindex="-1" aria-labelledby="auth-heading">
            <div class="auth-card-heading">
              <AppTypography id="auth-heading" as="h2" variant="section">{{ tab === 'login' ? '欢迎回来' : '注册' }}</AppTypography>
              <AppTypography variant="small" tone="secondary">登录以使用合同智能审阅能力</AppTypography>
            </div>
            <el-tabs v-model="tab" stretch class="auth-tabs" aria-label="登录或注册">
              <el-tab-pane label="登录" name="login">
                <el-form label-position="top" aria-label="登录" @submit.prevent="onLogin">
                  <el-form-item label="用户名 / 邮箱" for="login-identifier">
                    <AuthUsernameInput id="login-identifier" v-model="identifier" placeholder="用户名 / 邮箱" />
                  </el-form-item>
                  <el-form-item label="密码" for="login-password">
                    <AuthPasswordInput id="login-password" v-model="password" autocomplete="current-password" />
                  </el-form-item>
                  <AppButton size="large" native-type="submit" class="auth-submit" :loading="loading">登 录</AppButton>
                </el-form>
              </el-tab-pane>
              <el-tab-pane label="注册" name="register">
                <el-form label-position="top" aria-label="注册" @submit.prevent="onRegister">
                  <el-form-item label="用户名" for="register-username">
                    <AuthUsernameInput id="register-username" v-model="reg.username" placeholder="用户名" />
                  </el-form-item>
                  <el-form-item label="密码" for="register-password">
                    <AuthPasswordInput id="register-password" v-model="reg.password" autocomplete="new-password" />
                  </el-form-item>
                  <AppButton size="large" native-type="submit" class="auth-submit" :loading="loading">注 册</AppButton>
                </el-form>
              </el-tab-pane>
            </el-tabs>
          </AppCard>
        </div>
      </AppContainer>

      <AppSection tone="muted" aria-label="产品能力">
        <AppContainer class="auth-features-grid">
          <AppCard v-for="feature in features" :key="feature.title" data-reveal padding="large" class="auth-feature">
            <component :is="feature.icon" class="auth-feature-icon" aria-hidden="true" />
            <AppTypography as="h2" variant="card">{{ feature.title }}</AppTypography>
            <AppTypography tone="secondary">{{ feature.description }}</AppTypography>
          </AppCard>
        </AppContainer>
      </AppSection>
    </main>

    <AppContainer as="footer" class="auth-footer">
      <AppTypography variant="caption" tone="muted">高校合同智能审阅系统</AppTypography>
      <AppTypography variant="caption" tone="muted">Contract Review Agent</AppTypography>
    </AppContainer>
  </div>
</template>

<style scoped>
.auth-page { min-height: 100dvh; padding-top: var(--nav-height); color: var(--color-text); background: var(--color-canvas); font: var(--weight-regular) var(--font-body)/var(--leading-body) var(--font-sans); font-feature-settings: 'tnum' 1, 'lnum' 1; -webkit-font-smoothing: antialiased; }
.auth-page, .auth-page :deep(*), .auth-page :deep(*::before), .auth-page :deep(*::after) { box-sizing: border-box; }
.auth-page :deep(:focus-visible) { outline: 2px solid var(--color-accent); outline-offset: var(--space-1); }
.auth-skip-link { position: fixed; z-index: var(--layer-skip-link); top: var(--space-3); left: var(--space-3); padding: var(--space-3) var(--space-4); border-radius: var(--radius-button); color: var(--color-text); background: var(--color-canvas); transform: translateY(-200%); }
.auth-skip-link:focus { transform: none; }
.auth-header { position: fixed; z-index: var(--layer-navbar); inset: 0 0 auto; height: var(--nav-height); border-bottom: var(--border-width) solid transparent; background: var(--color-canvas); transition: background var(--duration-normal) var(--ease-out), border-color var(--duration-normal) var(--ease-out); }
.auth-header.is-scrolled { border-color: var(--color-border); background: var(--color-glass); backdrop-filter: blur(var(--blur-glass)); }
.auth-header-inner { display: flex; align-items: center; justify-content: space-between; gap: var(--space-6); height: 100%; }
.auth-brand { display: inline-flex; align-items: center; gap: var(--space-3); color: var(--color-text); text-decoration: none; }
.auth-brand :deep(svg) { width: var(--space-8); height: var(--space-8); color: var(--color-accent); }
.auth-brand-title, .auth-brand-sub { display: block; }
.auth-brand-title { font-size: var(--font-small); font-weight: var(--weight-semibold); }
.auth-brand-sub { color: var(--color-secondary); font-size: var(--font-caption); }
.auth-context { display: none; }
.auth-main { position: relative; isolation: isolate; padding-block: var(--space-8) var(--space-16); }
.auth-main::before { position: absolute; z-index: -1; inset: 0; pointer-events: none; content: ''; background: radial-gradient(ellipse at 85% 45%, var(--color-accent-glow), transparent 60%); }
.auth-grid { display: grid; align-items: center; gap: var(--space-8); }
.auth-intro { min-width: 0; }
.auth-eyebrow { margin-bottom: var(--space-4); }
.auth-subtitle { max-width: var(--auth-form-width); margin-top: var(--space-5); }
.auth-product-visual { display: none; }
.auth-card { width: 100%; max-width: var(--auth-form-width); justify-self: center; padding: var(--space-6); border-radius: var(--radius-panel); }
.auth-card-heading { --font-section: var(--auth-heading-size); display: grid; gap: var(--space-3); margin-bottom: var(--space-6); }
.auth-tabs :deep(.el-tabs__header) { margin-bottom: var(--space-6); }
.auth-tabs :deep(.el-tabs__nav-wrap::after) { height: var(--border-width); background: var(--color-border); }
.auth-tabs :deep(.el-tabs__item) { height: var(--button-height); font-size: var(--font-body); font-weight: var(--weight-medium); }
.auth-tabs :deep(.el-tabs__item.is-focus) { box-shadow: none; }
.auth-tabs :deep(.el-form-item) { margin-bottom: var(--space-6); }
.auth-tabs :deep(.el-form-item__label) { margin-bottom: var(--space-2); padding: 0; color: var(--color-text); font-size: var(--font-small); font-weight: var(--weight-medium); line-height: var(--leading-body); }
.auth-tabs :deep(.el-input__wrapper) { min-height: var(--button-height-large); padding-inline: var(--space-3); border-radius: var(--radius-button); background: var(--color-surface); box-shadow: 0 0 0 var(--border-width) var(--color-border-hover) inset; transition: box-shadow var(--duration-fast) var(--ease-out); }
.auth-tabs :deep(.el-input__wrapper.is-focus) { box-shadow: 0 0 0 var(--border-width) var(--color-accent) inset, var(--focus-ring); }
.auth-tabs :deep(.el-input__inner) { color: var(--color-text); font: inherit; font-size: var(--font-body); }
.auth-tabs :deep(.el-input__inner::placeholder) { color: var(--color-muted); }
.auth-submit { width: 100%; }
.auth-features-grid { display: grid; gap: var(--space-6); }
.auth-feature { display: grid; align-content: start; gap: var(--space-4); }
.auth-feature-icon { width: var(--space-6); height: var(--space-6); margin-bottom: var(--space-2); color: var(--color-accent); }
.auth-footer { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--space-3); padding-block: var(--space-8); }
.auth-page [data-reveal-state="pending"] { opacity: 0; transform: translateY(var(--reveal-offset)); }
.auth-page [data-reveal-state="visible"] { opacity: 1; transform: none; transition: opacity var(--duration-enter) var(--ease-out), transform var(--duration-enter) var(--ease-out); }
@media (min-width: 640px) {
  .auth-context { display: inline; }
  .auth-main { padding-block: var(--space-12) var(--space-20); }
  .auth-card { padding: var(--space-10); }
}
@media (min-width: 768px) {
  .auth-features-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .auth-feature { padding: var(--space-6); }
}
@media (min-width: 1024px) {
  .auth-main { padding-block: var(--space-16); }
  .auth-grid { grid-template-columns: minmax(0, 1fr) minmax(0, var(--auth-form-width)); gap: var(--space-16); min-height: calc(100svh - var(--nav-height) - var(--space-16) * 2); }
  .auth-product-visual { display: flex; max-width: var(--auth-visual-width); margin-top: var(--space-10); }
}
@media (min-width: 1280px) { .auth-grid { gap: var(--space-30); } }
@media (prefers-reduced-motion: no-preference) {
  .auth-eyebrow, .auth-subtitle, .auth-product-visual { animation: auth-enter var(--duration-enter) var(--ease-out) both; }
  .auth-subtitle { animation-delay: var(--stagger-step); }
  .auth-product-visual { animation-delay: calc(var(--stagger-step) * 2); }
}
@keyframes auth-enter { from { opacity: 0; transform: translateY(var(--reveal-offset)); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) {
  .auth-page :deep(*), .auth-page :deep(*::before), .auth-page :deep(*::after) { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
  .auth-page [data-reveal-state] { opacity: 1; transform: none; }
}
</style>
