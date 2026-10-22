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
          <div v-if="replyStatus" class="reply-status" role="status" aria-live="polite">{{ replyStatus }}</div>
        </div>
        <div class="input-row">
          <el-select v-model="bindFileId" placeholder="绑定合同（可选）" clearable style="width: 220px; margin-right: 12px">
            <el-option v-for="f in files" :key="f.id" :label="f.title" :value="f.id" />
          </el-select>
          <el-input
            v-model="input"
            type="textarea"
            :rows="2"
            placeholder="围绕合同提问，如：付款条款有什么风险？"
            @keydown.enter.exact.prevent="send"
          />
          <el-button type="primary" style="margin-left: 12px" :loading="sending" :disabled="loadingHistory" @click="send">发送</el-button>
          <el-button v-if="sending" @click="stopReply">停止</el-button>
        </div>
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/api/contract'
import { sessionApi } from '@/api/session'
import { TOKEN_KEY } from '@/api/http'
import { openSse } from '@/utils/sse'
import type { ContractFile, MessageInfo, SessionInfo } from '@/types/api'

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
const replyStatus = ref('')
const msgRef = ref<HTMLElement>()
const abortRef = ref<(() => void) | null>(null)
const loadingHistory = ref(false)
let sessionVersion = 0
let requestVersion = 0

onMounted(async () => {
  const [sessionData, contractData] = await Promise.all([sessionApi.list('chat'), api.list()])
  sessions.value = sessionData.items
  files.value = contractData.filter((file) => file.parse_status === 'parsed')
})

onUnmounted(() => {
  sessionVersion += 1
  abortRef.value?.()
})

function newSession() {
  sessionVersion += 1
  abortRef.value?.()
  currentId.value = undefined
  bindFileId.value = undefined
  messages.value = []
  input.value = ''
  sending.value = false
  replyStatus.value = ''
  loadingHistory.value = false
}

async function switchSession(s: SessionInfo) {
  const version = ++sessionVersion
  abortRef.value?.()
  sending.value = false
  replyStatus.value = ''
  loadingHistory.value = true
  currentId.value = s.session_id
  bindFileId.value = s.file_id ?? undefined
  messages.value = []
  try {
    const history = await sessionApi.history(s.session_id)
    if (version !== sessionVersion) return
    messages.value = history.map(toMessage)
    scrollBottom()
  } finally {
    if (version === sessionVersion) loadingHistory.value = false
  }
}

function fileTitle(fileId: number) {
  return files.value.find((f) => f.id === fileId)?.title || ''
}

function stopReply() {
  requestVersion += 1
  abortRef.value?.()
  abortRef.value = null
  sending.value = false
  replyStatus.value = '已停止，当前回答尚未完成'
}

async function send() {
  if (sending.value || loadingHistory.value) return
  const content = input.value.trim()
  if (!content) return
  const version = sessionVersion
  const requestId = ++requestVersion
  const isCurrent = () => version === sessionVersion && requestId === requestVersion
  sending.value = true
  replyStatus.value = '正在准备合同和会话…'
  try {
    if (!currentId.value) {
      const s = await sessionApi.create(`问答-${Date.now()}`, 'chat', bindFileId.value)
      if (!isCurrent()) return
      sessions.value.unshift(s)
      currentId.value = s.session_id
      bindFileId.value = s.file_id ?? undefined
      const history = await sessionApi.history(s.session_id)
      if (!isCurrent()) return
      messages.value = history.map(toMessage)
    }
  } catch {
    if (isCurrent()) {
      sending.value = false
      replyStatus.value = '会话准备失败，请重试'
    }
    return
  }
  messages.value.push({ role: 'user', content })
  input.value = ''
  let acc = ''
  abortRef.value = openSse({
    url: `${import.meta.env.VITE_API_BASE || '/api'}/chats`,
    kind: 'chat',
    token: localStorage.getItem(TOKEN_KEY) || '',
    body: { session_id: currentId.value, content },
    onEvent: (payload) => {
      if (!isCurrent()) return
      const ev = payload as { type: string; content?: string; message?: string }
      if (ev.type === 'content' && ev.content) {
        replyStatus.value = '正在生成回答…'
        acc += ev.content
        const last = messages.value[messages.value.length - 1]
        if (last && last.role === 'assistant') last.content = acc
        else messages.value.push({ role: 'assistant', content: acc })
        scrollBottom()
      } else if (ev.type === 'done') {
        sending.value = false
        replyStatus.value = ''
        abortRef.value = null
      } else if (ev.type === 'error') {
        ElMessage.error(ev.message || '出错了')
        sending.value = false
        replyStatus.value = ev.message || '回答生成失败，请重试'
        abortRef.value = null
      } else if (ev.type === 'start') {
        replyStatus.value = '正在等待回答…'
      } else if (ev.type === 'status') {
        replyStatus.value = '正在分析合同…'
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

function toMessage(message: MessageInfo): Msg {
  return { role: message.role, content: message.content }
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
.reply-status { padding: 8px 0; color: #606266; font-size: 13px; }
</style>
