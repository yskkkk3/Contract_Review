/** SSE 工具：审阅与聊天两类事件流（fetch + ReadableStream，支持 Abort）。
 *  审阅: data 行 JSON 含 event 字段（message/end/error）
 *  聊天: data 行 JSON 含 type 字段（content/done/error）
 */
export type SseKind = 'review' | 'chat'

export interface SseOptions {
  url: string
  kind: SseKind
  token: string
  onEvent: (payload: unknown) => void
  signal?: AbortSignal
}

export function openSse({ url, kind, token, onEvent, signal }: SseOptions): () => void {
  const controller = new AbortController()
  const external = signal
  const abort = () => controller.abort()
  if (external) {
    if (external.aborted) controller.abort()
    else external.addEventListener('abort', abort, { once: true })
  }

  void (async () => {
    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        signal: controller.signal,
      })
      if (!resp.ok || !resp.body) {
        onEvent({ type: 'error', message: `SSE 连接失败: ${resp.status}` })
        return
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let idx: number
        while ((idx = buffer.indexOf('\n\n')) >= 0) {
          const chunk = buffer.slice(0, idx)
          buffer = buffer.slice(idx + 2)
          const line = chunk.split('\n').find((l) => l.startsWith('data:'))
          if (!line) continue
          const raw = line.slice(5).trim()
          if (!raw) continue
          try {
            onEvent(JSON.parse(raw))
          } catch {
            // 忽略无法解析的数据帧
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        onEvent({ type: 'error', message: 'SSE 连接中断' })
      }
    }
  })()

  return abort
}
