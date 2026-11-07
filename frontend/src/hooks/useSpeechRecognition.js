import { useEffect, useRef, useState } from 'react'

// Browser speech-to-text (Chrome, Edge, Safari). Not available in Firefox.
const SpeechRecognition =
  typeof window !== 'undefined' ? window.SpeechRecognition || window.webkitSpeechRecognition : undefined

/**
 * Continuous speech-to-text with interim results.
 *
 * `onInterim(text)` fires as the current phrase is still changing.
 * `onFinal(text)` fires once per finished phrase.
 * The recogniser stops itself every so often (browser behaviour), so we restart it
 * until `enabled` goes false.
 */
export function useSpeechRecognition({ enabled, lang = 'en-GB', onInterim, onFinal }) {
  const [active, setActive] = useState(false)
  const [error, setError] = useState('')
  const handlers = useRef({ onInterim, onFinal })

  useEffect(() => {
    handlers.current = { onInterim, onFinal }
  })

  useEffect(() => {
    if (!enabled || !SpeechRecognition) return undefined

    let stopped = false
    let restartTimer
    const recognition = new SpeechRecognition()
    recognition.lang = lang
    recognition.continuous = true
    recognition.interimResults = true

    recognition.onstart = () => {
      setActive(true)
      setError('')
    }

    recognition.onresult = (event) => {
      let interim = ''
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i]
        const text = result[0].transcript.trim()
        if (!text) continue
        if (result.isFinal) handlers.current.onFinal?.(text)
        else interim += `${interim ? ' ' : ''}${text}`
      }
      handlers.current.onInterim?.(interim)
    }

    recognition.onerror = (event) => {
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
        stopped = true
        setError('Microphone permission was blocked. Allow it in your browser and try again.')
      } else if (event.error === 'audio-capture') {
        stopped = true
        setError('No microphone was found.')
      }
      // 'no-speech', 'network' and 'aborted' are transient: onend restarts below.
    }

    recognition.onend = () => {
      setActive(false)
      if (!stopped) {
        restartTimer = setTimeout(() => {
          try {
            recognition.start()
          } catch {
            // already started
          }
        }, 500)
      }
    }

    try {
      recognition.start()
    } catch {
      // already started
    }

    return () => {
      stopped = true
      clearTimeout(restartTimer)
      recognition.onend = null
      recognition.onresult = null
      recognition.onerror = null
      try {
        recognition.abort()
      } catch {
        // not running
      }
    }
  }, [enabled, lang])

  return { supported: Boolean(SpeechRecognition), listening: enabled && active, error: enabled ? error : '' }
}
