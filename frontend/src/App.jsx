import { useEffect, useState } from 'react'
import './App.css'
import LostButton from './LostButton.jsx'
import { fetchHeatmap, screenshotUrl, useLostMoments } from './lostMoments.js'

const LECTURE_ID = 'calc-w3'

const slides = [
  { number: 1, title: 'The big picture', topic: 'Functions of several variables', body: 'What happens when an output depends on more than one input?' },
  { number: 2, title: 'Meet partial derivatives', topic: 'Partial derivatives', body: 'A partial derivative describes how a function changes as one variable changes, while the others stay constant.' },
  { number: 3, title: 'A closer look', topic: 'Holding variables constant', body: 'To find the partial derivative with respect to x, treat y as a constant.' },
]
const initialMessages = [{ from: 'coach', text: 'Let’s work through this together. What do you think it means to hold one variable constant?' }]

function App() {
  const [view, setView] = useState('lecture')
  const [slideIndex, setSlideIndex] = useState(1)
  const { moments, online, markLost, attachScreenshot, toggleResolved } = useLostMoments(LECTURE_ID)
  const [lectureStartedAt] = useState(() => Date.now())
  const [heatmap, setHeatmap] = useState(null)
  const [messages, setMessages] = useState(initialMessages)
  const [input, setInput] = useState('')
  const slide = slides[slideIndex]

  useEffect(() => {
    if (view !== 'insights') return
    let cancelled = false
    fetchHeatmap(LECTURE_ID).then((data) => { if (!cancelled) setHeatmap(data) }).catch(() => { if (!cancelled) setHeatmap(null) })
    return () => { cancelled = true }
  }, [view])

  function sendMessage(event) {
    event.preventDefault()
    if (!input.trim()) return
    setMessages([...messages, { from: 'you', text: input.trim() }, { from: 'coach', text: `Good start. Look back at slide ${slide.number}: what changes, and what stays the same? Try explaining it in your own words.` }])
    setInput('')
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#home" onClick={() => setView('lecture')}><span className="brand-mark">✳</span><span>lost<span className="brand-light">point</span><small>LEARNING, RECONNECTED</small></span></a>
        <div className="nav-label">YOUR WORKSPACE</div>
        <nav aria-label="Main navigation">
          <button className={view === 'lecture' ? 'nav active' : 'nav'} onClick={() => setView('lecture')}><span>◉</span> Live lecture</button>
          <button className={view === 'moments' ? 'nav active' : 'nav'} onClick={() => setView('moments')}><span>⌁</span> Lost moments <b>{moments.filter((m) => !m.resolved).length}</b></button>
          <button className={view === 'coach' ? 'nav active' : 'nav'} onClick={() => setView('coach')}><span>✧</span> My coach</button>
          <div className="nav-label lecturer-label">FOR LECTURERS</div>
          <button className={view === 'insights' ? 'nav active' : 'nav'} onClick={() => setView('insights')}><span>▦</span> Lecture insights</button>
        </nav>
        <div className="sidebar-bottom"><div className="avatar">S</div><div><strong>Student workspace</strong><small>Demo account</small></div><span>⌄</span></div>
      </aside>

      <main className="main">
        <header className="topbar"><div><span className="breadcrumb">Workspace</span><span className="slash">/</span><strong>{({ lecture: 'Live lecture', moments: 'Lost moments', coach: 'My coach', insights: 'Lecture insights' })[view]}</strong></div><span className="demo-badge"><i /> Demo workspace</span></header>
        <div className="content">
          {view === 'lecture' && <>
            <div className="page-heading"><div><div className="eyebrow"><span className="live-dot" /> YOUR LEARNING SPACE</div><h1>Stay curious. <em>We’ve got you.</em></h1><p>Every question is a good place to start.</p></div><span className="date-pill">✦ &nbsp; Your lecture companion</span></div>
            <div className="demo-notice">✧ &nbsp; You’re exploring a demo lecture. {online ? 'Your lost moments are saved to your account.' : 'Offline: lost moments are saved on this device and will sync later.'}</div>
            <div className="lecture-layout"><section className="card lecture-card"><div className="card-top"><div><div className="section-kicker">CURRENT LECTURE <span className="sample-tag">SAMPLE</span></div><h2>Introduction to Calculus</h2><p>Week 03 · Multivariable functions</p></div><div className="subject-icon">∑</div></div>
              <div className="slide"><div className="slide-top"><span>CALCULUS · WEEK 03</span><span>{String(slide.number).padStart(2, '0')} / 03</span></div><div className="slide-content"><span className="slide-chip">TODAY’S CONCEPT</span><h3>{slide.title}</h3><p>{slide.body}</p><div className="formula">f (x, y) <span>=</span> x² + y²</div></div><div className="slide-footer">LEARNING, ONE STEP AT A TIME <span>✳</span></div></div>
              <div className="slide-controls"><span>Slide {slide.number} of {slides.length} <span className="muted"> · {slide.topic}</span></span><div><button aria-label="Previous slide" disabled={slideIndex === 0} onClick={() => setSlideIndex(slideIndex - 1)}>←</button><button aria-label="Next slide" disabled={slideIndex === slides.length - 1} onClick={() => setSlideIndex(slideIndex + 1)}>→</button></div></div>
            </section><aside className="right-column"><section className="card lost-card"><div className="sparkle">✳</div><span className="section-kicker">A LITTLE LOST?</span><h2>It happens to<br />everyone.</h2><p>Save this moment and come back to it when you’re ready. No raised hands required.</p><LostButton slide={slide} lectureStartedAt={lectureStartedAt} onLost={markLost} onAttachScreenshot={attachScreenshot} /></section>
              <section className="card captions-card"><div className="card-line"><div><span className="section-kicker">FOLLOW ALONG</span><h3>Live captions</h3></div><span className="caption-icon">“ ”</span></div><div className="caption-placeholder">Captions will appear here when a live lecture is connected.</div><div className="caption-foot"><span>◉ &nbsp; English</span><span>Coming soon</span></div></section></aside></div>
            <section className="bottom-banner"><div className="banner-icon">✧</div><div><strong>Understanding takes practice.</strong><p>Your personal coach is here to help you find your own way through.</p></div><button onClick={() => setView('coach')}>Meet your coach <span>→</span></button></section>
          </>}
          {view === 'moments' && <section className="secondary-page"><div className="eyebrow">YOUR LEARNING JOURNEY</div><h1>Your lost moments<span className="accent">.</span></h1><p>Little reminders that you’re learning something new.</p><div className="card list-card">{moments.length === 0 ? <div className="empty"><div className="sparkle">✳</div><h2>Nothing saved yet</h2><p>When something doesn’t quite click, save the slide and revisit it here.</p><button className="text-button" onClick={() => setView('lecture')}>Go to lecture →</button></div> : moments.map((moment) => <div className={moment.resolved ? 'moment resolved' : 'moment'} key={moment.id}>{screenshotUrl(moment) ? <img className="moment-thumb" src={screenshotUrl(moment)} alt={`Photo of slide ${moment.slide_number}`} /> : <div className="moment-number">{String(moment.slide_number).padStart(2, '0')}</div>}<div><strong>{moment.topic}</strong><p>Slide {moment.slide_number} · {new Date(moment.created_at).toLocaleString()}{!moment.synced && ' · saved on this device'}{moment.resolved && ' · understood'}</p></div><button onClick={() => { setSlideIndex(Math.min(moment.slide_number, slides.length) - 1); setMessages(initialMessages); setView('coach') }}>Explore →</button><button onClick={() => toggleResolved(moment.id)}>{moment.resolved ? 'Reopen' : 'Mark understood'}</button></div>)}</div></section>}
          {view === 'coach' && <section className="secondary-page"><div className="eyebrow">A LITTLE GUIDANCE GOES A LONG WAY</div><h1>Meet your coach<span className="accent">.</span></h1><p>Think it through, one question at a time.</p><div className="card chat-card"><div className="chat-header"><div className="coach-avatar">✧</div><div><strong>Learning coach</strong><p>Demo prompts · Slide {slide.number}: {slide.topic}</p></div><span className="guide-badge">GUIDE MODE</span></div><div className="chat-messages">{messages.map((message, index) => <div className={`message ${message.from}`} key={index}><span>{message.from === 'coach' ? '✧' : 'You'}</span><p>{message.text}</p></div>)}</div><form className="chat-form" onSubmit={sendMessage}><label className="sr-only" htmlFor="message">Your message</label><input id="message" value={input} onChange={(event) => setInput(event.target.value)} placeholder="Share what you’re thinking..." /><button type="submit">Send ↑</button></form><p className="chat-disclaimer">Demo coach uses preset prompts; AI and slide search are not connected yet.</p></div></section>}
          {view === 'insights' && <section className="secondary-page"><div className="eyebrow">FOR LECTURERS</div><h1>Lecture insights<span className="accent">.</span></h1><p>See where your students might need a little more support.</p><div className="card insights-card">{heatmap ? <HeatmapLive heatmap={heatmap} slideCount={slides.length} /> : <><span className="sample-tag">SAMPLE DATA</span><h2>Introduction to Calculus</h2><p>This preview illustrates the lecture heatmap. The backend is not reachable, so sample data is shown.</p><div className="heatmap">{[12, 40, 22, 8, 31, 16, 45, 26].map((value, index) => <div key={index}><div className="bar-track"><div className="bar" style={{ height: `${value * 2}%` }} /></div><span>{index + 1}</span></div>)}</div><div className="heatmap-label">SAMPLE SLIDES <span>Counts below 5 students are hidden.</span></div></>}</div></section>}
        </div>
      </main>
    </div>
  )
}

