import { useState } from 'react'
import './App.css'
import './Modules.css'
import './brand.css'
import './coach.css'
import './theme.css'
import LectureInsights from './components/LectureInsights'
import LiveWorkspace from './components/LiveWorkspace'
import Modules from './components/Modules'
import Sidebar from './components/Sidebar'
import { askCoach } from './data/api'

// The built-in demo lecture. Its coach uses the server's copy of these slides
// (Stephanie's demo fallback), so it works before anything is uploaded.
const slides = [
  { number: 1, title: 'The big picture', topic: 'Functions of several variables', body: 'What happens when an output depends on more than one input?' },
  { number: 2, title: 'Meet partial derivatives', topic: 'Partial derivatives', body: 'A partial derivative describes how a function changes as one variable changes, while the others stay constant.' },
  { number: 3, title: 'A closer look', topic: 'Holding variables constant', body: 'To find the partial derivative with respect to x, treat y as a constant.' },
]

const TITLES = { modules: 'My Modules', sample: 'Demo lecture', sampleCoach: 'Demo coach', lecture: 'Live Lecture', moments: 'Lost Moments', coach: 'My Coach', insights: 'Lecture Insights' }

function SampleCoach({ slide, onBack }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [mode, setMode] = useState('GUIDE')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [solved, setSolved] = useState(false)
  async function send(event) {
    event.preventDefault()
    const message = input.trim()
    if (!message || busy) return
    setBusy(true); setError(''); setMessages(current => [...current, { from: 'you', text: message }]); setInput('')
    try {
      const reply = await askCoach({ slideNumber: slide.number, message })
      setMessages(current => [...current, { from: 'coach', text: reply.response }])
      setMode(reply.mode); setSolved(reply.gap_closed)
    } catch (err) {
      setMessages(current => current.slice(0, -1)); setInput(message); setError(err.message)
    } finally { setBusy(false) }
  }
  return <section className="secondary-page">
    <div className="eyebrow">A LITTLE GUIDANCE GOES A LONG WAY</div>
    <h1>Meet your coach<span className="accent">.</span></h1>
    <p>Think it through, one question at a time.</p>
    <div className="card chat-card">
      <div className="chat-header"><div className="coach-avatar">✧</div><div><strong>Learning coach</strong><p>Demo lecture · Slide {slide.number}: {slide.topic}</p></div><span className="guide-badge">{mode === 'LOCKED' ? 'HINTS ONLY' : `${mode} MODE`}</span></div>
      <div className="chat-messages" aria-live="polite">
        {messages.length === 0 && <p className="chat-empty">What do you think “{slide.topic.toLowerCase()}” means? Have a go, even if you’re unsure.</p>}
        {messages.map((message, index) => <div className={`message ${message.from}`} key={index}><span>{message.from === 'coach' ? '✧' : 'You'}</span><p>{message.text}</p></div>)}
        {busy && <p className="chat-status" role="status">The coach is thinking…</p>}
      </div>
      <form className="chat-form" onSubmit={send}><label className="sr-only" htmlFor="message">Your message</label><input id="message" value={input} onChange={event => setInput(event.target.value)} placeholder="I think it means…" disabled={busy} /><button type="submit" disabled={busy || !input.trim()}>{busy ? 'Thinking…' : 'Send ↑'}</button></form>
      {error && <p className="chat-error" role="alert">{error}</p>}
      {solved && <p className="chat-success" role="status">🎉 You worked it out yourself!</p>}
      <p className="chat-disclaimer">Demo lecture. To get help with your own slides, upload them in My Modules. <button className="text-button" onClick={onBack}>Back to the demo lecture</button></p>
    </div>
  </section>
}

