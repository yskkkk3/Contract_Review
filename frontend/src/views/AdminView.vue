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
              <el-switch :model-value="Boolean(row.is_active)" @change="(v: boolean) => toggleType(row, v)" />
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </el-tab-pane>
    <el-tab-pane label="模型配置">
      <el-card shadow="hover">
        <el-button type="primary" size="small" @click="modelFormVisible = true">新增配置</el-button>
        <el-alert title="每个用途的启用默认配置从下一次请求生效；无默认配置时使用环境配置。更换向量模型后需重建知识库。" type="info" :closable="false" style="margin-top: 12px" />
        <el-table :data="models" style="margin-top: 16px">
          <el-table-column prop="model_name" label="模型" />
          <el-table-column prop="model_type" label="用途" width="110" />
          <el-table-column prop="provider" label="供应商" width="110" />
          <el-table-column prop="temperature" label="温度" width="70" />
          <el-table-column label="默认" width="80"><template #default="{ row }">{{ row.is_default && row.status === 'active' ? '是' : '否' }}</template></el-table-column>
          <el-table-column label="操作" width="240">
            <template #default="{ row }">
              <el-button link type="primary" @click="setDefaultModel(row)">设为默认</el-button>
              <el-button link @click="toggleModel(row)">{{ row.status === 'active' ? '停用' : '启用' }}</el-button>
              <el-button link type="danger" @click="removeModel(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </el-tab-pane>
    <el-tab-pane label="Prompt 管理">
      <el-card shadow="hover">
        <el-button type="primary" size="small" @click="editPrompt()">新增提示词</el-button>
        <el-alert title="名称对应内置模板。可为指定合同类型保存覆盖版本；停用后回退到其他启用版本或内置模板。" type="info" :closable="false" style="margin: 12px 0" />
        <el-table :data="prompts">
          <el-table-column prop="prompt_name" label="名称" width="200" />
          <el-table-column prop="level" label="层级" width="130" />
          <el-table-column prop="contract_type_id" label="合同类型 ID" width="120" />
          <el-table-column prop="prompt_content" label="内容" show-overflow-tooltip />
          <el-table-column label="状态" width="80"><template #default="{ row }">{{ row.is_active ? '启用' : '停用' }}</template></el-table-column>
          <el-table-column label="操作" width="180"><template #default="{ row }">
            <el-button link @click="editPrompt(row)">编辑</el-button>
            <el-button link @click="togglePrompt(row)">{{ row.is_active ? '停用' : '启用' }}</el-button>
            <el-button link type="danger" @click="deletePrompt(row)">删除</el-button>
          </template></el-table-column>
        </el-table>
      </el-card>
    </el-tab-pane>
  </el-tabs>

  <el-dialog v-model="modelFormVisible" title="新增模型配置" width="480px">
    <el-form label-width="100px">
      <el-form-item label="模型名称"><el-input v-model="modelForm.model_name" /></el-form-item>
      <el-form-item label="供应商"><el-input v-model="modelForm.provider" /></el-form-item>
      <el-form-item label="API 地址"><el-input v-model="modelForm.api_endpoint" placeholder="OpenAI 兼容地址；精排填写完整接口 URL" /></el-form-item>
      <el-form-item label="密钥引用"><el-input v-model="modelForm.api_key" placeholder="env:LLM_API_KEY；留空使用该用途的环境密钥" /></el-form-item>
      <el-form-item label="设为默认"><el-switch v-model="modelForm.is_default" :active-value="1" :inactive-value="0" /></el-form-item>
      <el-form-item label="用途">
        <el-select v-model="modelForm.model_type" style="width: 100%">
          <el-option v-for="t in ['review', 'chat', 'intent', 'embedding', 'rerank']" :key="t" :label="t" :value="t" />
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
  <el-dialog v-model="promptFormVisible" title="编辑提示词" width="760px">
    <el-form label-width="100px">
      <el-form-item label="模板名称"><el-select v-model="promptForm.prompt_name" :disabled="Boolean(promptForm.id)" filterable @change="selectTemplate"><el-option v-for="item in templates" :key="item.name" :label="item.name" :value="item.name" /></el-select></el-form-item>
      <el-form-item label="合同类型"><el-select v-model="promptForm.contract_type_id" :disabled="Boolean(promptForm.id)" clearable placeholder="全部类型"><el-option v-for="item in types" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item>
      <el-form-item label="内容"><el-input v-model="promptForm.prompt_content" type="textarea" :rows="15" /></el-form-item>
    </el-form>
    <template #footer><el-button @click="promptFormVisible = false">取消</el-button><el-button type="primary" @click="savePrompt">保存</el-button></template>
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
const modelForm = reactive({ model_name: '', model_type: 'chat', provider: 'openai-compatible', api_endpoint: 'https://api.deepseek.com', api_key: '', temperature: 0.7, top_p: 0.95, max_tokens: 4096, is_default: 1 })
const templates = ref<{ name: string; content: string }[]>([])
const promptFormVisible = ref(false)
const promptForm = reactive({ id: undefined as number | undefined, prompt_name: 'chat', prompt_content: '', contract_type_id: undefined as number | undefined, is_active: 1 })

onMounted(load)

async function load() {
  const [contractTypes, modelConfigs, promptTemplates, builtins] = await Promise.all([
    adminApi.contractTypes(),
    adminApi.modelConfigs(),
    adminApi.prompts(),
    adminApi.promptTemplates(),
  ])
  types.value = contractTypes
  models.value = modelConfigs
  prompts.value = promptTemplates
  templates.value = builtins
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
  await adminApi.createModelConfig({ ...modelForm })
  ElMessage.success('配置已保存，将用于后续请求')
  modelFormVisible.value = false
  await load()
}

async function removeModel(row: ModelConfig) {
  await adminApi.deleteModelConfig(row.id)
  await load()
}

async function setDefaultModel(row: ModelConfig) {
  await adminApi.updateModelConfig(row.id, { is_default: 1, status: 'active' })
  await load()
}
async function toggleModel(row: ModelConfig) {
  await adminApi.updateModelConfig(row.id, { status: row.status === 'active' ? 'inactive' : 'active' })
  await load()
}
function selectTemplate() {
  promptForm.prompt_content = templates.value.find((item) => item.name === promptForm.prompt_name)?.content || ''
}
function editPrompt(row?: PromptTemplate) {
  Object.assign(promptForm, { id: row?.id, prompt_name: row?.prompt_name || 'chat', prompt_content: row?.prompt_content || '', contract_type_id: row?.contract_type_id ?? undefined, is_active: row?.is_active ?? 1 })
  if (!row) selectTemplate()
  promptFormVisible.value = true
}
async function savePrompt() {
  await adminApi.savePrompt({ ...promptForm, contract_type_id: promptForm.contract_type_id || null, level: 'system' })
  promptFormVisible.value = false
  ElMessage.success('提示词已保存，将用于后续请求')
  await load()
}
async function togglePrompt(row: PromptTemplate) {
  await adminApi.savePrompt({ ...row, is_active: row.is_active ? 0 : 1 })
  await load()
}
async function deletePrompt(row: PromptTemplate) {
  await adminApi.deletePrompt(row.id)
  await load()
}
</script>

<style scoped>
.row { display: flex; align-items: center; }
</style>
