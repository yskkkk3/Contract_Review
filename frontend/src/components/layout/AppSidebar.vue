<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { Connection } from '@element-plus/icons-vue'
import type { NavigationItem } from './navigation'

defineProps<{ items: NavigationItem[] }>()
const emit = defineEmits<{ navigate: [] }>()
</script>

<template>
  <aside class="app-sidebar">
    <span class="sidebar-label">工作空间</span>
    <nav class="workspace-navigation" aria-label="主导航">
      <RouterLink v-for="item in items" :key="item.path" :to="item.path" class="workspace-navigation-link" active-class="is-active" @click="emit('navigate')">
        <component :is="item.icon" aria-hidden="true" /><span>{{ item.label }}</span><span class="navigation-active-mark" aria-hidden="true" />
      </RouterLink>
    </nav>
    <div class="sidebar-context">
      <div class="sidebar-context-art" aria-hidden="true"><Connection /><span /><span /></div>
      <strong>高校采购合同<br />智能审阅 Agent</strong>
      <span class="sidebar-context-caption">LangGraph + RAG</span>
    </div>
  </aside>
</template>

<style scoped>
.app-sidebar { box-sizing: border-box; display: flex; flex-direction: column; gap: var(--space-4); padding: var(--space-8) var(--space-5) var(--space-6); background: var(--color-canvas); color: var(--color-text); }
.sidebar-label { padding-inline: var(--space-3); font-size: var(--font-caption); color: var(--color-muted); }
.workspace-navigation { display: grid; gap: var(--space-2); }
.workspace-navigation-link { box-sizing: border-box; position: relative; min-height: var(--button-height); display: flex; align-items: center; gap: var(--space-3); padding: var(--space-2) var(--space-3); border-radius: var(--radius-button); font-size: var(--font-small); color: var(--color-secondary); text-decoration: none; transition: background var(--duration-fast) var(--ease-out), color var(--duration-fast) var(--ease-out); }
.workspace-navigation-link > svg { width: var(--icon-size); height: var(--icon-size); flex-shrink: 0; }
.workspace-navigation-link:hover { background: var(--color-surface); color: var(--color-text); }
.workspace-navigation-link.is-active { background: var(--color-accent-soft); color: var(--color-text); font-weight: var(--weight-medium); }
.workspace-navigation-link.is-active > svg { color: var(--color-accent); }
.navigation-active-mark { margin-left: auto; width: var(--space-1); height: var(--space-1); border-radius: var(--radius-pill); background: transparent; }
.is-active .navigation-active-mark { background: var(--color-accent); }
.sidebar-context { position: relative; isolation: isolate; overflow: hidden; display: grid; gap: var(--space-2); margin-top: auto; padding: var(--space-5); border: var(--border-width) solid var(--color-border); border-radius: var(--radius-card); background: var(--color-surface); }
.sidebar-context::before { content: ''; position: absolute; z-index: -1; inset: 0; background: radial-gradient(ellipse at top right, var(--color-accent-glow), transparent 75%); }
.sidebar-context-art { position: relative; display: flex; align-items: center; width: var(--space-10); height: var(--space-10); margin-bottom: var(--space-2); color: var(--color-accent); }
.sidebar-context-art > svg { width: var(--icon-size); height: var(--icon-size); }
.sidebar-context-art > span { position: absolute; inset: 0; border: var(--border-width) solid var(--color-accent-glow); border-radius: var(--radius-pill); }
.sidebar-context-art > span:last-child { inset: calc(-1 * var(--space-2)); }
.sidebar-context strong { font-size: var(--font-small); font-weight: var(--weight-medium); line-height: var(--leading-body); }
.sidebar-context-caption { font-size: var(--font-caption); color: var(--color-muted); }
</style>