function HeatmapLive({ heatmap, slideCount }) {
  const bySlide = Object.fromEntries(heatmap.slides.map((s) => [s.slide_number, s]))
  const count = Math.max(slideCount, ...heatmap.slides.map((s) => s.slide_number))
  const max = Math.max(1, ...heatmap.slides.map((s) => s.students ?? 0))
  const worst = heatmap.slides.filter((s) => !s.hidden).sort((a, b) => b.students - a.students)[0]
  return <>
    <span className="sample-tag">LIVE · ANONYMISED</span>
    <h2>Introduction to Calculus</h2>
    <p>{worst ? `Slide ${worst.slide_number} lost the most students (${worst.students}). Consider a short recap next lecture.` : `No slide has reached ${heatmap.min_students} students yet, so nothing is shown.`}</p>
    <div className="heatmap">{Array.from({ length: count }, (_, i) => i + 1).map((n) => {
      const s = bySlide[n]
      return <div key={n} title={s?.hidden ? `Fewer than ${heatmap.min_students} students` : `${s?.students ?? 0} students`}><div className="bar-track"><div className={s?.hidden ? 'bar bar-hidden' : 'bar'} style={{ height: s?.hidden ? '6%' : `${((s?.students ?? 0) / max) * 100}%` }} /></div><span>{n}</span></div>
    })}</div>
    <div className="heatmap-label">STUDENTS LOST PER SLIDE <span>Slides with fewer than {heatmap.min_students} students are hidden to protect privacy.</span></div>
  </>
}

export default App
