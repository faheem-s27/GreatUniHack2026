import { useEffect, useState } from 'react'
import { loadLectureInsights } from '../data/insights'
import './LectureInsights.css'

function LostPointsChart({ slides }) {
  const [selected, setSelected] = useState(null)
  const [hovered, setHovered] = useState(null)
  const counts = slides.filter(slide => Number.isInteger(slide.count) && slide.count >= 0).map(slide => slide.count)
  const highest = counts.length ? Math.max(...counts) : null
  const step = Math.max(1, Math.ceil((highest || 1) / 5))
  const ceiling = Math.max(step, Math.ceil((highest || 1) / step) * step)
  const ticks = Array.from({ length: ceiling / step + 1 }, (_, index) => index * step)
  const active = slides.find(slide => slide.number === (hovered ?? selected))
  return <figure className="li-chart" aria-label="Lost Points by slide"><div className="li-tooltip" role="status">{active ? `Slide ${active.number}: ${active.count === null ? 'Hidden — not reported by the data source' : `${active.count} lost points`}` : 'Hover, focus or click a bar to view its slide and count.'}</div><div className="li-chart-layout"><span className="li-y-title">Number of lost points</span><div className="li-y-ticks" aria-hidden="true">{ticks.map(tick => <span key={tick} style={{ bottom: `${tick / ceiling * 100}%` }}>{tick}</span>)}</div><div className="li-scroll" tabIndex={0} role="region" aria-label="Scrollable slide chart"><div className="li-plot" style={{ minWidth: Math.max(260, slides.length * 54) }}><div className="li-grid" aria-hidden="true">{ticks.map(tick => <div key={tick} style={{ bottom: `${tick / ceiling * 100}%` }}/>)}</div><div className="li-bars">{slides.map(slide => {
    const hidden = slide.count === null
    const maximum = !hidden && slide.count === highest
    return <div className="li-column" key={slide.number}><button type="button" className={`li-bar-target ${selected === slide.number ? 'selected' : ''}`} aria-label={`Slide ${slide.number}: ${hidden ? 'Hidden count' : `${slide.count} lost points`}`} aria-pressed={selected === slide.number} onMouseEnter={() => setHovered(slide.number)} onMouseLeave={() => setHovered(null)} onFocus={() => setHovered(slide.number)} onBlur={() => setHovered(null)} onClick={() => setSelected(slide.number)}><span className={`li-bar ${maximum ? 'maximum' : ''} ${hidden ? 'hidden-count' : ''}`} style={hidden ? undefined : { height: `${slide.count / ceiling * 100}%` }} aria-hidden="true">{hidden ? 'Hidden' : ''}</span></button><span className="li-slide-label">{slide.number}</span></div>
  })}</div></div></div></div><figcaption>Slide number</figcaption></figure>
}

export default function LectureInsights() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let cancelled = false
    loadLectureInsights().then(value => { if (!cancelled) { setData(value); setError('') } }).catch(() => { if (!cancelled) setError('Lecture insights could not be loaded. Please retry.') })
    return () => { cancelled = true }
  }, [attempt])
  return <section className="lecture-insights"><h1>Lecture Insights</h1>{error ? <div className="module-error" role="alert">{error}<button className="module-secondary" onClick={() => { setError(''); setAttempt(value => value + 1) }}>Retry insights</button></div> : !data ? <p role="status">Loading lecture insights…</p> : <><div className="li-lecture"><h2>{data.title}</h2><p>{data.totalPages == null ? 'Total pages unavailable' : `${data.totalPages} slides · Existing sample lecture`}</p><span className="local-label"><span>{data.source}</span>Illustrative counts for this lecture only.</span></div><section className="card li-card" aria-label="Lecture Lost Points chart">{!data.slides?.length ? <p>No data available for this lecture.</p> : <><LostPointsChart slides={data.slides}/>{data.slides.every(slide => slide.count === 0) && <p>No lost points recorded for this lecture.</p>}</>}<p className="li-note">Counts represent cumulative Lost Points, not student numbers or percentages. Marking Understood does not subtract a mark.</p></section></>}</section>
}
