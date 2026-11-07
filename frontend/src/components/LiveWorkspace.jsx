import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { findLecture, loadLectureData, saveLostPoint, updatePoint } from '../data/lecture'
import { checkLecture, connectLecture } from '../data/modules'
import CoachList from './CoachList'
import CoachPanel from './CoachPanel'
import LiveCaptions from './LiveCaptions'
import LostMoments from './LostMoments'
import './Coach.css'
import './LiveWorkspace.css'

const PdfReader = lazy(() => import('./PdfReader'))

// Turn the latest caption lines on this page into the context saved with a Lost Point.
function captionContext(feed, page) {
  const lines = feed.captions.filter(item => !item.slide || item.slide === page).slice(-3)
  return lines.map(item => ({
    id: `caption-${item.id}`,
    time: new Date().toISOString(),
    page: item.slide || page,
    original: item.original,
    translations: item.translations?.[feed.lang]?.text ? { [feed.lang]: item.translations[feed.lang].text } : {},
  }))
}

function CoachReadiness({ lecture, onConnected }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  if (lecture.serverId) {
    return <span className="lp-ready" title="The coach has read this PDF and can cite its slides.">✓ Coach can read these slides</span>
  }
  async function connect() {
    setBusy(true); setError('')
    try {
      const updated = await connectLecture(lecture.lectureId)
      if (updated?.serverId) onConnected(updated.serverId)
      else setError(updated?.serverError || 'The server could not read this PDF.')
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  return <span className="lp-not-ready">
    The coach can’t read this PDF yet.
    <button className="module-secondary" disabled={busy} onClick={connect}>{busy ? 'Sending…' : 'Let the coach read it'}</button>
    {error && <small role="alert">{error}</small>}
  </span>
}

export default function LiveWorkspace({ lecture, view, onNavigate, onOpenLecture, coachActive, momentScope, onModule, onCoachChange, onCountChange, onLectureUpdate }) {
  const [data, setData] = useState({ points: [], chats: {}, modules: [], lectures: [] })
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [readError, setReadError] = useState('')
  const [pages, setPages] = useState({})
  const [pageCounts, setPageCounts] = useState({})
  const [point, setPoint] = useState(null)
  const [saving, setSaving] = useState(false)
  const [coachEntry, setCoachEntry] = useState(0)
  const [pendingPoint, setPendingPoint] = useState(null)
  const captionFeed = useRef({ captions: [], lang: 'en' })
  const pointLock = useRef(false)
  const currentId = lecture?.lectureId
  const viewingPage = pages[currentId] || 1

  const reload = useCallback(async () => {
    try { setData(await loadLectureData()); setLoaded(true); setReadError('') } catch (err) { setReadError(err.message) }
  }, [])
  useEffect(() => {
    let cancelled = false
    loadLectureData().then(value => { if (!cancelled) { setData(value); setLoaded(true); setReadError('') } }).catch(err => { if (!cancelled) setReadError(err.message) })
    return () => { cancelled = true }
  }, [view])
  useEffect(() => { onCountChange(data.points.filter(item => !item.resolved).length) }, [data.points, onCountChange])
  // The server may have been reset since this PDF was sent: check, so the UI never claims the coach can read it when it can't.
  const lectureServerId = lecture?.serverId
  useEffect(() => {
    if (!currentId || !lectureServerId) return
    let cancelled = false
    checkLecture(currentId).then(item => { if (!cancelled && item && !item.serverId) onLectureUpdate({ ...lecture, serverId: null }) }).catch(() => {})
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only when a different lecture or server copy is opened
  }, [currentId, lectureServerId])

  const ready = useCallback(count => setPageCounts(previous => ({ ...previous, [currentId]: count })), [currentId])
  const keepCaptions = useCallback(feed => { captionFeed.current = feed }, [])
  const changePage = useCallback(value => {
    setPages(previous => ({ ...previous, [currentId]: Math.max(1, Math.min(value, pageCounts[currentId] || value)) }))
  }, [currentId, pageCounts])

  async function lost() {
    if (pointLock.current || !loaded || !pageCounts[currentId]) return
    pointLock.current = true; setSaving(true); setError('')
    const draft = (pendingPoint?.lectureId === currentId ? pendingPoint : null) || {
      id: crypto.randomUUID(), chatId: crypto.randomUUID(), moduleId: lecture.moduleId, lectureId: currentId,
      serverLectureId: lecture.serverId || null, moduleName: lecture.moduleName, lectureTitle: lecture.title,
      fileName: lecture.fileName, page: viewingPage, createdAt: new Date().toISOString(),
      context: captionContext(captionFeed.current, viewingPage), language: captionFeed.current.lang, resolved: false,
    }
    setPendingPoint(draft)
    try {
      const saved = await saveLostPoint(draft)
      setData(previous => ({ ...previous, points: [saved, ...previous.points.filter(item => item.id !== saved.id)] }))
      setPoint(saved); setCoachEntry(value => value + 1); setPendingPoint(null); onCoachChange(true); onNavigate('coach')
    } catch (err) { setError(`${err.message} Your Lost Point wasn’t saved. Try again: the same page and captions will be kept.`) }
    finally { setSaving(false); pointLock.current = false }
  }
  async function explore(item) {
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
  const pageTotal = pageCounts[currentId]

  return <div className="lp-workspace">
    {readError && view !== 'moments' && <div className="module-error" role="alert">{readError}<button onClick={reload}>Try again</button></div>}
    {error && view !== 'moments' && <div role="alert" className="module-error">{error}</div>}
    {live && <>
      <div className="lp-heading">
        <p>{lecture.moduleName} / {lecture.fileName}</p>
        <h1>{lecture.title}</h1>
        <CoachReadiness lecture={lecture} onConnected={serverId => onLectureUpdate({ ...lecture, serverId })} />
      </div>
      <div className="lp-live-layout">
        <Suspense fallback={<p role="status">Loading the PDF reader…</p>}>
          <PdfReader key={currentId} lecture={lecture} page={viewingPage} onPage={changePage} onReady={ready} />
        </Suspense>
        <aside className="lp-side">
          <section className="card lp-lost-card">
            <span className="section-kicker">A LITTLE LOST?</span>
            <h2>It happens to everyone.</h2>
            <p>Save page {viewingPage}{pageTotal ? ` of ${pageTotal}` : ''} and what the lecturer was saying. Your coach will help you work through it, no raised hand needed.</p>
            <button className="lp-lost" disabled={saving || !loaded || !pageTotal} onClick={lost}>
              {saving ? 'Saving…' : pendingPoint?.lectureId === currentId ? 'Try again: I’m lost' : '⌁  I’m lost'}
            </button>
            <small className="lp-private">♡ Only you see your Lost Points. Your lecturer sees anonymous counts once 5 or more students mark the same slide.</small>
          </section>
          <LiveCaptions lectureId={lecture.serverId || currentId} slideNumber={viewingPage} onLecturerSlide={changePage} onCaptions={keepCaptions} />
        </aside>
      </div>
    </>}
    {view === 'coach' && !coachActive && <CoachList data={data} loaded={loaded} error={readError} onRetry={reload} onExplore={explore} onModule={onModule} />}
    {coachPoint && lecture && coachPoint.lectureId === currentId && <CoachPanel key={coachPoint.chatId} active={!!coaching} entryKey={coachEntry} point={coachPoint} lecture={lecture} messages={data.chats[coachPoint.chatId] || []} onMessages={(id, messages) => setData(previous => ({ ...previous, chats: { ...previous.chats, [id]: messages } }))} onToggle={toggle} onNavigate={onNavigate} onList={() => onCoachChange(false)} onBackLecture={item => { setPages(previous => ({ ...previous, [item.lectureId]: item.page })); onNavigate('lecture') }} onLectureUpdate={onLectureUpdate} />}
    <LostMoments active={view === 'moments'} scope={momentScope} data={data} loaded={loaded} loadError={readError} onReload={reload} onExplore={explore} onToggle={toggle} onNavigate={onNavigate} />
  </div>
}
