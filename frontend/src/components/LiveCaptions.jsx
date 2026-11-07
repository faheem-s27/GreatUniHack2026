import { useEffect, useRef, useState } from 'react'
import { useLiveCaptions } from '../hooks/useLiveCaptions'
import { useSpeechRecognition } from '../hooks/useSpeechRecognition'

const LANG_KEY = 'lostpoint-caption-lang'
const SPEAKER_KEY = import.meta.env.VITE_SPEAKER_KEY || ''
const LECTURE_SPEECH_LANG = 'en-GB' // what the lecturer speaks
const VISIBLE_LINES = 6

function readStoredLang() {
  try {
    return localStorage.getItem(LANG_KEY) || 'en'
  } catch {
    return 'en'
  }
}

function CaptionLine({ caption, lang, rtl, showSlide }) {
  const translation = lang === 'en' ? null : caption.translations[lang]
  return (
    <div className="caption-line">
      {showSlide && caption.slide && <span className="caption-slide">SLIDE {caption.slide}</span>}
      {lang === 'en' && <p className="caption-main">{caption.original}</p>}
      {lang !== 'en' && translation?.text && (
        <>
          <p className="caption-main" lang={lang} dir={rtl ? 'rtl' : 'ltr'}>{translation.text}</p>
          <p className="caption-original">{caption.original}</p>
        </>
      )}
      {lang !== 'en' && !translation?.text && (
        <>
          <p className="caption-main">{caption.original}</p>
          <p className="caption-note">{translation?.failed ? 'Translation unavailable for this line' : 'Translating…'}</p>
        </>
      )}
    </div>
  )
}

export default function LiveCaptions({ lectureId, slideNumber, onLecturerSlide }) {
  const [lang, setLang] = useState(readStoredLang)
  const [speakerMode, setSpeakerMode] = useState(false)
  const [testLine, setTestLine] = useState('')
  const feedRef = useRef(null)

  const { status, captions, interim, info, error, sendInterim, sendFinal, sendSlide } = useLiveCaptions({
    lectureId,
    lang,
    speaker: speakerMode,
    speakerKey: SPEAKER_KEY,
    onSlide: onLecturerSlide,
  })

  const speech = useSpeechRecognition({
    enabled: speakerMode && info.isSpeaker,
    lang: LECTURE_SPEECH_LANG,
    onInterim: sendInterim,
    onFinal: (text) => sendFinal(text, slideNumber),
  })

  // When this device is the lecture source, its slide changes pin the captions.
  useEffect(() => {
    if (info.isSpeaker && status === 'live') sendSlide(slideNumber)
  }, [slideNumber, info.isSpeaker, status, sendSlide])

  useEffect(() => {
    const el = feedRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [captions, interim])

  function changeLanguage(event) {
    const next = event.target.value
    setLang(next)
    try {
      localStorage.setItem(LANG_KEY, next)
    } catch {
      // storage unavailable
    }
  }

  function submitTestLine(event) {
    event.preventDefault()
    const text = testLine.trim()
    if (!text) return
    sendFinal(text, slideNumber)
    setTestLine('')
  }

  const languages = info.languages.length ? info.languages : [{ code: lang, name: lang, native: lang, rtl: false }]
  const rtl = Boolean(languages.find((item) => item.code === lang)?.rtl)
  const visible = captions.slice(-VISIBLE_LINES)
  const problem = speech.error || error

  let statusLabel = 'Waiting for lecturer'
  if (status !== 'live') statusLabel = status === 'reconnecting' ? 'Reconnecting…' : 'Connecting…'
  else if (info.speakerActive) statusLabel = 'Lecture live'

  return (
    <section className="card captions-card">
      <div className="card-line">
        <div>
          <span className="section-kicker">FOLLOW ALONG</span>
          <h3>Live captions</h3>
        </div>
        <span className="caption-icon">“ ”</span>
      </div>

      <div className="caption-feed" ref={feedRef} aria-live="polite">
        {visible.length === 0 && !interim && (
          <p className="caption-empty">
            {info.speakerActive
              ? 'Listening… captions will appear as the lecturer speaks.'
              : 'Captions will appear here when a live lecture is connected.'}
          </p>
        )}
        {visible.map((caption, index) => (
          <CaptionLine
            key={caption.id}
            caption={caption}
            lang={lang}
            rtl={rtl}
            showSlide={index === 0 || visible[index - 1].slide !== caption.slide}
          />
        ))}
        {interim && <p className="caption-interim" aria-hidden="true">{interim}</p>}
      </div>

      <div className="caption-foot">
        <label className="caption-lang">
          <span aria-hidden="true">◉</span>
          <span className="sr-only">Caption language</span>
          <select value={lang} onChange={changeLanguage}>
            {languages.map((item) => (
              <option key={item.code} value={item.code}>
                {item.native}
                {item.native !== item.name ? ` · ${item.name}` : ''}
              </option>
            ))}
          </select>
        </label>
        <span>
          {info.mock && lang !== 'en' && <span className="sample-tag">DEMO TRANSLATION</span>}
          {statusLabel}
        </span>
      </div>

      {problem && <p className="caption-problem" role="alert">{problem}</p>}

      <details className="caption-tools">
        <summary>LECTURER / DEMO CONTROLS</summary>
        <label className="caption-check">
          <input type="checkbox" checked={speakerMode} onChange={(event) => setSpeakerMode(event.target.checked)} />
          Use this device as the lecture source
        </label>
        {speakerMode && (
          <>
            <p className="caption-hint">
              {speech.supported
                ? speech.listening
                  ? 'Listening to the microphone…'
                  : 'Starting the microphone…'
                : 'Speech recognition isn’t available in this browser (try Chrome, Edge or Safari). You can still type test lines.'}
            </p>
            <form className="caption-test" onSubmit={submitTestLine}>
              <label className="sr-only" htmlFor="caption-test-line">Test caption line</label>
              <input
                id="caption-test-line"
                value={testLine}
                onChange={(event) => setTestLine(event.target.value)}
                placeholder="Type a line as the lecturer…"
              />
              <button type="submit" disabled={!info.isSpeaker}>Send</button>
            </form>
          </>
        )}
        <p className="caption-hint">
          LostPoint never receives or stores audio, only the text. Your browser’s speech service may process audio to
          transcribe it.
        </p>
      </details>
    </section>
  )
}
