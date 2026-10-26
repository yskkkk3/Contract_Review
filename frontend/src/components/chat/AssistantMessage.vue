<template>
  <article class="assistant-message">
    <!-- eslint-disable-next-line vue/no-v-html -- content is sanitized in renderMarkdown -->
    <div class="markdown-body" v-html="html" />
    <button class="copy-button" type="button" :aria-label="copied ? '已复制回答' : '复制回答'" @click="copy">
      {{ copied ? '已复制' : '复制' }}
    </button>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps<{ content: string }>()
const copied = ref(false)
const html = computed(() => renderMarkdown(props.content))
let resetTimer: ReturnType<typeof setTimeout> | undefined

async function copy() {
  try {
    await navigator.clipboard.writeText(props.content)
    copied.value = true
    clearTimeout(resetTimer)
    resetTimer = setTimeout(() => { copied.value = false }, 1500)
  } catch {
    copied.value = false
  }
}
</script>

<style scoped>
.assistant-message { position: relative; min-width: 0; }
.copy-button { margin-top: 8px; padding: 2px 8px; border: 0; border-radius: 4px; color: var(--el-text-color-secondary); background: transparent; cursor: pointer; font-size: 12px; }
.copy-button:hover { color: var(--el-color-primary); background: var(--el-fill-color-light); }
.markdown-body { color: var(--el-text-color-primary); overflow-wrap: anywhere; }
.markdown-body :deep(> :first-child) { margin-top: 0; }
.markdown-body :deep(> :last-child) { margin-bottom: 0; }
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3) { margin: 1.1em 0 0.55em; line-height: 1.35; color: var(--el-text-color-primary); }
.markdown-body :deep(h1) { font-size: 18px; }
.markdown-body :deep(h2) { padding-bottom: 6px; border-bottom: 1px solid var(--el-border-color-lighter); font-size: 17px; }
.markdown-body :deep(h3) { font-size: 15px; }
.markdown-body :deep(p) { margin: 0.65em 0; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { margin: 0.65em 0; padding-left: 1.5em; }
.markdown-body :deep(li + li) { margin-top: 0.35em; }
.markdown-body :deep(strong) { color: var(--el-color-primary-dark-2); font-weight: 650; }
.markdown-body :deep(blockquote) { margin: 0.8em 0; padding: 8px 12px; border-left: 3px solid var(--el-color-primary-light-5); border-radius: 0 6px 6px 0; background: var(--el-color-primary-light-9); color: var(--el-text-color-secondary); }
.markdown-body :deep(code) { padding: 2px 5px; border-radius: 4px; background: var(--el-fill-color); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 0.9em; }
.markdown-body :deep(pre) { overflow-x: auto; padding: 12px; border-radius: 6px; background: var(--el-fill-color-dark); }
.markdown-body :deep(pre code) { padding: 0; background: transparent; }
.markdown-body :deep(.markdown-table-scroll) { max-width: 100%; margin: 0.8em 0; overflow-x: auto; }
.markdown-body :deep(table) { width: 100%; min-width: 480px; border-collapse: collapse; font-size: 13px; }
.markdown-body :deep(th), .markdown-body :deep(td) { padding: 8px 10px; border: 1px solid var(--el-border-color); text-align: left; vertical-align: top; }
.markdown-body :deep(th) { background: var(--el-fill-color-light); font-weight: 600; }
.markdown-body :deep(a) { color: var(--el-color-primary); text-decoration: none; }
.markdown-body :deep(a:hover) { text-decoration: underline; }
</style>