function App() {
  const [view, setView] = useState('modules')
  const [slideIndex, setSlideIndex] = useState(1)
  const [activeLecture, setActiveLecture] = useState(null)
  const [pointCoach, setPointCoach] = useState(false)
  const [moduleEntry, setModuleEntry] = useState(null)
  const [momentScope, setMomentScope] = useState(null)
  const [pointCount, setPointCount] = useState(0)
  const slide = slides[slideIndex]

  function openLecture(lecture) {
    setActiveLecture(lecture); setPointCoach(false); setView('lecture')
  }

  return (
    <div className="app-shell">
      <Sidebar view={view} onNavigate={next => { if (next === 'coach') setPointCoach(false); setView(next) }} count={pointCount} />
      <main className="main">
        <header className="topbar"><div><span className="breadcrumb">Workspace</span><span className="slash">/</span><strong>{TITLES[view]}</strong></div><button className="topbar-help" onClick={() => setView('sample')}>Try the demo lecture</button></header>
        <div className="content">
          <div hidden={view !== 'modules'}><Modules requestedModule={moduleEntry} onMoments={moduleId => { setMomentScope({ moduleId, entry: crypto.randomUUID() }); setView('moments') }} onOpen={openLecture} /></div>
          <LiveWorkspace lecture={activeLecture} view={view} onNavigate={setView} onOpenLecture={openLecture} onLectureUpdate={setActiveLecture} coachActive={pointCoach} momentScope={momentScope} onModule={moduleId => { setModuleEntry({ moduleId, entry: crypto.randomUUID() }); setView('modules') }} onCoachChange={setPointCoach} onCountChange={setPointCount} />
          {view === 'lecture' && !activeLecture && <section className="card module-guidance"><h1>Live Lecture</h1><p>Open a lecture from My Modules to follow along: see the slides, read live captions in your language, and press “I’m lost” whenever something doesn’t click.</p><button className="module-button" onClick={() => setView('modules')}>Choose a lecture</button><button className="module-secondary" onClick={() => setView('sample')}>Try the demo lecture</button></section>}
          {view === 'sample' && <>
            <div className="page-heading"><div><div className="eyebrow"><span className="live-dot" /> DEMO LECTURE</div><h1>Stay curious. <em>We’ve got you.</em></h1><p>A three-slide calculus lecture to try LostPoint before uploading your own slides.</p></div></div>
            <div className="lecture-layout"><section className="card lecture-card"><div className="card-top"><div><div className="section-kicker">DEMO LECTURE</div><h2>Introduction to Calculus</h2><p>Week 3 · Multivariable functions</p></div><div className="subject-icon">∑</div></div>
              <div className="slide"><div className="slide-top"><span>CALCULUS · WEEK 3</span><span>{String(slide.number).padStart(2, '0')} / 03</span></div><div className="slide-content"><span className="slide-chip">TODAY’S CONCEPT</span><h3>{slide.title}</h3><p>{slide.body}</p><div className="formula">f (x, y) <span>=</span> x² + y²</div></div><div className="slide-footer">LEARNING, ONE STEP AT A TIME <span>✳</span></div></div>
              <div className="slide-controls"><span>Slide {slide.number} of {slides.length} <span className="muted"> · {slide.topic}</span></span><div><button aria-label="Previous slide" disabled={slideIndex === 0} onClick={() => setSlideIndex(slideIndex - 1)}>←</button><button aria-label="Next slide" disabled={slideIndex === slides.length - 1} onClick={() => setSlideIndex(slideIndex + 1)}>→</button></div></div>
            </section><aside className="right-column"><section className="card lost-card"><div className="sparkle">✳</div><span className="section-kicker">A LITTLE LOST?</span><h2>It happens to everyone.</h2><p>Press the button and your coach will help you work through this slide. No raised hands required.</p><button className="primary-button" onClick={() => setView('sampleCoach')}>⌁ &nbsp; I’m lost <span>→</span></button><div className="private-note">♡ &nbsp; Just for you, always private</div></section></aside></div>
          </>}
          {view === 'sampleCoach' && <SampleCoach key={slide.number} slide={slide} onBack={() => setView('sample')} />}
          {view === 'insights' && <LectureInsights />}
        </div>
      </main>
    </div>
  )
}

export default App
