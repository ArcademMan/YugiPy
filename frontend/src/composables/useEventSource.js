import { ref, onUnmounted } from 'vue'

/**
 * Composable for EventSource (SSE) streaming with auto-cleanup.
 */
export function useEventSource() {
  const data = ref(null)
  const error = ref(null)
  const isActive = ref(false)
  let source = null

  function start(url, { onMessage, onError, onDone } = {}) {
    stop()
    isActive.value = true
    error.value = null
    source = new EventSource(url)

    source.onmessage = (event) => {
      try {
        data.value = JSON.parse(event.data)
      } catch {
        data.value = event.data
      }
      if (onMessage) onMessage(data.value)
      if (data.value?.type === 'done' || data.value?.type === 'cancelled') {
        stop()
        if (onDone) onDone(data.value)
      }
    }

    source.onerror = (e) => {
      error.value = e
      stop()
      if (onError) onError(e)
    }
  }

  function stop() {
    if (source) {
      source.close()
      source = null
    }
    isActive.value = false
  }

  onUnmounted(stop)

  return { data, error, isActive, start, stop }
}
