type SessionExpiryHandler = (redirect: string) => void | Promise<void>

let handler: SessionExpiryHandler | null = null
let handling = false

export function installSessionExpiryHandler(nextHandler: SessionExpiryHandler) {
  handler = nextHandler
}

export function resetSessionExpiryCoordinator() {
  handling = false
}

export async function notifySessionExpired(redirect: string) {
  if (handling || !handler) return
  handling = true
  await handler(redirect)
}
