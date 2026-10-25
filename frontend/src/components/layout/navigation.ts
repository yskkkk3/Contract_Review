import type { Component } from 'vue'
import { ChatDotRound, CopyDocument, DocumentChecked, FolderOpened, Odometer, Setting } from '@element-plus/icons-vue'

export interface NavigationItem {
  name: string
  path: string
  label: string
  icon: Component
  adminOnly?: boolean
}

export const APP_NAVIGATION: NavigationItem[] = [
  { name: 'dashboard', path: '/dashboard', label: '工作台', icon: Odometer },
  { name: 'contracts', path: '/contracts', label: '合同管理', icon: FolderOpened },
  { name: 'review', path: '/review', label: '智能审阅', icon: DocumentChecked },
  { name: 'review-history', path: '/review-history', label: '审阅历史', icon: FolderOpened },
  { name: 'compare', path: '/compare', label: '合同比对', icon: CopyDocument },
  { name: 'chat', path: '/chat', label: '智能问答', icon: ChatDotRound },
  { name: 'admin', path: '/admin', label: '系统配置', icon: Setting, adminOnly: true },
]
