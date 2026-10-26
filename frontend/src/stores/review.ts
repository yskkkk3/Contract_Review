import { defineStore } from 'pinia'
import { api } from '@/api/contract'
import { reviewApi } from '@/api/review'
import type { ContractFile, ContractType, ReviewJob, RiskPoint } from '@/types/api'

// Timers belong to the application store, not to a route component.
const timers = new WeakMap<object, ReturnType<typeof setTimeout>>()
const active = (job: ReviewJob) => ['processing', 'cancelling'].includes(job.status)

export const useReviewStore = defineStore('review', {
  state: () => ({
    ownerId: null as number | null,
    generation: 0,
    refreshSequence: 0,
    jobs: [] as ReviewJob[],
    selectedId: '',
    editingDraft: false,
    fileId: undefined as number | undefined,
    contractType: '',
    stance: '甲方' as '甲方' | '乙方',
    intensity: '标准' as '严格' | '标准' | '宽松',
    description: '',
    supplementFileIds: [] as number[],
    submitting: false,
    cancelRequested: false,
    stopping: false,
    connectionError: '',
  }),
  getters: {
    selected: (state) => state.jobs.find((job) => job.id === state.selectedId),
    activeJobs: (state) => state.jobs.filter(active),
    running(): boolean { return this.submitting || Boolean(this.selected && active(this.selected)) },
  },
  actions: {
    async connect(userId: number | null) {
      if (this.ownerId === userId) return
      clearTimeout(timers.get(this))
      const generation = this.generation + 1
      this.$reset()
      this.generation = generation
      this.ownerId = userId
      if (userId !== null) await this.refresh()
    },
    async refresh() {
      clearTimeout(timers.get(this))
      if (this.ownerId === null) return
      const generation = this.generation
      const sequence = ++this.refreshSequence
      try {
        const jobs = await reviewApi.list()
        if (this.generation !== generation || this.refreshSequence !== sequence) return
        this.jobs = jobs
        this.connectionError = ''
        if (!this.editingDraft && (!this.selectedId || !jobs.some((job) => job.id === this.selectedId))) {
          const job = jobs[0]
          if (job) this.select(job.id)
        }
      } catch {
        if (this.generation !== generation || this.refreshSequence !== sequence) return
        this.connectionError = '暂时无法获取进度，后台任务仍会继续，正在重新连接'
      }
      if (this.generation === generation && this.refreshSequence === sequence && (this.activeJobs.length || this.connectionError)) {
        timers.set(this, setTimeout(() => { void this.refresh() }, this.connectionError ? 5000 : 2000))
      }
    },
    select(id: string) {
      this.editingDraft = false
      this.selectedId = id
      const job = this.selected
      if (!job) return
      this.fileId = job.file_id
      this.contractType = job.contract_type
      this.stance = job.stance
      this.intensity = job.intensity
      this.description = job.description
      this.supplementFileIds = [...(job.supplement_file_ids || [])]
    },
    prepareFromHistory(data: Pick<ReviewJob, 'file_id' | 'contract_type' | 'stance' | 'intensity' | 'description'> &
      { supplement_file_ids?: number[] }) {
      if (this.submitting) throw new Error('正在发起审阅，请稍后重试')
      this.editingDraft = true
      this.selectedId = ''
      this.fileId = data.file_id
      this.contractType = data.contract_type
      this.stance = data.stance
      this.intensity = data.intensity
      this.description = data.description
      this.supplementFileIds = [...(data.supplement_file_ids || [])]
    },
    async start(files: ContractFile[], types: ContractType[]) {
      if (this.submitting || this.ownerId === null || !this.fileId) return
      if (this.activeJobs.some((job) => job.file_id === this.fileId)) {
        throw new Error('该合同已有审阅进行中，请先查看或停止现有任务')
      }
      this.submitting = true
      this.cancelRequested = false
      const generation = this.generation
      const fileId = this.fileId
      const options = { stance: this.stance, intensity: this.intensity,
        description: this.description, contract_type: this.contractType,
        supplement_file_ids: [...this.supplementFileIds] }
      let sessionId: number | undefined
      try {
        const selectedType = types.find((type) => type.name === options.contract_type)
        const selectedFile = files.find((file) => file.id === fileId)
        if (selectedType && selectedFile) {
          await api.setType(selectedFile.id, selectedType.id, options.stance === '乙方' ? 1 : 0)
          if (this.generation !== generation || this.cancelRequested) return
          selectedFile.contract_type_id = selectedType.id
          selectedFile.review_position = options.stance === '乙方' ? 1 : 0
        }
        if (this.generation !== generation || this.cancelRequested) return
        const session = await api.createSession(`审阅-${Date.now()}`, 'review', fileId)
        sessionId = session.session_id
        if (this.generation !== generation || this.cancelRequested) return
        let job = await reviewApi.start({ session_id: session.session_id, ...options })
        if (this.generation !== generation) return
        if (this.cancelRequested) job = await reviewApi.cancel(job.id)
        if (this.generation !== generation) return
        this.jobs = [job, ...this.jobs.filter((item) => item.id !== job.id)]
        this.editingDraft = false
        this.selectedId = job.id
        await this.refresh()
      } catch (error) {
        if (this.generation === generation) {
          // A lost start response must not hide a task already accepted by the server.
          await this.refresh()
          const accepted = this.jobs.find((job) => job.session_id === sessionId && active(job))
          if (this.cancelRequested && accepted) {
            await reviewApi.cancel(accepted.id)
            await this.refresh()
          }
        }
        throw error
      } finally {
        if (this.generation === generation) this.submitting = false
      }
    },
    async stop(id?: string) {
      if (this.submitting && !id) {
        this.cancelRequested = true
        return
      }
      id = id || this.selectedId
      if (this.stopping || !this.jobs.some((job) => job.id === id && active(job))) return
      this.stopping = true
      const generation = this.generation
      try {
        const job = await reviewApi.cancel(id)
        if (this.generation !== generation) return
        this.jobs = this.jobs.map((item) => item.id === id ? job : item)
        await this.refresh()
      } finally {
        if (this.generation === generation) this.stopping = false
      }
    },
    async accept(point: RiskPoint) {
      if (!point.id || !point.task_id || !point.session_id) return
      const current = this.selected?.risk_points.find((item) => item.id === point.id)
      if (!current) return
      const accepted = current.is_accepted ? 0 : 1
      await api.acceptRiskPoint(point.task_id, point.session_id, point.index, Boolean(accepted))
      current.is_accepted = accepted
    },
    async recordMaterialDecision(
      id: string,
      decision: 'deferred' | 'supplemented',
      supplementFileIds: number[] = [],
    ) {
      const updated = await reviewApi.materialDecision(id, decision, supplementFileIds)
      this.jobs = this.jobs.map((item) => item.id === id ? updated : item)
      return updated
    },
  },
})
