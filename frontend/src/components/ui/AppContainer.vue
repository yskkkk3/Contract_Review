<script setup lang="ts">
withDefaults(defineProps<{ as?: 'div' | 'main' | 'header' | 'footer' | 'nav'; width?: 'wide' | 'reading' }>(), {
  as: 'div', width: 'wide',
})
</script>

<template>
  <component :is="as" class="app-container" :class="`app-container--${width}`"><slot /></component>
</template>

<style scoped>
.app-container { box-sizing: border-box; width: 100%; max-width: var(--container-width); margin-inline: auto; padding-inline: var(--gutter); }
.app-container--reading { max-width: var(--reading-width); }
</style>
