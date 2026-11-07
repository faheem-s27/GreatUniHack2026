import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
const PdfReader = lazy(() => import('./PdfReader'))
import { demoCaption, findLecture, languages, loadLectureData, requestRecording, saveLostPoint, saveSession, updatePoint } from '../data/lecture'
import './LiveWorkspace.css'
import LostMoments from './LostMoments'
import CoachList from './CoachList'
import CoachPanel from './CoachPanel'
import './Coach.css'

export default function LiveWorkspace({ lecture, view, onNavigate, onOpenLecture, onRecordingChange, coachActive, momentScope, onModule, onCoachChange, onCountChange }) {
  const [data, setData] = useState({ sessions: [], points: [], chats: {}, modules: [], lectures: [] })
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [readError, setReadError] = useState('')
  const [pages, setPages] = useState({})
  const [pageCounts, setPageCounts] = useState({})
  const [language, setLanguage] = useState('zh')
  const [demo, setDemo] = useState(false)
  const [consent, setConsent] = useState(false)
  const [status, setStatus] = useState('Stopped')
  const [historyId, setHistoryId] = useState('')
  const [selectedCaption, setSelectedCaption] = useState(null)
  const [point, setPoint] = useState(null)
  const [saving, setSaving] = useState(false)
  const [coachEntry, setCoachEntry] = useState(0)
  const [coachPage, setCoachPage] = useState(null)
  const [pendingPoint, setPendingPoint] = useState(null)
  const session = useRef(null)
  const pageRef = useRef(1)
  const lock = useRef(false)
  const pointLock = useRef(false)
  const queue = useRef(Promise.resolve())
  const currentId = lecture?.lectureId
  const viewingPage = pages[currentId] || 1
  const pdfPage = view === 'coach' && coachActive && point?.lectureId === currentId ? (coachPage?.pointId === point.id && coachPage.lectureId === currentId ? coachPage.page : point.page) : viewingPage
  useEffect(() => { pageRef.current = pdfPage }, [pdfPage])
  const reload = useCallback(async () => {
    try { setData(await loadLectureData()); setLoaded(true); setReadError('') } catch (err) { setReadError(err.message) }
  }, [])
  useEffect(() => {
    let cancelled = false
    loadLectureData().then(value => { if (!cancelled) { setData(value); setLoaded(true) } }).catch(err => { if (!cancelled) setReadError(err.message) })
    return () => { cancelled = true }
  }, [])
  useEffect(() => {
    if (!['moments', 'coach'].includes(view)) return
    let cancelled = false
    loadLectureData().then(value => { if (!cancelled) { setData(value); setLoaded(true); setReadError('') } }).catch(err => { if (!cancelled) setReadError(err.message) })
    return () => { cancelled = true }
  }, [view])
  useEffect(() => { onCountChange(data.points.filter(item => !item.resolved).length) }, [data.points, onCountChange])
  useEffect(() => {
    if (status !== 'Subtitle demo running') return
    const timer = setInterval(() => {
      const active = session.current
      if (!active) return
      const translations = demoCaption(active.captions.length)
      const caption = { id: crypto.randomUUID(), time: new Date().toISOString(), page: pageRef.current, original: translations.en, translations, source: 'preset-demo', pageSource: 'student-view' }
      const next = { ...active, captions: [...active.captions, caption] }
      session.current = next
      queue.current = queue.current.then(async () => {
        await saveSession(next)
        setData(previous => ({ ...previous, sessions: [next, ...previous.sessions.filter(item => item.id !== next.id)] }))
      }).catch(err => { session.current = null; lock.current = false; onRecordingChange(false); setStatus('Disconnected — storage failed'); setError(`${err.message} Demo stopped. Previously saved captions remain available.`) })
    }, 4000)
    const warn = event => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => { clearInterval(timer); window.removeEventListener('beforeunload', warn) }
  }, [status, onRecordingChange])
  const ready = useCallback(count => setPageCounts(previous => ({ ...previous, [currentId]: count })), [currentId])
  const sessions = data.sessions.filter(item => item.lectureId === currentId && item.moduleId === lecture?.moduleId)
  const history = sessions.find(item => item.id === historyId)
  const latest = history?.captions.at(-1)
  const reviewing = selectedCaption && history?.captions.some(item => item.id === selectedCaption.id)
  const caption = reviewing ? selectedCaption : latest
  const isActive = ['Subtitle demo running', 'Starting subtitle demo…', 'Requesting microphone permission…', 'Stopping…'].includes(status)
  function changePage(value) {
    if (view === 'coach' && point) return
    setPages(previous => ({ ...previous, [currentId]: value })); pageRef.current = value
  }
  async function start(isDemo) {
    if (lock.current || !consent || !loaded || !pageCounts[currentId]) return
    lock.current = true; onRecordingChange(true); setError('')
    if (!isDemo) {
      setStatus('Requesting microphone permission…')
      try { await requestRecording() } catch (err) { setError(err.message); setStatus(err.message.includes('denied') ? 'Permission denied' : 'Connection failed') }
      finally { lock.current = false; onRecordingChange(false) }
      return
    }
    setStatus('Starting subtitle demo…')
    const next = { id: crypto.randomUUID(), moduleId: lecture.moduleId, lectureId: currentId, startedAt: new Date().toISOString(), mode: 'subtitle-demo', captions: [] }
    try {
      await saveSession(next); session.current = next; setHistoryId(next.id); setSelectedCaption(null)
      setData(previous => ({ ...previous, sessions: [next, ...previous.sessions] })); setStatus('Subtitle demo running')
    } catch (err) { lock.current = false; onRecordingChange(false); setError(err.message); setStatus('Stopped — save failed') }
  }
  async function stop() {
    if (!session.current) return
    const ended = { ...session.current, endedAt: new Date().toISOString() }
    session.current = null; setStatus('Stopping…')
    try {
      await queue.current; await saveSession(ended)
      setData(previous => ({ ...previous, sessions: [ended, ...previous.sessions.filter(item => item.id !== ended.id)] })); setStatus('Stopped')
    } catch (err) { setError(`${err.message} Session end could not be saved. Captions already saved are retained.`); setStatus('Stopped — save failed') }
    finally { lock.current = false; onRecordingChange(false) }
  }
  async function lost() {
    if (pointLock.current || !loaded || !pageCounts[currentId]) return
    pointLock.current = true; setSaving(true); setError('')
    const chosen = caption && (reviewing || caption.page === viewingPage) ? caption : null
    const context = history?.captions || []
    const index = chosen ? context.findIndex(item => item.id === chosen.id) : -1
    const draft = (pendingPoint?.lectureId === currentId ? pendingPoint : null) || { id: crypto.randomUUID(), chatId: crypto.randomUUID(), moduleId: lecture.moduleId, lectureId: currentId, moduleName: lecture.moduleName, lectureTitle: lecture.title, fileName: lecture.fileName, page: viewingPage, createdAt: new Date().toISOString(), sessionId: history?.id || null, captionId: chosen?.id || null, captionTime: chosen?.time || null, context: index < 0 ? [] : context.slice(Math.max(0, index - 2), index + 1), language, resolved: false }
    setPendingPoint(draft)
    try {
      const saved = await saveLostPoint(draft)
      setData(previous => ({ ...previous, points: [saved, ...previous.points.filter(item => item.id !== saved.id)] }))
      setPoint(saved); setCoachEntry(value => value + 1); setPendingPoint(null); onCoachChange(true); onNavigate('coach')
    } catch (err) { setError(`${err.message} Lost Point was not saved. Retry keeps the original page and subtitle context.`) }
    finally { setSaving(false); pointLock.current = false }
  }
  async function explore(item) {
    if (lock.current && item.lectureId !== currentId) throw new Error('Stop the current recording or subtitle demo before opening another lecture.')
    const target = await findLecture(item.moduleId, item.lectureId)
    onOpenLecture(target); setPoint(item); setCoachEntry(value => value + 1); onCoachChange(true); onNavigate('coach'); setError('')
  }
  async function toggle(item) {
    const next = { ...item, resolved: !item.resolved }
    await updatePoint(next)
    setData(previous => ({ ...previous, points: previous.points.map(value => value.id === next.id ? next : value) }))
  }
  const live = view === 'lecture' && lecture
  const coachPoint = data.points.find(item => item.id === point?.id) || point
  const coaching = view === 'coach' && coachActive && coachPoint && coachPoint.lectureId === currentId && lecture
  return <div className="lp-workspace">
    {status === 'Subtitle demo running' && !live && <div className="lp-session-banner" role="status">Subtitle demo continues · {lecture?.moduleName} / {lecture?.title}<button onClick={stop}>Stop subtitle demo</button><button onClick={() => onNavigate('lecture')}>Return to Live Lecture</button></div>}
    {readError && view !== 'moments' && <div className="module-error" role="alert">{readError}<button onClick={reload}>Retry loading saved records</button></div>}
    {error && view !== 'moments' && <div role="alert" className="module-error">{error}{!loaded && <button onClick={reload}>Retry loading saved sessions</button>}</div>}
    {live && <>
      <div className="lp-heading"><p>{lecture.moduleName} / {lecture.fileName}</p><h1>Live Lecture</h1><span className="local-label"><span>Local demo</span> Saved on this device · No server or AI connection</span></div>
      {live && <section className="lp-control card"><div><label htmlFor="subtitle-language">Native language</label><select id="subtitle-language" value={language} onChange={event => setLanguage(event.target.value)}>{Object.entries(languages).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></div><label className="lp-check"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)}/>I confirm I have permission to transcribe this lecture.</label><div className="lp-record-buttons"><button className="module-secondary" disabled={!consent || isActive || !loaded || !pageCounts[currentId]} onClick={() => start(false)}>Start recording</button><button className="module-secondary" disabled={status !== 'Subtitle demo running'} onClick={stop}>Stop</button><span role="status">{status}</span><button className="lp-lost" disabled={saving || !loaded || !pageCounts[currentId]} onClick={lost}>{saving ? 'Saving Lost Point…' : pendingPoint?.lectureId === currentId ? 'Retry I’m lost' : 'I’m lost'}</button></div><label className="lp-check"><input type="checkbox" checked={demo} disabled={isActive} onChange={event => setDemo(event.target.checked)}/>Enable subtitle demo — preset text, no microphone, no translation service</label>{demo && <button className="module-secondary" disabled={!consent || isActive || !loaded || !pageCounts[currentId]} onClick={() => start(true)}>Start subtitle demo</button>}<p className="lp-note">No speech/translation API is configured. Recording cannot connect. Demo subtitles are fictional and unrelated to this PDF.</p></section>}
      <Suspense fallback={<p role="status">Loading PDF reader…</p>}><PdfReader key={currentId} lecture={lecture} page={viewingPage} onPage={changePage} onReady={ready}/></Suspense>
      {live && <><section className="lp-captions card" aria-labelledby="current-caption"><div className="lp-section-head"><h2 id="current-caption">{reviewing ? 'Selected subtitle' : 'Current subtitle'}</h2><button className="module-secondary" onClick={() => { const current = sessions.find(item => item.id === session.current?.id) || sessions[0]; setHistoryId(current?.id || ''); setSelectedCaption(null); if (current?.captions.length) changePage(current.captions.at(-1).page) }}>Back to live</button></div><p className="lp-note">Viewing page {viewingPage} · Caption recorded on student page {caption?.page || '—'}. No teacher page synchronization.</p>{caption ? <><p className="lp-translation">{caption.translations[language]}</p><p lang="en">Original: {caption.original}</p><small>{new Date(caption.time).toLocaleTimeString()} · Preset demo subtitle</small></> : <p>No subtitles yet. Enable and start subtitle demo to try this workflow.</p>}</section><section className="lp-history card"><h2>Subtitle History</h2><label htmlFor="subtitle-session">Saved session</label><select id="subtitle-session" value={history?.id || ''} onChange={event => { setHistoryId(event.target.value); setSelectedCaption(null) }}><option value="">Select a session</option>{sessions.map(item => <option key={item.id} value={item.id}>{new Date(item.startedAt).toLocaleString()} · {item.id.slice(0, 8)} · {item.captions.length} captions · Local demo</option>)}</select><p className="lp-note">Saved in this browser only. Recording does not resume after a reload. Page numbers refer to the student’s viewed page at capture time.</p><div className="lp-history-list">{!history?.captions.length && <p>No saved subtitles in this session.</p>}{history?.captions.map(item => <button className={`lp-caption-row ${selectedCaption?.id === item.id ? 'selected' : ''}`} key={item.id} aria-pressed={selectedCaption?.id === item.id} onClick={() => { setSelectedCaption(item); changePage(item.page) }}><small>{new Date(item.time).toLocaleTimeString()} · Recorded student page {item.page}</small><strong>{item.translations[language]}</strong><span lang="en">{item.original}</span></button>)}</div></section></>}

    </>}
    {view === 'coach' && !coachActive && <CoachList data={data} loaded={loaded} error={readError} onRetry={reload} onExplore={explore} onModule={onModule}/>}
    {coachPoint && lecture && coachPoint.lectureId === currentId && <CoachPanel key={coachPoint.chatId} active={!!coaching} entryKey={coachEntry} point={coachPoint} lecture={lecture} messages={data.chats[coachPoint.chatId] || []} onMessages={(id, messages) => setData(previous => ({ ...previous, chats: { ...previous.chats, [id]: messages } }))} onToggle={toggle} onNavigate={onNavigate} onList={() => onCoachChange(false)} onModule={onModule} onViewedPage={setCoachPage} onBackLecture={item => { setPages(previous => ({ ...previous, [item.lectureId]: item.page })); pageRef.current = item.page; onNavigate('lecture') }}/>}
    <LostMoments active={view === 'moments'} scope={momentScope} data={data} loaded={loaded} loadError={readError} onReload={reload} onExplore={explore} onToggle={toggle} onNavigate={onNavigate}/>

  </div>
}
