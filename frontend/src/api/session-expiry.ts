type SessionExpiryHandler = (redirect: string) => void | Promise<void>

let handler: SessionExpiryHandler | null = null
let handlingPromise: Promise<void> | null = null
let suppressed = false

export function installSessionExpiryHandler(nextHandler: SessionExpiryHandler) {
  handler = nextHandler
}

export function resetSessionExpiryCoordinator() {
  handlingPromise = null
  suppressed = false
}

export function suppressSessionExpiryCoordinator() {
  suppressed = true
}

export async function notifySessionExpired(redirect: string) {
  if (suppressed || !handler) return
  if (handlingPromise) return handlingPromise

  handlingPromise = Promise.resolve(handler(redirect))
    .then(() => {
      suppressed = true
    })
    .catch((error) => {
      suppressed = false
      throw error
    })
    .finally(() => {
      handlingPromise = null
    })
  return handlingPromise
}
