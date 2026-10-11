<template>
  <el-row :gutter="16" style="height: calc(100vh - 120px)">
    <el-col :span="6">
      <el-card shadow="hover" style="height: 100%">
        <template #header>会话列表</template>
        <el-button type="primary" size="small" style="width: 100%; margin-bottom: 12px" @click="newSession">新建会话</el-button>
        <div v-for="s in sessions" :key="s.session_id" class="session-item" :class="{ active: s.session_id === currentId }" @click="switchSession(s)">
          <div>{{ s.title }}</div>
          <div v-if="s.file_id" class="sub">{{ fileTitle(s.file_id) }}</div>
        </div>
      </el-card>
    </el-col>
    <el-col :span="18">
      <el-card shadow="hover" style="height: 100%; display: flex; flex-direction: column">
        <div class="messages" ref="msgRef">
          <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
            <div class="bubble">{{ m.content }}</div>
          </div>
        </div>
        <div class="input-row">
          <el-select v-model="bindFileId" placeholder="绑定合同（可选）" clearable style="width: 220px; margin-right: 12px">
            <el-option v-for="f in files" :key="f.file_id" :label="f.title" :value="f.file_id" />
          </el-select>
          <el-input
            v-model="input"
            type="textarea"
            :rows="2"
            placeholder="围绕合同提问，如：付款条款有什么风险？"
            @keydown.enter.exact.prevent="send"
          />
          <el-button type="primary" style="margin-left: 12px" :loading="sending" @click="send">发送</el-button>
        </div>
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/api/contract'
import { sessionApi } from '@/api/session'
import { TOKEN_KEY } from '@/api/http'
import { openSse } from '@/utils/sse'
import type { ContractFile, SessionInfo } from '@/types/api'

interface Msg {
  role: 'user' | 'assistant'
  content: string
}

const sessions = ref<SessionInfo[]>([])
const files = ref<ContractFile[]>([])
const currentId = ref<number>()
const bindFileId = ref<number>()
const messages = ref<Msg[]>([])
const input = ref('')
const sending = ref(false)
const msgRef = ref<HTMLElement>()
const abortRef = ref<(() => void) | null>(null)

onMounted(async () => {
  const data = await sessionApi.list('chat')
  sessions.value = data.items
  const fdata = await api.list(1, 100)
  files.value = fdata.items
})

async function newSession() {
  const s = await sessionApi.create(`问答-${Date.now()}`, 'chat', bindFileId.value)
  sessions.value.unshift(s)
  await switchSession(s)
}

async function switchSession(s: SessionInfo) {
  currentId.value = s.session_id
  messages.value = []
}

function fileTitle(fileId: number) {
  return files.value.find((f) => f.file_id === fileId)?.title || ''
}

async function send() {
  const content = input.value.trim()
  if (!content) return
  if (!currentId.value) {
    const s = await sessionApi.create(`问答-${Date.now()}`, 'chat', bindFileId.value)
    sessions.value.unshift(s)
    await switchSession(s)
  }
  messages.value.push({ role: 'user', content })
  input.value = ''
  sending.value = true
  let acc = ''
  abortRef.value = openSse({
    url: `${import.meta.env.VITE_API_BASE || '/api'}/chats`,
    kind: 'chat',
    token: localStorage.getItem(TOKEN_KEY) || '',
    onEvent: (payload) => {
      const ev = payload as { type: string; content?: string; message?: string }
      if (ev.type === 'content' && ev.content) {
        acc += ev.content
        const last = messages.value[messages.value.length - 1]
        if (last && last.role === 'assistant') last.content = acc
        else messages.value.push({ role: 'assistant', content: acc })
        scrollBottom()
      } else if (ev.type === 'done') {
        sending.value = false
      } else if (ev.type === 'error') {
        ElMessage.error(ev.message || '出错了')
        sending.value = false
      }
    },
  })
  scrollBottom()
}

function scrollBottom() {
  void nextTick(() => {
    if (msgRef.value) msgRef.value.scrollTop = msgRef.value.scrollHeight
  })
}
</script>

<style scoped>
.messages { flex: 1; overflow-y: auto; padding: 8px; }
.msg { margin-bottom: 12px; display: flex; }
.msg.user { justify-content: flex-end; }
.bubble { max-width: 70%; padding: 10px 14px; border-radius: 8px; background: #f0f2f5; line-height: 1.6; white-space: pre-wrap; }
.msg.user .bubble { background: #409eff; color: #fff; }
.input-row { display: flex; align-items: flex-end; padding-top: 12px; border-top: 1px solid #e5e7eb; }
.session-item { padding: 10px 12px; border-radius: 6px; cursor: pointer; margin-bottom: 4px; }
.session-item:hover { background: #f0f2f5; }
.session-item.active { background: #ecf5ff; color: #409eff; }
.sub { font-size: 12px; color: #999; margin-top: 2px; }
</style>
