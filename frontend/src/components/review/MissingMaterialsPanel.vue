<template>
  <section v-if="materials.length" class="missing-materials">
    <div class="missing-heading">
      <div>
        <b>审阅引用了尚未提供的相关文件</b>
        <p>这些材料会影响专项结论。你可以补充后重新审阅，也可以暂不补充并保留当前提示。</p>
      </div>
      <el-tag type="warning">{{ materials.length }} 项待补</el-tag>
    </div>
    <el-alert
      v-if="decision === 'deferred'"
      title="你已选择暂不补充；当前结果仍保留材料缺口，不能视为完整审阅。"
      type="info"
      :closable="false"
    />
    <el-alert
      v-else-if="decision === 'supplemented'"
      title="你已补充材料并发起新的审阅；本记录保留补充前的结论，便于追溯。"
      type="success"
      :closable="false"
    />
    <div v-for="item in materials" :key="item.id" class="material-item">
      <div class="material-title">{{ item.title }} <el-tag size="small">{{ item.risk_dim }}</el-tag></div>
      <div class="material-files">
        <span>建议补充：</span>
        <el-tag v-for="name in item.suggested_files" :key="name" size="small" type="warning">{{ name }}</el-tag>
      </div>
      <p>{{ item.reason }}</p>
      <small v-if="item.clause_indices.length">关联条款索引：{{ item.clause_indices.join('、') }}</small>
    </div>
    <div v-if="showActions" class="material-actions">
      <el-button type="primary" @click="$emit('supplement')">选择或上传材料后重新审阅</el-button>
      <el-button v-if="!decision" @click="$emit('defer')">暂不补充</el-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { MissingMaterial } from '@/types/api'

withDefaults(defineProps<{
  materials: MissingMaterial[]
  decision?: 'deferred' | 'supplemented' | null
  showActions?: boolean
}>(), { decision: null, showActions: false })

defineEmits<{ supplement: []; defer: [] }>()
</script>

<style scoped>
.missing-materials { margin-bottom: 16px; padding: 16px; border: 1px solid var(--el-color-warning-light-5); border-radius: 8px; background: var(--el-color-warning-light-9); }
.missing-heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.missing-heading p, .material-item p { margin: 6px 0; color: var(--el-text-color-secondary); line-height: 1.6; }
.material-item { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--el-border-color-lighter); }
.material-title, .material-files, .material-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.material-title { font-weight: 600; }
.material-files { margin-top: 8px; }
.material-actions { margin-top: 16px; }
</style>
