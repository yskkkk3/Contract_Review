<script setup lang="ts">
withDefaults(defineProps<{
  as?: 'h1' | 'h2' | 'h3' | 'h4' | 'p' | 'span'
  variant?: 'hero' | 'section' | 'card' | 'lead' | 'body' | 'small' | 'caption' | 'eyebrow'
  tone?: 'default' | 'secondary' | 'muted'
}>(), { as: 'p', variant: 'body', tone: 'default' })
</script>

<template>
  <component :is="as" class="app-type" :class="[`app-type--${variant}`, `app-type--${tone}`]"><slot /></component>
</template>

<style scoped>
.app-type { margin: 0; overflow-wrap: anywhere; }
.app-type--hero, .app-type--section, .app-type--card { font-weight: var(--weight-semibold); line-height: var(--leading-heading); letter-spacing: var(--tracking-heading); }
.app-type--hero { font-size: var(--font-hero); font-weight: var(--weight-bold); line-height: var(--leading-hero); }
.app-type--section { font-size: var(--font-section); }
.app-type--card { font-size: var(--font-card); line-height: var(--leading-card); }
.app-type--lead { font-size: var(--font-lead); }
.app-type--body { font-size: var(--font-body); }
.app-type--small { font-size: var(--font-small); }
.app-type--caption { font-size: var(--font-caption); }
.app-type--eyebrow { font-size: var(--font-caption); font-weight: var(--weight-semibold); letter-spacing: var(--tracking-label); text-transform: uppercase; }
.app-type--secondary { color: var(--color-secondary); }
.app-type--muted { color: var(--color-muted); }
</style>
