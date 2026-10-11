<script setup lang="ts">
import { ref } from 'vue'
import { ElInput } from 'element-plus'
import { Hide, View } from '@element-plus/icons-vue'

defineProps<{ id: string; autocomplete: 'current-password' | 'new-password' }>()
const model = defineModel<string>({ required: true })
const visible = ref(false)
</script>

<template>
  <ElInput :id="id" v-model="model" name="password" :autocomplete="autocomplete" :type="visible ? 'text' : 'password'" placeholder="密码" size="large">
    <template #suffix>
      <button type="button" class="password-toggle" :aria-label="visible ? '隐藏密码' : '显示密码'" :aria-pressed="visible" :aria-controls="id" @click="visible = !visible">
        <component :is="visible ? View : Hide" aria-hidden="true" />
      </button>
    </template>
  </ElInput>
</template>

<style scoped>
.password-toggle { display: inline-flex; align-items: center; justify-content: center; width: var(--space-8); height: var(--space-8); padding: 0; border: 0; border-radius: var(--radius-button); color: var(--color-secondary); background: transparent; cursor: pointer; transition: color var(--duration-fast) var(--ease-out), background var(--duration-fast) var(--ease-out); }
.password-toggle:hover { color: var(--color-accent); background: var(--color-accent-soft); }
.password-toggle svg { width: var(--icon-size); height: var(--icon-size); }
.password-toggle:focus-visible { outline: 2px solid var(--color-accent); outline-offset: var(--space-1); }
@media (prefers-reduced-motion: reduce) { .password-toggle { transition: none; } }
</style>
