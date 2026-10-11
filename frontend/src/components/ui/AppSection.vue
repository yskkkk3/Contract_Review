<script setup lang="ts">
withDefaults(defineProps<{ tone?: 'default' | 'muted' | 'inverse'; spacing?: 'default' | 'compact' }>(), {
  tone: 'default', spacing: 'default',
})
</script>

<template>
  <section class="app-section" :class="[`app-section--${tone}`, `app-section--${spacing}`]" :data-theme="tone === 'inverse' ? 'dark' : undefined"><slot /></section>
</template>

<style scoped>
.app-section { padding-block: var(--section-space); background: var(--color-canvas); color: var(--color-text); }
.app-section--muted { background: var(--color-surface); }
.app-section--compact { padding-block: var(--space-12); }
</style>
