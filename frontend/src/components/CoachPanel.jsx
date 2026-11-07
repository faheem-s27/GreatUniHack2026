import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { findLecture } from '../data/lecture'
import { sendCoachMessage } from '../data/coach'
const PdfReader = lazy(() => import('./PdfReader'))
export default function CoachPanel({ active, entryKey, point, lecture, messages, onMessages, onToggle, onNavigate, onList, onModule, onBackLecture, onViewedPage }) {
  const [appliedEntry, setAppliedEntry] = useState(entryKey)
  const [reference, setReference] = useState({ lecture, page: point.page })
  const [pageText, setPageText] = useState(null)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [referenceError, setReferenceError] = useState('')
  const [markBusy, setMarkBusy] = useState(false)
  const [markError, setMarkError] = useState('')
  const [latestNotice, setLatestNotice] = useState(false)
  const [pdfExpanded, setPdfExpanded] = useState(true)
  const pending = useRef(null)
  const sendLock = useRef(false)
  const markLock = useRef(false)
  const composing = useRef(false)
  const scroll = useRef(null)
  const follow = useRef(true)
  if (appliedEntry !== entryKey) {
    setAppliedEntry(entryKey); setReference({ lecture, page: point.page }); setPageText(null); setReferenceError('')
  }
  const onReady = useCallback(() => {}, [])
  const onText = useCallback(value => setPageText(value), [])
  useEffect(() => { if (active) onViewedPage({ pointId: point.id, lectureId: reference.lecture.lectureId, page: reference.page }) }, [reference, point.id, onViewedPage, active])
  useEffect(() => {
    const target = scroll.current
    if (follow.current && target) target.scrollTop = target.scrollHeight
    else if (messages.length) queueMicrotask(() => setLatestNotice(true))
  }, [messages, active])
  function latest() { follow.current = true; setLatestNotice(false); if (scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight }
  async function send(event) {
    event?.preventDefault()
    if (sendLock.current || !draft.trim()) return
    sendLock.current = true; setBusy(true); setError('')
    const context = pageText?.lectureId === reference.lecture.lectureId && pageText?.page === reference.page ? pageText.text : ''
    const request = pending.current || { pointId: point.id, chatId: point.chatId, moduleId: point.moduleId, lectureId: point.lectureId, messageId: crypto.randomUUID(), text: draft.trim(), page: reference.page, pageText: context, resourceTitle: reference.lecture.title, resourceLectureId: reference.lecture.lectureId }
    pending.current = request
    try { const next = await sendCoachMessage(request); onMessages(point.chatId, next); pending.current = null; setDraft('') }
    catch (err) { setError(`${err.message} Sending was not confirmed. Retry keeps your original question and cannot duplicate it.`) }
    finally { sendLock.current = false; setBusy(false) }
  }
  async function mark() {
    if (markLock.current) return
    markLock.current = true; setMarkBusy(true); setMarkError('')
    try { await onToggle(point) } catch (err) { setMarkError(`${err.message} Your previous status is unchanged. Please retry.`) }
    finally { markLock.current = false; setMarkBusy(false) }
  }
  async function cite(source) {
    setReferenceError('')
    try {
      if (source.moduleId !== point.moduleId || !Number.isInteger(source.page) || source.page < 1) throw new Error('This source is not a valid reference for this module.')
      const resource = source.lectureId === lecture.lectureId ? lecture : await findLecture(point.moduleId, source.lectureId)
      setPageText(null); setReference({ lecture: resource, page: source.page }); setPdfExpanded(true)
    } catch (err) { setReferenceError(`${err.message} The PDF was not changed.`) }
  }
  return <section className="coach-panel" hidden={!active}>
    <header className="coach-heading"><h1>My Coach</h1><p>{point.moduleName} / {point.lectureTitle} · Lost Point page {point.page}</p><div className="coach-context-actions"><span className="coach-status">{point.resolved ? '✓ Understood' : 'To review'}</span><button className="module-secondary" disabled={markBusy} onClick={mark}>{markBusy ? 'Saving…' : point.resolved ? 'Reopen' : 'Mark Understood'}</button><small>Student self-confirmed</small></div>{markError && <div className="module-error" role="alert">{markError}<button onClick={mark}>Retry status update</button></div>}<nav className="coach-back-links" aria-label="Coach navigation"><button className="module-secondary" onClick={onList}>All module conversations</button><button className="module-secondary" onClick={() => onNavigate('moments')}>Back to Lost Moments</button><button className="module-secondary" onClick={() => onBackLecture(point)}>Back to lecture</button></nav></header>
    <div className="coach-grid"><section className="coach-resource"><button className="module-secondary coach-collapse" aria-expanded={pdfExpanded} onClick={() => setPdfExpanded(value => !value)}>{pdfExpanded ? 'Collapse PDF' : 'Show PDF'}</button><div hidden={!pdfExpanded}><div className="coach-source-heading"><h2>{reference.lecture.title}</h2><p>Viewing page {reference.page} · Original Lost Point page {point.page}</p><small>{pageText?.lectureId === reference.lecture.lectureId && pageText?.page === reference.page && pageText.text ? 'Local page text available for demo prompts' : 'PDF text is loading or unavailable; no page-grounded answer is claimed.'}</small><button className="module-secondary" onClick={() => { setPageText(null); setReference({ lecture, page: point.page }) }}>Return to original Lost Point page</button></div>{referenceError && <div className="module-error" role="alert">{referenceError}</div>}{active && pdfExpanded && <Suspense fallback={<p role="status">Loading PDF reader…</p>}><PdfReader key={reference.lecture.lectureId} lecture={reference.lecture} page={reference.page} onPage={page => { setPageText(null); setReference(previous => ({ ...previous, page })) }} onReady={onReady} onPageText={onText}/></Suspense>}<button className="module-secondary" onClick={() => onModule(point.moduleId)}>Check slides in My Modules</button></div><details className="coach-subtitles"><summary>Saved Lost Point context</summary><p>Created {new Date(point.createdAt).toLocaleString()}</p>{point.captionTime && <p>Selected historical subtitle: {new Date(point.captionTime).toLocaleString()}</p>}{point.context?.length ? point.context.map(item => <blockquote key={item.id}>{item.translations?.[point.language] || item.original}<small>{item.original} · Recorded student page {item.page} · {new Date(item.time).toLocaleTimeString()}</small></blockquote>) : <p>No subtitle context was captured for this Lost Point.</p>}<small>Conversation ID (chatId): <code>{point.chatId}</code></small></details></section>
    <section className="card coach-chat" aria-label="Learning Coach conversation"><div className="coach-chat-top"><h2>Learning Coach</h2><span className="local-label"><span>Demo</span>Demo coach — AI not connected</span><p>No server mode available. Guide, Explain and Locked states require the teaching service; this demo does not unlock modes or assess homework.</p></div><div ref={scroll} className="coach-messages" role="log" aria-label="Conversation history" onScroll={() => { const node = scroll.current; follow.current = node.scrollHeight - node.scrollTop - node.clientHeight < 60; if (follow.current) setLatestNotice(false) }}>{!messages.length && <p className="coach-empty">What would you like to understand about page {point.page}? Demo prompts can use locally extracted PDF text, but cannot interpret the lecture.</p>}{messages.map(message => <article className={`coach-message ${message.from === 'you' ? 'student' : 'assistant'}`} key={message.id}><strong>{message.from === 'you' ? 'You' : 'Learning Coach · Demo'}</strong><p>{message.text}</p>{message.reference ? <div className="coach-reference"><small>Local PDF excerpt — not an AI citation</small><button onClick={() => cite(message.reference)}>{message.reference.title} · Page {message.reference.page}</button><blockquote>{message.reference.excerpt}</blockquote></div> : message.from !== 'you' && <small>No verified source reference was provided.</small>}</article>)}</div>{latestNotice && <button className="module-secondary coach-latest" onClick={latest}>View latest messages</button>}{busy && <p className="coach-wait" role="status">Saving question and preparing a local demo prompt…</p>}{error && <div className="module-error" role="alert">{error}<button className="module-secondary" disabled={busy} onClick={send}>Retry send</button></div>}<form className="coach-composer" onSubmit={send}><label htmlFor="coach-question">Your question</label><textarea id="coach-question" rows="3" value={draft} readOnly={busy || !!error} onChange={event => setDraft(event.target.value)} onCompositionStart={() => { composing.current = true }} onCompositionEnd={() => { composing.current = false }} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && !composing.current && event.keyCode !== 229) { event.preventDefault(); send() } }}/><div><small>Enter to send · Shift+Enter for a new line</small><button className="module-button" disabled={busy || !draft.trim() || !!error}>Send</button></div>{error && <button type="button" className="module-secondary" onClick={() => { pending.current = null; setError('') }}>Edit question</button>}</form></section></div>
  </section>
}
