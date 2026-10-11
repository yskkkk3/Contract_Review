<template>
  <el-tabs>
    <el-tab-pane label="合同类型">
      <el-card shadow="hover">
        <div class="row">
          <el-input v-model="newType.name" placeholder="类型名称" style="width: 200px" />
          <el-input v-model="newType.description" placeholder="描述" style="width: 300px; margin-left: 8px" />
          <el-button type="primary" style="margin-left: 8px" @click="addType">新增</el-button>
        </div>
        <el-table :data="types" style="margin-top: 16px">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="name" label="名称" />
          <el-table-column prop="description" label="描述" />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-switch :model-value="row.is_active" @change="(v: boolean) => toggleType(row, v)" />
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </el-tab-pane>
    <el-tab-pane label="模型配置">
      <el-card shadow="hover">
        <el-button type="primary" size="small" @click="modelFormVisible = true">新增配置</el-button>
        <el-table :data="models" style="margin-top: 16px">
          <el-table-column prop="model_name" label="模型" />
          <el-table-column prop="model_type" label="用途" width="110" />
          <el-table-column prop="provider" label="供应商" width="110" />
          <el-table-column prop="temperature" label="温度" width="70" />
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              <el-button link type="danger" @click="removeModel(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </el-tab-pane>
    <el-tab-pane label="Prompt 管理">
      <el-card shadow="hover">
        <el-table :data="prompts">
          <el-table-column prop="name" label="名称" width="200" />
          <el-table-column prop="prompt_type" label="类型" width="130" />
          <el-table-column prop="scope" label="作用域" width="110" />
          <el-table-column prop="content" label="内容" show-overflow-tooltip />
        </el-table>
      </el-card>
    </el-tab-pane>
  </el-tabs>

  <el-dialog v-model="modelFormVisible" title="新增模型配置" width="480px">
    <el-form label-width="100px">
      <el-form-item label="模型名称"><el-input v-model="modelForm.model_name" /></el-form-item>
      <el-form-item label="用途">
        <el-select v-model="modelForm.model_type" style="width: 100%">
          <el-option v-for="t in ['review', 'chat', 'embedding', 'rerank']" :key="t" :label="t" :value="t" />
        </el-select>
      </el-form-item>
      <el-form-item label="温度"><el-input-number v-model="modelForm.temperature" :min="0" :max="2" :step="0.1" /></el-form-item>
      <el-form-item label="Top P"><el-input-number v-model="modelForm.top_p" :min="0" :max="1" :step="0.05" /></el-form-item>
      <el-form-item label="Max Tokens"><el-input-number v-model="modelForm.max_tokens" :min="256" :step="256" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="modelFormVisible = false">取消</el-button>
      <el-button type="primary" @click="saveModel">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi } from '@/api/dashboard'
import type { ContractType, ModelConfig, PromptTemplate } from '@/types/api'

const types = ref<ContractType[]>([])
const models = ref<ModelConfig[]>([])
const prompts = ref<PromptTemplate[]>([])
const newType = reactive({ name: '', description: '' })
const modelFormVisible = ref(false)
const modelForm = reactive({ model_name: '', model_type: 'chat', temperature: 0.7, top_p: 0.95, max_tokens: 4096 })

onMounted(load)

async function load() {
  types.value = await adminApi.contractTypes()
  models.value = await adminApi.modelConfigs()
  prompts.value = await adminApi.prompts()
}

async function addType() {
  if (!newType.name) return
  await adminApi.createContractType(newType.name, newType.description)
  newType.name = ''
  newType.description = ''
  await load()
}

async function toggleType(row: ContractType, v: boolean) {
  await adminApi.toggleContractType(row.id, v)
  ElMessage.success('已更新')
  await load()
}

async function saveModel() {
  await adminApi.createModelConfig({ ...modelForm, provider: 'siliconflow', api_endpoint: 'https://api.siliconflow.cn/v1' })
  modelFormVisible.value = false
  await load()
}

async function removeModel(row: ModelConfig) {
  await adminApi.deleteModelConfig(row.id)
  await load()
}
</script>

<style scoped>
.row { display: flex; align-items: center; }
</style>
