import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { sendCoachMessage } from '../data/coach'

const PdfReader = lazy(() => import('./PdfReader'))

const MODES = {
  GUIDE: { label: 'Guide mode', help: 'The coach asks questions and gives hints so you can work it out yourself.' },
  EXPLAIN: { label: 'Explain mode', help: 'You’ve made several honest attempts, so the coach now explains the idea.' },
  LOCKED: { label: 'Hints only', help: 'This looks like assessed coursework, so the coach only gives hints, never the solution.' },
}

export default function CoachPanel({ active, entryKey, point, lecture, messages, onMessages, onToggle, onNavigate, onList, onModule, onBackLecture }) {
  const [appliedEntry, setAppliedEntry] = useState(entryKey)
  const [reference, setReference] = useState({ lecture, page: point.page })
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [markBusy, setMarkBusy] = useState(false)
  const [markError, setMarkError] = useState('')
  const [pdfExpanded, setPdfExpanded] = useState(true)
  const pending = useRef(null)
  const sendLock = useRef(false)
  const markLock = useRef(false)
  const composing = useRef(false)
  const scroll = useRef(null)
  if (appliedEntry !== entryKey) {
    setAppliedEntry(entryKey); setReference({ lecture, page: point.page })
  }
  const onReady = useCallback(() => {}, [])
  useEffect(() => {
    if (scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight
  }, [messages, active, busy])

  const serverLectureId = point.serverLectureId || lecture.serverId
  const last = [...messages].reverse().find(message => message.from === 'coach' && message.mode)
  const mode = MODES[last?.mode] || MODES.GUIDE

  async function send(event) {
    event?.preventDefault()
    if (sendLock.current || !draft.trim()) return
    sendLock.current = true; setBusy(true); setError('')
    const request = pending.current || { pointId: point.id, chatId: point.chatId, moduleId: point.moduleId, lectureId: point.lectureId, messageId: crypto.randomUUID(), text: draft.trim(), page: reference.page, serverLectureId }
    pending.current = request
    try { const next = await sendCoachMessage(request); onMessages(point.chatId, next); pending.current = null; setDraft('') }
    catch (err) { setError(err.message) }
    finally { sendLock.current = false; setBusy(false) }
  }
  async function mark() {
    if (markLock.current) return
    markLock.current = true; setMarkBusy(true); setMarkError('')
    try { await onToggle(point) } catch (err) { setMarkError(`${err.message} Nothing was changed. Please try again.`) }
    finally { markLock.current = false; setMarkBusy(false) }
  }

  return <section className="coach-panel" hidden={!active}>
    <header className="coach-heading">
      <h1>My Coach</h1>
      <p>{point.moduleName} / {point.lectureTitle} · you got lost on page {point.page}</p>
      <div className="coach-context-actions">
        <span className="coach-status">{point.resolved ? '✓ Understood' : 'To review'}</span>
        <button className="module-secondary" disabled={markBusy} onClick={mark}>{markBusy ? 'Saving…' : point.resolved ? 'Reopen' : 'Mark as understood'}</button>
      </div>
      {markError && <div className="module-error" role="alert">{markError}<button onClick={mark}>Try again</button></div>}
      <nav className="coach-back-links" aria-label="Coach navigation">
        <button className="module-secondary" onClick={onList}>← All conversations</button>
        <button className="module-secondary" onClick={() => onNavigate('moments')}>Lost Moments</button>
        <button className="module-secondary" onClick={() => onBackLecture(point)}>Back to the lecture</button>
      </nav>
    </header>
    <div className="coach-grid">
      <section className="coach-resource">
        <button className="module-secondary coach-collapse" aria-expanded={pdfExpanded} onClick={() => setPdfExpanded(value => !value)}>{pdfExpanded ? 'Hide slides' : 'Show slides'}</button>
        <div hidden={!pdfExpanded}>
          <div className="coach-source-heading">
            <h2>{reference.lecture.title}</h2>
            <p>Page {reference.page}{reference.page !== point.page && <> · <button className="link-button" onClick={() => setReference({ lecture, page: point.page })}>back to page {point.page}</button></>}</p>
          </div>
          {active && pdfExpanded && <Suspense fallback={<p role="status">Loading the PDF reader…</p>}><PdfReader key={reference.lecture.lectureId} lecture={reference.lecture} page={reference.page} onPage={page => setReference(previous => ({ ...previous, page }))} onReady={onReady} /></Suspense>}
        </div>
        {point.context?.length > 0 && <details className="coach-subtitles"><summary>What the lecturer was saying</summary>{point.context.map(item => <blockquote key={item.id}>{item.translations?.[point.language] || item.original}{item.translations?.[point.language] && <small lang="en">{item.original}</small>}</blockquote>)}</details>}
      </section>
      <section className="card coach-chat" aria-label="Conversation with your coach">
        <div className="coach-chat-top">
          <h2>Learning coach</h2>
          <span className={`coach-mode mode-${(last?.mode || 'GUIDE').toLowerCase()}`} title={mode.help}>{mode.label}</span>
          <p>{mode.help}</p>
        </div>
        {!serverLectureId && <div className="module-error" role="status">The coach can’t read this PDF yet, so it can’t answer. Open My Modules and choose “Let the coach read it”.<button className="module-secondary" onClick={() => onModule(point.moduleId)}>Go to My Modules</button></div>}
        <div ref={scroll} className="coach-messages" role="log" aria-label="Conversation history">
          {!messages.length && <p className="coach-empty">What didn’t click on page {point.page}? Tell the coach what you think it means, even if you’re unsure. It will guide you with questions and point you to the right slide.</p>}
          {messages.map(message => <article className={`coach-message ${message.from === 'you' ? 'student' : 'assistant'}`} key={message.id}>
            <strong>{message.from === 'you' ? 'You' : 'Coach'}</strong>
            <p>{message.text}</p>
            {message.citations?.length > 0 && <div className="coach-citations">{message.citations.map(c => <button key={c.slide_number} className="citation" onClick={() => { setPdfExpanded(true); setReference({ lecture, page: c.slide_number }) }}>Slide {c.slide_number}{c.title ? ` · ${c.title}` : ''}</button>)}</div>}
            {message.gapClosed && !point.resolved && <div className="coach-win">🎉 You worked it out yourself! <button className="module-button" onClick={mark}>Mark as understood</button></div>}
            {message.provider === 'fake' && <small>Offline demo coach</small>}
          </article>)}
          {busy && <p className="coach-wait" role="status">The coach is reading your slides…</p>}
        </div>
        {error && <div className="module-error" role="alert">{error}<button className="module-secondary" disabled={busy} onClick={send}>Try again</button><button type="button" className="module-secondary" onClick={() => { pending.current = null; setError('') }}>Edit my question</button></div>}
        <form className="coach-composer" onSubmit={send}>
          <label htmlFor="coach-question">Your answer or question</label>
          <textarea id="coach-question" rows="3" value={draft} readOnly={busy || !!error} placeholder="I think it means…" onChange={event => setDraft(event.target.value)} onCompositionStart={() => { composing.current = true }} onCompositionEnd={() => { composing.current = false }} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && !composing.current && event.keyCode !== 229) { event.preventDefault(); send() } }} />
          <div><small>Enter to send · Shift+Enter for a new line</small><button className="module-button" disabled={busy || !draft.trim() || !!error || !serverLectureId}>{busy ? 'Sending…' : 'Send'}</button></div>
        </form>
      </section>
    </div>
  </section>
}
