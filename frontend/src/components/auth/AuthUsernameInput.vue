<script setup lang="ts">
import { ref } from 'vue'
import { ElInput, type InputInstance } from 'element-plus'
import { Close } from '@element-plus/icons-vue'

defineProps<{ id: string; placeholder: string }>()
const model = defineModel<string>({ required: true })
const input = ref<InputInstance>()

function clear() {
  model.value = ''
  input.value?.focus()
}
</script>

<template>
  <ElInput :id="id" ref="input" v-model="model" name="username" autocomplete="username" :placeholder="placeholder" size="large">
    <template #suffix>
      <button v-if="model" type="button" class="username-clear" :aria-label="'清空' + placeholder" :aria-controls="id" @click="clear">
        <Close aria-hidden="true" />
      </button>
    </template>
  </ElInput>
</template>

<style scoped>
.username-clear { display: inline-flex; align-items: center; justify-content: center; width: var(--space-8); height: var(--space-8); padding: 0; border: 0; border-radius: var(--radius-button); color: var(--color-secondary); background: transparent; cursor: pointer; transition: color var(--duration-fast) var(--ease-out), background var(--duration-fast) var(--ease-out); }
.username-clear:hover { color: var(--color-accent); background: var(--color-accent-soft); }
.username-clear svg { width: var(--icon-size); height: var(--icon-size); }
.username-clear:focus-visible { outline: 2px solid var(--color-accent); outline-offset: var(--space-1); }
@media (prefers-reduced-motion: reduce) { .username-clear { transition: none; } }
</style>
