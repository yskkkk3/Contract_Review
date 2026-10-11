<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElDrawer } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import AppContainer from '@/components/ui/AppContainer.vue'
import AppTypography from '@/components/ui/AppTypography.vue'
import AppNavbar from '@/components/layout/AppNavbar.vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import AppFooter from '@/components/layout/AppFooter.vue'
import AvatarDialog from '@/components/account/AvatarDialog.vue'
import { APP_NAVIGATION } from '@/components/layout/navigation'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const mainRef = ref<HTMLElement>()
const mobileNavigationOpen = ref(false)
const scrolled = ref(false)
const avatarDialogOpen = ref(false)
const navbar = ref<InstanceType<typeof AppNavbar>>()
let desktopQuery: MediaQueryList | undefined

const navigation = computed(() => APP_NAVIGATION.filter((item) => !item.adminOnly || auth.user?.role === 'admin'))
const title = computed(() => APP_NAVIGATION.find((item) => item.name === route.name)?.label || '合同智能审阅')

function closeOnDesktop() {
  if (desktopQuery?.matches) mobileNavigationOpen.value = false
}

onMounted(() => {
  desktopQuery = window.matchMedia('(min-width: 1024px)')
  desktopQuery.addEventListener('change', closeOnDesktop)
  if (!auth.user) auth.fetchMe()
})
onUnmounted(() => desktopQuery?.removeEventListener('change', closeOnDesktop))

watch(() => route.path, () => {
  mobileNavigationOpen.value = false
  mainRef.value?.scrollTo({ top: 0 })
  scrolled.value = false
})

function onLogout() {
  auth.logout()
  router.push('/login')
}

function onScroll() {
  scrolled.value = (mainRef.value?.scrollTop || 0) > 0
}
</script>

<template>
  <div class="design-system app-shell">
    <a href="#workspace-main" class="workspace-skip-link">跳转到主要内容</a>
    <AppNavbar ref="navbar" :title="title" :username="auth.user?.username || ''" :avatar-url="auth.avatarUrl" :menu-open="mobileNavigationOpen" :scrolled="scrolled" @toggle-menu="mobileNavigationOpen = !mobileNavigationOpen" @logout="onLogout" @manage-avatar="avatarDialogOpen = true" />
    <AvatarDialog v-model="avatarDialogOpen" @closed="navbar?.focusAccount()" />
    <AppSidebar class="desktop-sidebar" :items="navigation" />
    <ElDrawer v-model="mobileNavigationOpen" class="design-system app-mobile-navigation" modal-class="workspace-navigation-overlay" title="导航" direction="ltr" size="min(var(--shell-drawer-width), calc(100vw - var(--space-10)))" destroy-on-close>
      <AppSidebar id="mobile-workspace-navigation" :items="navigation" @navigate="mobileNavigationOpen = false" />
    </ElDrawer>
    <main id="workspace-main" ref="mainRef" class="workspace-main" tabindex="-1" aria-labelledby="workspace-title" @scroll.passive="onScroll">
      <AppContainer class="workspace-inner">
        <header class="workspace-heading">
          <div><AppTypography class="workspace-eyebrow" variant="eyebrow" tone="muted">Contract Review Agent</AppTypography><AppTypography id="workspace-title" as="h1" variant="section">{{ title }}</AppTypography><AppTypography class="workspace-description" variant="small" tone="secondary">高校采购合同智能审阅 Agent</AppTypography></div>
          <span class="workspace-context-label">采购合同管理场景</span>
        </header>
        <div class="workspace-stage"><router-view /></div>
        <AppFooter />
      </AppContainer>
    </main>
  </div>
</template>
