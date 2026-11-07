import { useCallback, useEffect, useRef, useState } from 'react'

// In dev, Vite proxies /api (including WebSockets) to the FastAPI backend.
// Set VITE_WS_BASE (e.g. wss://api.example.com) if the backend is hosted elsewhere.
const WS_BASE =
  import.meta.env.VITE_WS_BASE || `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`
const MAX_CAPTIONS = 40

const INITIAL_INFO = { mock: false, listeners: 0, speakerActive: false, slide: null, languages: [], isSpeaker: false }

function upsertCaption(list, message) {
  const index = list.findIndex((caption) => caption.id === message.id)
  if (index >= 0) {
    const next = [...list]
    const existing = next[index]
    next[index] = {
      ...existing,
      original: message.original,
      slide: message.slide,
      // If the server restarted, ids can repeat with different text: drop stale translations.
      translations: existing.original === message.original ? existing.translations : {},
    }
    return next
  }
  return [...list, { id: message.id, original: message.original, slide: message.slide, translations: {} }].slice(
    -MAX_CAPTIONS,
  )
}

/**
 * Connects to the caption WebSocket for a lecture.
 *
 * Everyone listens in their own `lang`. A connection opened with `speaker: true`
 * can also push the lecture text (`sendInterim`, `sendFinal`, `sendSlide`).
 *
 * `captions` is [{ id, original, slide, translations: { [lang]: { text, failed } } }].
 * The original arrives first; translations fill in afterwards.
 */
export function useLiveCaptions({ lectureId, lang, speaker = false, speakerKey = '', onSlide }) {
  const [status, setStatus] = useState('connecting') // connecting | live | reconnecting
  const [captions, setCaptions] = useState([])
  const [interim, setInterim] = useState('')
  const [info, setInfo] = useState(INITIAL_INFO)
  const [error, setError] = useState('')

  const wsRef = useRef(null)
  const langRef = useRef(lang)
  const onSlideRef = useRef(onSlide)

  useEffect(() => {
    onSlideRef.current = onSlide
  })

  const send = useCallback((payload) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload))
      return true
    }
    return false
  }, [])

  // Language switches go over the open socket; no reconnect needed.
  useEffect(() => {
    langRef.current = lang
    send({ type: 'set_language', lang })
  }, [lang, send])

  useEffect(() => {
    let closed = false
    let attempt = 0
    let timer

    function handle(message) {
      switch (message.type) {
        case 'hello':
          setError('')
          setInfo((prev) => ({
            ...prev,
            mock: message.mock,
            slide: message.slide,
            languages: message.languages,
            isSpeaker: message.speaker,
          }))
          // A listener starts on the lecturer's current slide. A speaker drives it instead.
          if (!speaker && message.slide) onSlideRef.current?.(message.slide)
          break
        case 'presence':
          setInfo((prev) => ({ ...prev, listeners: message.listeners, speakerActive: message.speaker_active }))
          break
        case 'slide':
          setInfo((prev) => ({ ...prev, slide: message.slide }))
          if (!speaker) onSlideRef.current?.(message.slide)
          break
        case 'interim':
          setInterim(message.text)
          break
        case 'caption':
          setCaptions((prev) => upsertCaption(prev, message))
          break
        case 'translation':
          setCaptions((prev) =>
            prev.map((caption) =>
              caption.id === message.id
                ? {
                    ...caption,
                    translations: { ...caption.translations, [message.lang]: { text: message.text, failed: message.failed } },
                  }
                : caption,
            ),
          )
          break
        case 'error':
          setError(message.message)
          break
        default:
          break
      }
    }

    function connect() {
      const params = new URLSearchParams({ lang: langRef.current })
      if (speaker) {
        params.set('speaker', '1')
        if (speakerKey) params.set('key', speakerKey)
      }
      const ws = new WebSocket(`${WS_BASE}/api/ws/captions/${encodeURIComponent(lectureId)}?${params}`)
      wsRef.current = ws

      ws.onopen = () => {
        attempt = 0
        setStatus('live')
        // The language may have changed while we were connecting.
        ws.send(JSON.stringify({ type: 'set_language', lang: langRef.current }))
      }
      ws.onmessage = (event) => {
        try {
          handle(JSON.parse(event.data))
        } catch {
          // ignore malformed frames
        }
      }
      ws.onclose = () => {
        if (closed) return
        setStatus('reconnecting')
        setInterim('')
        timer = setTimeout(connect, Math.min(5000, 500 * 2 ** attempt))
        attempt += 1
      }
      ws.onerror = () => ws.close()
    }

    connect()
    return () => {
      closed = true
      clearTimeout(timer)
      wsRef.current?.close()
    }
  }, [lectureId, speaker, speakerKey])

  const sendInterim = useCallback((text) => send({ type: 'interim', text }), [send])
  const sendFinal = useCallback((text, slide) => send({ type: 'final', text, slide }), [send])
  const sendSlide = useCallback((slide) => send({ type: 'slide', slide }), [send])

  return { status, captions, interim, info, error, sendInterim, sendFinal, sendSlide }
}
