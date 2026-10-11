import { onMounted, onUnmounted, ref } from 'vue'

/** Opt-in, one-shot reveal. Content remains visible without JS/observer support. */
export function useReveal() {
  const root = ref<HTMLElement>()
  let observer: IntersectionObserver | undefined
  let preference: MediaQueryList | undefined
  let elements: HTMLElement[] = []

  const showAll = () => {
    observer?.disconnect()
    elements.forEach((element) => { element.dataset.revealState = 'visible' })
  }
  const onPreferenceChange = () => { if (preference?.matches) showAll() }

  onMounted(() => {
    preference = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (preference.matches || !('IntersectionObserver' in window)) return
    elements = Array.from(root.value?.querySelectorAll<HTMLElement>('[data-reveal]') ?? [])
    observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return
        const element = entry.target as HTMLElement
        element.dataset.revealState = 'visible'
        observer?.unobserve(element)
      })
    }, { threshold: .12 })
    elements.forEach((element) => {
      element.dataset.revealState = 'pending'
      observer?.observe(element)
    })
    preference.addEventListener('change', onPreferenceChange)
  })

  onUnmounted(() => {
    observer?.disconnect()
    preference?.removeEventListener('change', onPreferenceChange)
  })

  return root
}
