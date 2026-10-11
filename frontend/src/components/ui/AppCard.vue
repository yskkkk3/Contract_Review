<script setup lang="ts">
withDefaults(defineProps<{ as?: 'article' | 'div'; tone?: 'default' | 'soft'; padding?: 'none' | 'standard' | 'large' }>(), {
  as: 'article', tone: 'default', padding: 'standard',
})
</script>

<template>
  <component :is="as" class="app-card" :class="[`app-card--${tone}`, `app-card--${padding}`]"><slot /></component>
</template>

<style scoped>
.app-card { min-width: 0; border: var(--border-width) solid var(--color-border); border-radius: var(--radius-card); background: var(--color-canvas); transition: border-color var(--duration-fast) var(--ease-out); }
.app-card:hover { border-color: var(--color-border-hover); }
.app-card--soft { background: var(--color-surface); }
.app-card--standard { padding: var(--space-6); }
.app-card--large { padding: var(--space-8); }
</style>
