import { useRef, useState } from 'react'
export default function CoachList({ data, loaded, error, onRetry, onExplore, onModule }) {
  const [opening, setOpening] = useState(null)
  const [failure, setFailure] = useState(null)
  const lock = useRef(false)
  const modules = new Map(data.modules.map(item => [item.id, item.name]))
  for (const point of data.points) if (!modules.has(point.moduleId)) modules.set(point.moduleId, point.moduleName || 'Unavailable module')
  async function open(point) {
    if (lock.current) return
    lock.current = true; setOpening(point.id); setFailure(null)
    try { await onExplore(point) } catch (err) { setFailure({ id: point.id, message: err.message }) }
    finally { lock.current = false; setOpening(null) }
  }
  return <section className="coach-list"><h1>My Coach</h1><p className="coach-note">Every Lost Point has its own conversation with your coach, grouped by module. Pick one to carry on where you left off.</p>{error && <div className="module-error" role="alert">{error}<button className="module-secondary" onClick={onRetry}>Try again</button></div>}{!loaded && !error && <p role="status">Loading conversations…</p>}{loaded && Array.from(modules, ([id, name]) => { const points = data.points.filter(item => item.moduleId === id).sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt)); return <section className="card coach-module" key={id}><div className="coach-module-heading"><h2>{name}</h2><button className="module-secondary" onClick={() => onModule(id)}>Module slides</button></div>{!points.length ? <p>No conversations yet. Open a lecture in this module and press “I’m lost” on a page you don’t follow.</p> : <div>{points.map(point => <article key={point.id}><button className="coach-conversation" disabled={!!opening} onClick={() => open(point)}><span><strong>{point.lectureTitle}</strong><small>Page {point.page} · {new Date(point.createdAt).toLocaleString()}</small></span><span className="coach-status">{point.resolved ? '✓ Understood' : 'To review'}</span><span>{opening === point.id ? 'Opening…' : 'Continue →'}</span></button>{failure?.id === point.id && <div className="module-error" role="alert">{failure.message}<button className="module-secondary" onClick={() => open(point)}>Try again</button><button className="module-secondary" onClick={() => onModule(id)}>Module slides</button></div>}</article>)}</div>}</section> })}</section>
}
