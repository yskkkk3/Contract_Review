import { defineStore } from 'pinia'
import { authApi } from '@/api/auth'
import { TOKEN_KEY } from '@/api/http'
import type { UserInfo } from '@/types/api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || '',
    user: null as UserInfo | null,
  }),
  getters: {
    isLoggedIn: (s) => !!s.token,
  },
  actions: {
    async login(identifier: string, password: string) {
      const result = await authApi.login(identifier, password)
      this.token = result.access_token
      localStorage.setItem(TOKEN_KEY, result.access_token)
      await this.fetchMe()
    },
    async register(username: string, password: string, displayName?: string, department?: string) {
      await authApi.register(username, password, displayName, department)
    },
    async fetchMe() {
      if (!this.token) return
      this.user = await authApi.me()
    },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem(TOKEN_KEY)
    },
  },
})
