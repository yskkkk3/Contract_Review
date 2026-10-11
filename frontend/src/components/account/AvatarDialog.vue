<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { ElDialog, ElMessage } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { AVATAR_ACCEPT, avatarFileError } from '@/utils/avatar'
import AppButton from '@/components/ui/AppButton.vue'
import AppTypography from '@/components/ui/AppTypography.vue'
import AppUserAvatar from '@/components/ui/AppUserAvatar.vue'

const open = defineModel<boolean>({ required: true })
const emit = defineEmits<{ closed: [] }>()
const auth = useAuthStore()
const editor = ref<HTMLElement>()
const fileInput = ref<HTMLInputElement>()
const selectedFile = ref<File>()
const previewUrl = ref('')
const saving = ref(false)
const resetting = ref(false)
const busy = computed(() => saving.value || resetting.value)

function resetSelection() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  selectedFile.value = undefined
}
onUnmounted(resetSelection)

function onClosed() {
  resetSelection()
  emit('closed')
}

function focusEditor() {
  editor.value?.querySelector<HTMLButtonElement>('button')?.focus()
}

function selectFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const error = avatarFileError(file)
  if (error) return ElMessage.warning(error)
  resetSelection()
  selectedFile.value = file
  previewUrl.value = URL.createObjectURL(file)
}

async function save() {
  if (!selectedFile.value || busy.value) return
  saving.value = true
  try {
    await auth.uploadAvatar(selectedFile.value)
    ElMessage.success('头像已更新')
    open.value = false
  } catch {
    // The shared HTTP layer displays the API error; keep the selection for retry.
  } finally {
    saving.value = false
  }
}

async function remove() {
  if (busy.value) return
  resetting.value = true
  try {
    await auth.removeAvatar()
    ElMessage.success('已恢复默认头像')
    open.value = false
  } catch {
    // Keep the saved avatar when the request fails.
  } finally {
    resetting.value = false
  }
}
</script>

<template>
  <ElDialog v-model="open" class="design-system avatar-dialog" modal-class="avatar-dialog-overlay" title="更换头像" width="min(var(--avatar-dialog-width), calc(100vw - var(--space-10)))" append-to-body destroy-on-close :close-on-click-modal="!busy" :close-on-press-escape="!busy" :show-close="!busy" @opened="focusEditor" @closed="onClosed">
    <div ref="editor" class="avatar-editor" :aria-busy="busy">
      <AppUserAvatar :username="auth.user?.username || ''" :src="previewUrl || auth.avatarUrl" size="large" />
      <AppTypography variant="small" tone="secondary">选择图片预览，保存后更新头像。</AppTypography>
      <input ref="fileInput" type="file" :accept="AVATAR_ACCEPT" hidden aria-label="选择头像图片" @change="selectFile" />
      <AppButton variant="secondary" :disabled="busy" aria-describedby="avatar-upload-hint" @click="fileInput?.click()"><Upload class="avatar-upload-icon" aria-hidden="true" />选择图片</AppButton>
      <AppTypography id="avatar-upload-hint" variant="caption" tone="secondary">支持 JPG、PNG、WebP，最大 5 MB</AppTypography>
      <AppTypography v-if="selectedFile" variant="caption" tone="secondary" class="avatar-filename" aria-live="polite">{{ selectedFile.name }}</AppTypography>
    </div>
    <template #footer>
      <div class="avatar-dialog-actions">
        <AppButton v-if="auth.user?.avatar_url" class="avatar-reset" variant="ghost" :loading="resetting" :disabled="saving" @click="remove">恢复默认</AppButton>
        <AppButton variant="secondary" :disabled="busy" @click="open = false">取消</AppButton>
        <AppButton :loading="saving" :disabled="!selectedFile || resetting" @click="save">保存头像</AppButton>
      </div>
    </template>
  </ElDialog>
</template>

<style scoped>
.avatar-editor { display: flex; flex-direction: column; align-items: center; gap: var(--space-4); padding-block: var(--space-6); text-align: center; }
.avatar-upload-icon { width: var(--icon-size); height: var(--icon-size); margin-right: var(--space-2); }
.avatar-filename { max-width: 100%; overflow-wrap: anywhere; }
.avatar-dialog-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: var(--space-2); }
.avatar-reset { margin-right: auto; }
</style>
