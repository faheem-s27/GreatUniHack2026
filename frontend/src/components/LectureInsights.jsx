import { useEffect, useState } from 'react'
import { listInsightLectures, loadLectureInsights } from '../data/insights'
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
  return <figure className="li-chart" aria-label="Lost Points by slide"><div className="li-tooltip" role="status">{active ? `Slide ${active.number}${active.title ? ` · ${active.title}` : ''}: ${active.count === null ? 'hidden (fewer than 5 students)' : `${active.count} ${active.count === 1 ? 'student' : 'students'} lost`}` : 'Point at a bar to see the slide and how many students got lost there.'}</div><div className="li-chart-layout"><span className="li-y-title">Students lost</span><div className="li-y-ticks" aria-hidden="true">{ticks.map(tick => <span key={tick} style={{ bottom: `${tick / ceiling * 100}%` }}>{tick}</span>)}</div><div className="li-scroll" tabIndex={0} role="region" aria-label="Scrollable slide chart"><div className="li-plot" style={{ minWidth: Math.max(260, slides.length * 54) }}><div className="li-grid" aria-hidden="true">{ticks.map(tick => <div key={tick} style={{ bottom: `${tick / ceiling * 100}%` }}/>)}</div><div className="li-bars">{slides.map(slide => {
    const hidden = slide.count === null
    const maximum = !hidden && slide.count === highest
    return <div className="li-column" key={slide.number}><button type="button" className={`li-bar-target ${selected === slide.number ? 'selected' : ''}`} aria-label={`Slide ${slide.number}: ${hidden ? 'hidden, fewer than 5 students' : `${slide.count} students lost`}`} aria-pressed={selected === slide.number} onMouseEnter={() => setHovered(slide.number)} onMouseLeave={() => setHovered(null)} onFocus={() => setHovered(slide.number)} onBlur={() => setHovered(null)} onClick={() => setSelected(slide.number)}><span className={`li-bar ${maximum ? 'maximum' : ''} ${hidden ? 'hidden-count' : ''}`} style={hidden ? undefined : { height: `${slide.count / ceiling * 100}%` }} aria-hidden="true">{hidden ? 'Hidden' : ''}</span></button><span className="li-slide-label">{slide.number}</span></div>
  })}</div></div></div></div><figcaption>Slide number</figcaption></figure>
}

export default function LectureInsights() {
  const [lectures, setLectures] = useState([])
  const [selected, setSelected] = useState('')
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let cancelled = false
    listInsightLectures().then(items => { if (!cancelled) { setLectures(items); setSelected(current => current || items[0]?.id || '') } }).catch(() => {})
    return () => { cancelled = true }
  }, [])
  useEffect(() => {
    let cancelled = false
    loadLectureInsights(selected).then(value => { if (!cancelled) { setData(value); setError('') } }).catch(err => { if (!cancelled) setError(`Lecture insights could not be loaded. ${err.message}`) })
    return () => { cancelled = true }
  }, [selected, attempt])
  const worst = data?.slides?.find(slide => slide.number === data.mostLost)
  return <section className="lecture-insights"><h1>Lecture Insights</h1>
    <p className="li-intro">See which slides lost the room, so you can recap them next lecture. Counts are anonymous and a slide only shows once 5 or more students mark it.</p>
    {lectures.length > 0 && <div className="li-picker"><label htmlFor="insights-lecture">Lecture</label><select id="insights-lecture" value={selected} onChange={event => setSelected(event.target.value)}>{lectures.map(item => <option key={item.id} value={item.id}>{item.moduleName} · {item.title}</option>)}</select><button className="module-secondary" onClick={() => setAttempt(value => value + 1)}>Refresh</button></div>}
    {error ? <div className="module-error" role="alert">{error}<button className="module-secondary" onClick={() => { setError(''); setAttempt(value => value + 1) }}>Try again</button></div> : !data ? <p role="status">Loading lecture insights…</p> : <>
      <div className="li-lecture"><h2>{data.title}</h2><p>{data.totalPages} slides</p><span className="local-label"><span>{data.source}</span>{data.source === 'Sample data' ? 'Upload a lecture in My Modules to see real data.' : 'Updates as students press “I’m lost”.'}</span></div>
      {worst && <p className="li-callout">Slide {worst.number}{worst.title ? ` (${worst.title})` : ''} lost the most students: {worst.count}. Consider a short recap at the start of the next lecture.</p>}
      <section className="card li-card" aria-label="Students lost per slide">{!data.slides?.length ? <p>This lecture has no slides yet.</p> : <><LostPointsChart slides={data.slides} />{data.slides.every(slide => !slide.count) && <p>No slide has reached 5 students yet.</p>}</>}<p className="li-note">Each bar counts distinct students who pressed “I’m lost” on that slide. Students who later mark it as understood still count, so you can see where the room struggled.</p></section>
    </>}
  </section>
}
