<template>
  <div v-if="scope" class="review-scope">
    <div class="scope-heading">
      <b>本次审阅范围</b>
      <el-tag>{{ scope.profile_name }}</el-tag>
      <span>清单 v{{ scope.version }}</span>
    </div>
    <p>通用六个风险维度{{ scope.fallback ? '' : '＋分类专项检查' }}。检查范围和核对记录不等同于合同合规结论。</p>
    <el-alert v-if="scope.fallback" title="当前类型暂无对应专项清单，采用通用审阅。" type="info" :closable="false" />
    <el-alert v-if="scope.checklist_status === 'incomplete'" title="专项核对存在资料或记录缺口，请查看待补充事项。" type="warning" :closable="false" />
    <el-collapse>
      <el-collapse-item title="查看检查方向与专项核对记录" name="checks">
        <el-table :data="rows" size="small">
          <el-table-column prop="title" label="检查方向" min-width="170" />
          <el-table-column prop="risk_dim" label="所属维度" min-width="140" />
          <el-table-column prop="label" label="核对状态" width="100" />
          <el-table-column prop="reason" label="专项核对说明" min-width="220" />
        </el-table>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ReviewScope } from '@/types/api'
import { scopeRows } from '@/utils/review-scope'

const props = defineProps<{ scope?: ReviewScope | null }>()
const rows = computed(() => props.scope ? scopeRows(props.scope) : [])
</script>

<style scoped>
.review-scope { margin-bottom: 16px; padding: 12px 16px; border: 1px solid var(--el-border-color-light); border-radius: 6px; }
.scope-heading { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.review-scope p { color: var(--el-text-color-secondary); font-size: 13px; line-height: 1.6; }
</style>
