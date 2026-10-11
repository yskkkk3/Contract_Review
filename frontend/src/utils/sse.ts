/** SSE 工具：审阅与聊天两类事件流（fetch + ReadableStream，支持 Abort）。
 *  审阅: data 行 JSON 含 event 字段（message/end/error）
 *  聊天: data 行 JSON 含 type 字段（content/done/error）
 */
export type SseKind = 'review' | 'chat'

export interface SseOptions {
  url: string
  kind: SseKind
  token: string
  body?: unknown
  onEvent: (payload: unknown) => void
  signal?: AbortSignal
}

export function openSse({ url, kind, token, body, onEvent, signal }: SseOptions): () => void {
  void kind
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
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      })
      if (!resp.ok || !resp.body) {
        let message = `SSE 连接失败: ${resp.status}`
        try {
          const errorBody = (await resp.json()) as { msg?: string; detail?: string }
          message = errorBody.msg || errorBody.detail || message
        } catch {
          // 非 JSON 错误响应保留 HTTP 状态信息
        }
        onEvent({ type: 'error', event: 'error', message, data: { message } })
        return
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        buffer = buffer.replace(/\r\n/g, '\n')
        let idx: number
        while ((idx = buffer.indexOf('\n\n')) >= 0) {
          const chunk = buffer.slice(0, idx)
          buffer = buffer.slice(idx + 2)
          const raw = chunk
            .split('\n')
            .filter((line) => line.startsWith('data:'))
            .map((line) => line.slice(5).trimStart())
            .join('\n')
          if (!raw) continue
          try {
            onEvent(JSON.parse(raw))
          } catch {
            // 忽略无法解析的数据帧
          }
        }
      }
      buffer += decoder.decode()
      const raw = buffer
        .replace(/\r\n/g, '\n')
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart())
        .join('\n')
      if (raw) {
        try {
          onEvent(JSON.parse(raw))
        } catch {
          // 忽略不完整的末尾数据帧
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        const message = 'SSE 连接中断'
        onEvent({ type: 'error', event: 'error', message, data: { message } })
      }
    }
  })()

  return abort
}
