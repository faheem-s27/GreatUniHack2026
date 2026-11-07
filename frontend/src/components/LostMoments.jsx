import { useEffect, useRef, useState } from 'react'
import { readMomentFilters, rememberMomentFilters } from '../data/lecture'
import './LostMoments.css'

function MomentRow({ point, moduleName, lectureTitle, pdfAvailable, onExplore, onToggle, onModules }) {
  const [busy, setBusy] = useState('')
  const [failure, setFailure] = useState(null)
  const lock = useRef(false)
  async function act(action) {
    if (lock.current) return
    lock.current = true; setBusy(action); setFailure(null)
    try { await (action === 'explore' ? onExplore(point) : onToggle(point)) }
    catch (error) { setFailure({ action, message: error.message }) }
    finally { setBusy(''); lock.current = false }
  }
  return <article className={`lm-row ${point.resolved ? 'understood' : ''}`} aria-label={`${lectureTitle}, page ${point.page}`}>
    <div className="lm-record"><span className="lm-module">{moduleName}</span><h2>{lectureTitle}</h2>{point.fileName && <p className="lm-filename">{point.fileName}</p>}<div className="lm-metadata"><span>Page {point.page}</span><span>Created <time dateTime={point.createdAt}>{new Date(point.createdAt).toLocaleString()}</time></span></div>{point.captionTime && <small>Subtitle captured at {new Date(point.captionTime).toLocaleString()} · Page {point.context?.at(-1)?.page ?? point.page}</small>}</div>
    <span className={`lm-status ${point.resolved ? 'understood' : ''}`}>{point.resolved && <span aria-hidden="true">✓ </span>}{point.resolved ? 'Understood' : 'To review'}</span>
    <div className="lm-actions"><button className="module-secondary" aria-label={`Explore Lost Point: ${lectureTitle}, page ${point.page}`} disabled={!!busy || !pdfAvailable} onClick={() => act('explore')}>{busy === 'explore' ? 'Opening…' : 'Explore'}</button><button className="module-secondary" disabled={!!busy} onClick={() => act('toggle')}>{busy === 'toggle' ? 'Saving…' : point.resolved ? 'Reopen' : 'Mark Understood'}</button></div>
    {!pdfAvailable && <div className="lm-row-message" role="status">The original PDF is unavailable on this device. Check the original lecture slides in My Modules.<button className="module-secondary" onClick={onModules}>Go to My Modules</button></div>}
    {failure && <div className="module-error lm-row-message" role="alert">{failure.message} {failure.action === 'toggle' ? 'Status was not changed.' : 'The original conversation was not opened.'}<div><button className="module-secondary" onClick={() => act(failure.action)}>Retry {failure.action === 'toggle' ? 'status update' : 'Explore'}</button>{failure.action === 'explore' && <button className="module-secondary" onClick={onModules}>Go to My Modules</button>}</div></div>}
  </article>
}

export default function LostMoments({ active, scope, data, loaded, loadError, onReload, onExplore, onToggle, onNavigate }) {
  const [filters, setFilters] = useState(readMomentFilters)
  const [preferenceError, setPreferenceError] = useState('')
  const [appliedScope, setAppliedScope] = useState(scope)
  const scroll = useRef(0)
  const freezeScroll = useRef(false)
  // A course-specific entry is an explicit navigation event, not a global-nav reset.
  if (scope !== appliedScope) {
    setAppliedScope(scope)
    if (scope?.moduleId) setFilters(previous => ({ ...previous, moduleId: scope.moduleId, lectureId: '' }))
  }
  useEffect(() => {
    rememberMomentFilters(filters).catch(() => setPreferenceError('Filters are retained for this visit only; browser preferences could not be saved.'))
  }, [filters])
  useEffect(() => {
    if (!active) return
    const frame = requestAnimationFrame(() => { window.scrollTo(0, scroll.current); freezeScroll.current = false })
    const remember = () => { if (!freezeScroll.current) scroll.current = window.scrollY }
    window.addEventListener('scroll', remember, { passive: true })
    return () => { cancelAnimationFrame(frame); window.removeEventListener('scroll', remember) }
  }, [active])
  const modules = new Map(data.modules.map(item => [item.id, item.name]))
  const lectures = new Map(data.lectures.map(item => [item.id, item]))
  for (const point of data.points) {
    if (!modules.has(point.moduleId)) modules.set(point.moduleId, point.moduleName || 'Unavailable module')
    if (!lectures.has(point.lectureId)) lectures.set(point.lectureId, { id: point.lectureId, moduleId: point.moduleId, title: point.lectureTitle || 'Unavailable lecture', available: false })
  }
  const shown = data.points.filter(item => (!filters.moduleId || item.moduleId === filters.moduleId) && (!filters.lectureId || item.lectureId === filters.lectureId) && (filters.status === 'all' || (filters.status === 'understood' ? item.resolved : !item.resolved))).sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))
  function change(next) { setFilters(previous => ({ ...previous, ...next })); scroll.current = 0 }
  return <section className="lm-page" hidden={!active} aria-labelledby="lost-moments-heading"><h1 id="lost-moments-heading">Lost Moments</h1><div className="local-label"><span>Local demo</span>Saved on this device · Student self-marked status</div>
    <div className="lm-filters"><div><label htmlFor="moment-module">Module</label><select id="moment-module" value={filters.moduleId} onChange={event => change({ moduleId: event.target.value, lectureId: '' })}><option value="">All modules</option>{Array.from(modules, ([id, name]) => <option key={id} value={id}>{name}</option>)}</select></div><div><label htmlFor="moment-lecture">Lecture / PDF</label><select id="moment-lecture" value={filters.lectureId} onChange={event => change({ lectureId: event.target.value })}><option value="">All lectures</option>{Array.from(lectures.values()).filter(item => !filters.moduleId || item.moduleId === filters.moduleId).map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></div><div><label htmlFor="moment-status">Status</label><select id="moment-status" value={filters.status} onChange={event => change({ status: event.target.value })}><option value="all">All</option><option value="review">To review</option><option value="understood">Understood</option></select></div></div>
    {preferenceError && <p role="status">{preferenceError}</p>}
    {loaded && loadError && <div className="module-error" role="alert">{loadError}<button className="module-secondary" onClick={onReload}>Retry loading Lost Moments</button></div>}
    {!loaded ? loadError ? <div className="module-error" role="alert">{loadError}<button className="module-secondary" onClick={onReload}>Retry loading Lost Moments</button></div> : <p role="status">Loading Lost Moments…</p> : !data.points.length ? <div className="card lm-empty"><h2>No lost moments yet</h2><p>Select a lecture and use I’m lost to save a page and its subtitle context.</p><button className="module-button" onClick={() => onNavigate('modules')}>Go to My Modules</button></div> : !shown.length ? <div className="card lm-empty"><h2>No moments match these filters</h2><button className="module-secondary" onClick={() => change({ moduleId: '', lectureId: '', status: 'all' })}>Reset filters</button></div> : <><p className="lm-results" role="status">{shown.length} {shown.length === 1 ? 'moment' : 'moments'} · Newest first</p><div className="lm-list">{shown.map(item => <MomentRow key={item.id} point={item} moduleName={modules.get(item.moduleId)} lectureTitle={lectures.get(item.lectureId)?.title || item.lectureTitle} pdfAvailable={!!lectures.get(item.lectureId)?.available} onExplore={async point => { scroll.current = window.scrollY; freezeScroll.current = true; try { await onExplore(point) } catch (error) { freezeScroll.current = false; throw error } }} onToggle={onToggle} onModules={() => onNavigate('modules')}/>)}</div></>}
  </section>
}
