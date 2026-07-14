export type ProgressMessage = { task_id: string; status: string; progress: number; current_step: string }

export function subscribeTaskProgress(taskId: string, onMessage: (data: ProgressMessage) => void) {
  const base = import.meta.env.VITE_WS_URL
  if (!base) return () => undefined
  const token = sessionStorage.getItem('studypilot_token') || ''
  const socket = new WebSocket(`${base}/${taskId}?token=${encodeURIComponent(token)}`)
  socket.onmessage = (event) => onMessage(JSON.parse(event.data) as ProgressMessage)
  socket.onerror = () => socket.close()
  return () => socket.close()
}
