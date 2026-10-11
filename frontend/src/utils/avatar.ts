export const MAX_AVATAR_BYTES = 5 * 1024 * 1024
export const AVATAR_ACCEPT = 'image/jpeg,image/png,image/webp'

export function avatarFileError(file: Pick<File, 'size' | 'type'>): string | undefined {
  if (!AVATAR_ACCEPT.split(',').includes(file.type)) return '请选择 JPG、PNG 或 WebP 图片'
  if (!file.size) return '图片不能为空'
  if (file.size > MAX_AVATAR_BYTES) return '头像大小不能超过 5 MB'
}
