<script setup lang="ts">
import { Connection } from '@element-plus/icons-vue'
</script>

<template>
  <figure class="auth-visual" data-theme="dark" aria-label="LangGraph 多智能体编排流程：意图识别、专家并行、仲裁">
    <figcaption class="visual-caption">
      <span><Connection aria-hidden="true" />多智能体编排</span>
      <span class="visual-engine">LangGraph</span>
    </figcaption>
    <div class="visual-flow">
      <div class="flow-node"><span class="node-mark" aria-hidden="true" />意图识别</div>
      <span class="flow-connector" aria-hidden="true" />
      <div class="flow-node flow-node--experts"><span class="node-mark" aria-hidden="true" />专家并行</div>
      <span class="flow-connector" aria-hidden="true" />
      <div class="flow-node"><span class="node-mark" aria-hidden="true" />仲裁</div>
    </div>
  </figure>
</template>

<style scoped>
.auth-visual { position: relative; isolation: isolate; display: flex; flex-direction: column; justify-content: space-between; min-height: var(--auth-visual-height); margin: 0; padding: var(--space-6); overflow: hidden; border: var(--border-width) solid var(--color-border); border-radius: var(--radius-panel); color: var(--color-text); background: var(--color-canvas); }
.auth-visual::before { position: absolute; z-index: -1; inset: 0; content: ''; background: radial-gradient(ellipse at 50% 100%, var(--color-accent-glow), transparent 70%), linear-gradient(var(--color-border) var(--border-width), transparent var(--border-width)), linear-gradient(90deg, var(--color-border) var(--border-width), transparent var(--border-width)); background-size: auto, var(--grid-size) var(--grid-size), var(--grid-size) var(--grid-size); opacity: .6; }
.visual-caption, .visual-caption > span { display: flex; align-items: center; gap: var(--space-2); }
.visual-caption { justify-content: space-between; gap: var(--space-4); font-size: var(--font-small); font-weight: var(--weight-medium); }
.visual-caption svg { width: var(--icon-size); height: var(--icon-size); color: var(--color-accent-light-5); }
.visual-engine { font: var(--font-caption)/var(--leading-body) var(--font-mono); color: var(--color-secondary); }
.visual-flow { display: flex; align-items: center; padding-block: var(--space-6); }
.flow-node { flex: 1; display: flex; flex-direction: column; align-items: center; gap: var(--space-3); padding: var(--space-4) var(--space-2); border: var(--border-width) solid var(--color-border-hover); border-radius: var(--radius-card); background: var(--color-surface); font-size: var(--font-small); white-space: nowrap; }
.flow-node--experts { border-color: var(--color-accent-light-3); background: var(--color-accent-soft); }
.node-mark { width: var(--space-2); height: var(--space-2); border-radius: var(--radius-pill); background: var(--color-secondary); }
.flow-node--experts .node-mark { background: var(--color-accent-light-5); box-shadow: 0 0 0 var(--space-1) var(--color-accent-glow); }
.flow-connector { width: var(--space-6); height: var(--border-width); background: var(--color-border-hover); }
@media (min-width: 768px) { .auth-visual { padding: var(--space-8); } }
</style>
