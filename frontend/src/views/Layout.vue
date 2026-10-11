<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="brand">
        <svg class="brand-logo" viewBox="0 0 48 48" width="30" height="30" aria-hidden="true">
          <defs>
            <linearGradient id="lg1" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stop-color="#60a5fa" />
              <stop offset="1" stop-color="#2563eb" />
            </linearGradient>
          </defs>
          <path
            d="M24 4l14 5.2v11.6c0 9.1-5.9 16.6-14 20.2-8.1-3.6-14-11.1-14-20.2V9.2L24 4z"
            fill="url(#lg1)"
          />
          <path d="M16 24.5l5.5 5.5L32.5 18.5" stroke="#fff" stroke-width="3.4" fill="none" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <span class="brand-name">合同智能审阅</span>
      </div>
      <el-menu
        :default-active="route.path"
        router
        background-color="transparent"
        text-color="#a8b8d8"
        active-text-color="#fff"
      >
        <el-menu-item index="/dashboard">
          <el-icon><Odometer /></el-icon><span>工作台</span>
        </el-menu-item>
        <el-menu-item index="/contracts">
          <el-icon><FolderOpened /></el-icon><span>合同管理</span>
        </el-menu-item>
        <el-menu-item index="/review">
          <el-icon><DocumentChecked /></el-icon><span>智能审阅</span>
        </el-menu-item>
        <el-menu-item index="/compare">
          <el-icon><CopyDocument /></el-icon><span>合同比对</span>
        </el-menu-item>
        <el-menu-item index="/chat">
          <el-icon><ChatDotRound /></el-icon><span>智能问答</span>
        </el-menu-item>
        <el-menu-item index="/admin">
          <el-icon><Setting /></el-icon><span>系统配置</span>
        </el-menu-item>
      </el-menu>
      <div class="aside-footer">v0.3.0 · LangGraph + RAG</div>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div class="header-left">
          <span class="title">{{ title }}</span>
          <span class="subtitle">高校采购合同智能审阅 Agent</span>
        </div>
        <el-dropdown @command="onCommand">
          <span class="user">
            <el-avatar :size="30" class="avatar">{{ avatarText }}</el-avatar>
            <span class="user-name">{{ auth.user?.display_name || auth.user?.username }}</span>
            <el-icon class="caret"><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown, ChatDotRound, CopyDocument, DocumentChecked, FolderOpened, Odometer, Setting } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const TITLES: Record<string, string> = {
  dashboard: '工作台',
  contracts: '合同管理',
  review: '智能审阅',
  compare: '合同比对',
  chat: '智能问答',
  admin: '系统配置',
}

const title = computed(() => TITLES[route.name as string] || '合同智能审阅')
const avatarText = computed(() => {
  const name = auth.user?.display_name || auth.user?.username || 'U'
  return name.slice(0, 1).toUpperCase()
})

onMounted(() => {
  if (!auth.user) auth.fetchMe()
})

function onCommand(cmd: string) {
  if (cmd === 'logout') {
    auth.logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.layout {
  height: 100vh;
}

.aside {
  background: linear-gradient(180deg, #0f172a 0%, #1e3a8a 100%);
  display: flex;
  flex-direction: column;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 22px 18px 18px;
}

.brand-name {
  color: #fff;
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0.5px;
  white-space: nowrap;
}

.aside :deep(.el-menu) {
  border-right: none;
  flex: 1;
}

.aside :deep(.el-menu-item) {
  margin: 2px 10px;
  border-radius: 8px;
  height: 44px;
  line-height: 44px;
}

.aside :deep(.el-menu-item.is-active) {
  background: linear-gradient(90deg, rgba(37, 99, 235, 0.85), rgba(37, 99, 235, 0.4));
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.35);
}

.aside :deep(.el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.08);
}

.aside-footer {
  padding: 14px 20px;
  font-size: 12px;
  color: rgba(168, 184, 216, 0.7);
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #eef1f6;
  height: 60px;
}

.header-left {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.title {
  font-size: 17px;
  font-weight: 600;
  color: #1e293b;
}

.subtitle {
  font-size: 12px;
  color: #94a3b8;
}

.user {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 10px;
  border-radius: 8px;
  transition: background 0.2s;
}

.user:hover {
  background: #f1f5f9;
}

.avatar {
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  color: #fff;
  font-weight: 600;
}

.user-name {
  color: #334155;
  font-size: 14px;
}

.caret {
  color: #94a3b8;
  font-size: 12px;
}

.main {
  background: #f3f5f9;
  overflow-y: auto;
}
</style>
