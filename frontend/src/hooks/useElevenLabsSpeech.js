import { useEffect, useRef, useState } from 'react'

/** Microphone -> Scribe realtime -> the existing text-only caption socket. */
export function useElevenLabsSpeech({ enabled, speakerKey, onInterim, onFinal }) {
  const [listening, setListening] = useState(false)
  const [error, setError] = useState('')
  const handlers = useRef({ onInterim, onFinal })

  useEffect(() => {
    handlers.current = { onInterim, onFinal }
  })

  useEffect(() => {
    if (!enabled) return undefined

    let closed = false
    let connection

    async function start() {
      try {
        setListening(false)
        setError('')
        const response = await fetch('/api/captions/scribe-token', {
          method: 'POST',
          headers: speakerKey ? { 'X-Speaker-Key': speakerKey } : {},
        })
        if (!response.ok) {
          let detail
          try { detail = (await response.json()).detail } catch { /* proxy error */ }
          throw new Error(typeof detail === 'string' ? detail : 'Could not connect to ElevenLabs. Check the backend and try again.')
        }
        const { token } = await response.json()
        if (closed) return
        if (!token) throw new Error('ElevenLabs did not provide a transcription token.')
        const { CommitStrategy, RealtimeEvents, Scribe } = await import('@elevenlabs/client')
        if (closed) return

        connection = Scribe.connect({
          token,
          modelId: 'scribe_v2_realtime',
          languageCode: 'en',
          commitStrategy: CommitStrategy.VAD,
          vadSilenceThresholdSecs: 1,
          microphone: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        })
        connection.on(RealtimeEvents.SESSION_STARTED, () => {
          if (!closed) setListening(true)
        })
        connection.on(RealtimeEvents.PARTIAL_TRANSCRIPT, (data) => {
          if (!closed) handlers.current.onInterim?.(data.text || '')
        })
        connection.on(RealtimeEvents.COMMITTED_TRANSCRIPT, (data) => {
          if (!closed && data.text?.trim()) handlers.current.onFinal?.(data.text.trim())
        })
        connection.on(RealtimeEvents.ERROR, () => {
          if (!closed) {
            setListening(false)
            setError('ElevenLabs transcription stopped. Check microphone permission, account credits and the API key, then turn the lecture source off and on to retry.')
            connection?.close()
          }
        })
        connection.on(RealtimeEvents.CLOSE, () => {
          if (!closed) {
            setListening(false)
            setError((current) => current || 'ElevenLabs disconnected. Turn the lecture source off and on to reconnect.')
          }
        })
      } catch (cause) {
        if (!closed) setError(cause instanceof Error ? cause.message : 'Could not start ElevenLabs transcription.')
      }
    }

    start()
    return () => {
      closed = true
      connection?.close()
    }
  }, [enabled, speakerKey])

  return {
    supported: typeof navigator !== 'undefined' && Boolean(navigator.mediaDevices?.getUserMedia),
    listening: enabled && listening,
    error: enabled ? error : '',
  }
}
