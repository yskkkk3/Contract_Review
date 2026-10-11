import { defineStore } from 'pinia'
import { authApi } from '@/api/auth'
import { avatarApi } from '@/api/avatar'
import { TOKEN_KEY } from '@/api/http'
import type { UserInfo } from '@/types/api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || '',
    user: null as UserInfo | null,
    avatarUrl: '',
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
    async register(username: string, password: string) {
      await authApi.register(username, password)
    },
    async fetchMe() {
      if (!this.token) return
      this.user = await authApi.me()
      void this.loadAvatar()
    },
    clearAvatar() {
      if (this.avatarUrl) URL.revokeObjectURL(this.avatarUrl)
      this.avatarUrl = ''
    },
    async loadAvatar() {
      const user = this.user
      if (!this.token || !user?.avatar_url) {
        this.clearAvatar()
        return
      }
      try {
        const image = await avatarApi.read()
        // Ignore a download belonging to a logged-out or replaced profile.
        if (this.user !== user) return
        this.clearAvatar()
        this.avatarUrl = URL.createObjectURL(image)
      } catch {
        if (this.user === user) this.clearAvatar()
      }
    },
    async uploadAvatar(file: File) {
      const token = this.token
      const user = await avatarApi.upload(file)
      if (this.token !== token) return
      this.user = user
      await this.loadAvatar()
    },
    async removeAvatar() {
      const token = this.token
      const user = await avatarApi.remove()
      if (this.token !== token) return
      this.user = user
      this.clearAvatar()
    },
    logout() {
      this.clearAvatar()
      this.token = ''
      this.user = null
      localStorage.removeItem(TOKEN_KEY)
    },
  },
})
