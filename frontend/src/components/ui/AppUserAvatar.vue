<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = withDefaults(defineProps<{ username: string; src?: string; size?: 'small' | 'large' }>(), { src: '', size: 'small' })
const failed = ref(false)
const initial = computed(() => (props.username || 'U').slice(0, 1).toUpperCase())
watch(() => props.src, () => { failed.value = false })
</script>

<template>
  <span class="user-avatar" :class="{ 'user-avatar--large': size === 'large' }" role="img" :aria-label="(username || '用户') + (src && !failed ? '的头像' : '的默认头像')">
    <img v-if="src && !failed" :src="src" :alt="(username || '用户') + '的头像'" @error="failed = true" />
    <span v-else aria-hidden="true">{{ initial }}</span>
  </span>
</template>

<style scoped>
.user-avatar { display: inline-grid; place-items: center; flex-shrink: 0; width: var(--shell-avatar-size); height: var(--shell-avatar-size); overflow: hidden; border-radius: var(--radius-pill); color: var(--color-text); background: var(--color-inset); font-size: var(--font-small); font-weight: var(--weight-semibold); }
.user-avatar--large { width: var(--avatar-preview-size); height: var(--avatar-preview-size); font-size: var(--font-section); }
.user-avatar img { display: block; width: 100%; height: 100%; object-fit: cover; }
</style>
