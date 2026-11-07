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
  return <section className="coach-list"><h1>My Coach</h1><div className="local-label"><span>Local demo</span>Demo coach — AI not connected</div><p className="coach-note">Each Lost Point keeps its own conversation. Messages are saved on this device.</p>{error && <div className="module-error" role="alert">{error}<button className="module-secondary" onClick={onRetry}>Retry loading conversations</button></div>}{!loaded && !error && <p role="status">Loading conversations…</p>}{loaded && Array.from(modules, ([id, name]) => { const points = data.points.filter(item => item.moduleId === id).sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt)); return <section className="card coach-module" key={id}><div className="coach-module-heading"><h2>{name}</h2><button className="module-secondary" onClick={() => onModule(id)}>View module slides</button></div>{!points.length ? <p>No conversations yet. Open a lecture in this module and select I’m lost.</p> : <div>{points.map(point => <article key={point.id}><button className="coach-conversation" disabled={!!opening} onClick={() => open(point)}><span><strong>{point.lectureTitle}</strong><small>Page {point.page} · Created {new Date(point.createdAt).toLocaleString()}</small></span><span className="coach-status">{point.resolved ? '✓ Understood' : 'To review'}</span><span>{opening === point.id ? 'Opening…' : 'Open conversation →'}</span></button>{failure?.id === point.id && <div className="module-error" role="alert">{failure.message}<button className="module-secondary" onClick={() => open(point)}>Retry conversation</button><button className="module-secondary" onClick={() => onModule(id)}>View module slides</button></div>}</article>)}</div>}</section> })}</section>
}
