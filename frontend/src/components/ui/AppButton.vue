<script setup lang="ts">
import { ElButton } from 'element-plus'

withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'ghost'
  size?: 'small' | 'default' | 'large'
  loading?: boolean
  disabled?: boolean
  nativeType?: 'button' | 'submit' | 'reset'
  href?: string
}>(), { variant: 'primary', size: 'default', loading: false, disabled: false, nativeType: 'button' })
</script>

<template>
  <ElButton class="app-button" :class="[`app-button--${variant}`, `app-button--${size}`]" :type="variant === 'primary' ? 'primary' : undefined" :loading="loading" :disabled="disabled" :native-type="nativeType" :tag="href ? 'a' : 'button'" :href="disabled || loading ? undefined : href" :aria-disabled="disabled || undefined" :tabindex="disabled ? -1 : undefined" :aria-busy="loading">
    <slot />
  </ElButton>
</template>

<style scoped>
.app-button.el-button { height: var(--button-height); margin: 0; padding-inline: var(--space-5); border-radius: var(--radius-button); font-size: var(--font-small); font-weight: var(--weight-medium); transition: transform var(--duration-fast) var(--ease-out), background var(--duration-fast) var(--ease-out), border-color var(--duration-fast) var(--ease-out), box-shadow var(--duration-fast) var(--ease-out); }
.app-button--small.el-button { height: var(--button-height-small); padding-inline: var(--space-4); }
.app-button--large.el-button { height: var(--button-height-large); padding-inline: var(--space-6); }
.app-button--secondary.el-button { color: var(--color-text); background: var(--color-canvas); border-color: var(--color-border-hover); }
.app-button--ghost.el-button { color: var(--color-text); border-color: transparent; background: transparent; }
.app-button.el-button:not(.is-disabled, .is-loading):hover { transform: translateY(-1px); box-shadow: var(--shadow-float); }
.app-button--secondary.el-button:not(.is-disabled):hover, .app-button--ghost.el-button:not(.is-disabled):hover { background: var(--color-surface); border-color: var(--color-border-hover); }
.app-button.el-button.is-disabled { opacity: .55; }
.app-button.el-button:focus-visible { outline: 2px solid var(--color-accent); outline-offset: var(--space-1); }
@media (prefers-reduced-motion: reduce) {
  .app-button.el-button:not(.is-disabled, .is-loading):hover { transform: none; }
}
</style>
