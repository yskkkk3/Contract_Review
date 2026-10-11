<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { ElDropdown, ElDropdownItem, ElDropdownMenu } from 'element-plus'
import { ArrowDown, ArrowRight, DocumentChecked, Picture, SwitchButton } from '@element-plus/icons-vue'
import AppButton from '@/components/ui/AppButton.vue'
import AppUserAvatar from '@/components/ui/AppUserAvatar.vue'
import BrandLogo from './BrandLogo.vue'

defineProps<{
  title: string
  username: string
  avatarUrl: string
  menuOpen: boolean
  scrolled: boolean
}>()
const emit = defineEmits<{ toggleMenu: []; logout: []; manageAvatar: [] }>()
const accountTrigger = ref<HTMLButtonElement>()
defineExpose({ focusAccount: () => accountTrigger.value?.focus() })

function onCommand(command: string) {
  if (command === 'logout') emit('logout')
  if (command === 'avatar') emit('manageAvatar')
}
</script>

<template>
  <header class="app-navbar" :class="{ 'is-scrolled': scrolled }">
    <div class="navbar-inner">
      <button class="workspace-menu-toggle" type="button" aria-label="打开导航" aria-controls="mobile-workspace-navigation" :aria-expanded="menuOpen" @click="emit('toggleMenu')">
        <span class="workspace-menu-lines" aria-hidden="true"><i /><i /><i /></span>
      </button>
      <RouterLink to="/dashboard" class="workspace-brand" aria-label="合同智能审阅 · 工作台">
        <span class="workspace-brand-symbol"><BrandLogo /></span>
        <span class="workspace-brand-copy"><strong>合同智能审阅</strong><span>Contract Review Agent</span></span>
      </RouterLink>
      <div class="navbar-breadcrumb" aria-label="当前位置"><span>工作空间</span><span class="breadcrumb-separator" aria-hidden="true">/</span><span class="breadcrumb-current">{{ title }}</span></div>
      <div class="navbar-actions">
        <RouterLink v-slot="{ href, navigate }" to="/review" custom>
          <AppButton class="navbar-review" :href="href" @click="navigate"><DocumentChecked class="navbar-icon" aria-hidden="true" />智能审阅<ArrowRight class="navbar-icon navbar-action-arrow" aria-hidden="true" /></AppButton>
        </RouterLink>
        <ElDropdown trigger="click" popper-class="design-system app-account-menu" @command="onCommand">
          <button ref="accountTrigger" class="account-trigger" type="button" :aria-label="`账户菜单，${username || '用户'}`">
            <AppUserAvatar :username="username" :src="avatarUrl" aria-hidden="true" />
            <span class="account-name">{{ username }}</span><ArrowDown class="account-caret" aria-hidden="true" />
          </button>
          <template #dropdown>
            <ElDropdownMenu>
              <ElDropdownItem command="avatar"><Picture class="navbar-icon" aria-hidden="true" />更换头像</ElDropdownItem>
              <ElDropdownItem command="logout"><SwitchButton class="navbar-icon" aria-hidden="true" />退出登录</ElDropdownItem>
            </ElDropdownMenu>
          </template>
        </ElDropdown>
      </div>
    </div>
  </header>
</template>

<style scoped>
.app-navbar { position: fixed; inset: 0 0 auto; z-index: var(--layer-navbar); height: var(--nav-height); box-sizing: border-box; background: var(--color-canvas); border-bottom: var(--border-width) solid transparent; transition: background var(--duration-normal) var(--ease-out), border-color var(--duration-normal) var(--ease-out); }
.app-navbar.is-scrolled { background: var(--color-glass); border-color: var(--color-border); backdrop-filter: blur(var(--blur-glass)); }
.navbar-inner { height: 100%; padding-inline: var(--space-5); display: flex; align-items: center; gap: var(--space-3); }
.workspace-menu-toggle { width: var(--button-height); height: var(--button-height); flex-shrink: 0; display: grid; place-items: center; padding: 0; border: 0; border-radius: var(--radius-button); background: transparent; color: var(--color-text); cursor: pointer; }
.workspace-menu-toggle:hover { background: var(--color-surface); }
.workspace-menu-lines { display: grid; gap: var(--space-1); width: var(--icon-size); }
.workspace-menu-lines i { display: block; height: 2px; background: currentColor; border-radius: var(--radius-pill); }
.workspace-brand { min-width: 0; flex: 1; display: flex; align-items: center; gap: var(--space-2); color: var(--color-text); text-decoration: none; }
.workspace-brand-symbol { --brand-mark-cutout: var(--color-inverse); width: var(--space-8); height: var(--space-8); flex-shrink: 0; display: grid; place-items: center; color: var(--color-on-inverse); background: var(--color-inverse); border-radius: var(--radius-button); }
.workspace-brand-symbol svg { width: var(--space-6); height: var(--space-6); }
.workspace-brand-copy { min-width: 0; display: grid; gap: var(--space-1); line-height: var(--leading-compact); }
.workspace-brand-copy strong { font-size: var(--font-small); font-weight: var(--weight-semibold); white-space: nowrap; }
.workspace-brand-copy > span { display: none; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: var(--shell-brand-width); color: var(--color-muted); font-size: var(--font-caption); }
.navbar-breadcrumb { display: none; align-items: center; gap: var(--space-4); color: var(--color-muted); font-size: var(--font-small); }
.breadcrumb-separator { color: var(--color-border-hover); }
.breadcrumb-current { color: var(--color-text); font-weight: var(--weight-medium); }
.navbar-actions { display: flex; align-items: center; gap: var(--space-4); flex-shrink: 0; }
.navbar-review { display: none; }
.navbar-icon { width: var(--space-4); height: var(--space-4); margin-right: var(--space-2); }
.navbar-action-arrow { margin: 0 0 0 var(--space-3); }
.account-trigger { display: flex; align-items: center; gap: var(--space-2); min-width: var(--button-height); height: var(--button-height); padding: var(--space-1); border: 0; border-radius: var(--radius-button); color: var(--color-text); background: transparent; cursor: pointer; transition: background var(--duration-fast) var(--ease-out); }
.account-trigger:hover { background: var(--color-surface); }
.account-name { display: none; max-width: var(--shell-user-width); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--font-small); }
.account-caret { display: none; width: var(--space-3); height: var(--space-3); color: var(--color-muted); }
@media (min-width: 640px) {
  .navbar-inner { padding-inline: var(--space-6); gap: var(--space-4); }
  .workspace-brand-copy > span, .account-name, .account-caret { display: block; }
  .workspace-brand-symbol { width: var(--space-10); height: var(--space-10); }
  .account-trigger { padding-inline: var(--space-2); }
}
@media (min-width: 768px) { .navbar-review { display: inline-flex; } }
@media (min-width: 1024px) {
  .navbar-inner { display: grid; grid-template-columns: var(--shell-sidebar-width) minmax(0, 1fr) auto; }
  .workspace-menu-toggle { display: none; }
  .navbar-breadcrumb { display: flex; }
}
</style>
