import { useState } from 'react'
import './App.css'
import Modules from './components/Modules'
import Sidebar from './components/Sidebar'
import './Modules.css'
import LiveWorkspace from './components/LiveWorkspace'

const slides = [
  { number: 1, title: 'The big picture', topic: 'Functions of several variables', body: 'What happens when an output depends on more than one input?' },
  { number: 2, title: 'Meet partial derivatives', topic: 'Partial derivatives', body: 'A partial derivative describes how a function changes as one variable changes, while the others stay constant.' },
  { number: 3, title: 'A closer look', topic: 'Holding variables constant', body: 'To find the partial derivative with respect to x, treat y as a constant.' },
]
const initialMessages = [{ from: 'coach', text: 'Let’s work through this together. What do you think it means to hold one variable constant?' }]

function App() {
  const [view, setView] = useState('modules')
  const [slideIndex, setSlideIndex] = useState(1)
  const [moments, setMoments] = useState(() => {
    try { return JSON.parse(localStorage.getItem('lostpoint-moments') || '[]') } catch { return [] }
  })
  const [messages, setMessages] = useState(initialMessages)
  const [input, setInput] = useState('')
  const [notice, setNotice] = useState('')
  const [activeLecture, setActiveLecture] = useState(null)
  const [recording, setRecording] = useState(false)
  const [pointCoach, setPointCoach] = useState(false)
  const [moduleEntry, setModuleEntry] = useState(null)
  const [momentScope, setMomentScope] = useState(null)
  const [pointCount, setPointCount] = useState(0)
  function openLecture(lecture) {
    if (recording && activeLecture?.lectureId !== lecture.lectureId) {
      window.alert('Stop the current recording or subtitle demo before opening another lecture.')
      return
    }
    setActiveLecture(lecture); setPointCoach(false); setMessages([{ from: 'coach', text: 'Use I’m lost in Live Lecture to save a PDF page and its subtitle context. AI coaching is not connected.' }]); setView('lecture')
  }
  const slide = slides[slideIndex]

  function markLost() {
    const next = [{ id: crypto.randomUUID(), slide: slide.number, topic: slide.topic, time: new Date().toISOString(), resolved: false }, ...moments]
    setMoments(next)
    localStorage.setItem('lostpoint-moments', JSON.stringify(next))
    setNotice(`Saved slide ${slide.number} to your lost moments.`)
  }

  function toggleMoment(id) {
    const next = moments.map((moment) => moment.id === id ? { ...moment, resolved: !moment.resolved } : moment)
    setMoments(next)
    localStorage.setItem('lostpoint-moments', JSON.stringify(next))
  }

  function sendMessage(event) {
    event.preventDefault()
    if (!input.trim()) return
    setMessages([...messages, { from: 'you', text: input.trim() }, { from: 'coach', text: activeLecture ? `What part of ${activeLecture.title} would you like to explore? This demo cannot read your PDF or provide AI answers yet.` : `Good start. Look back at slide ${slide.number}: what changes, and what stays the same? Try explaining it in your own words.` }])
    setInput('')
  }

  return (
    <div className="app-shell">
      <Sidebar view={view} onNavigate={next => { if (next === 'coach') setPointCoach(false); setView(next) }} count={pointCount + moments.filter((m) => !m.resolved).length} />

      <main className="main">
        <header className="topbar"><div><span className="breadcrumb">Workspace</span><span className="slash">/</span><strong>{({ modules: 'My Modules', sample: 'Sample lecture', sampleCoach: 'Sample Coach', lecture: 'Live Lecture', moments: 'Lost Moments', coach: 'My Coach', insights: 'Lecture Insights' })[view]}</strong></div><span className="demo-badge"><i /> Demo workspace</span></header>
        <div className="content">
          <div hidden={view !== 'modules'}><Modules requestedModule={moduleEntry} onMoments={moduleId => { setMomentScope({ moduleId, entry: crypto.randomUUID() }); setView('moments') }} onOpen={openLecture} /></div>
          <LiveWorkspace lecture={activeLecture} view={view} onNavigate={setView} onOpenLecture={openLecture} onRecordingChange={setRecording} coachActive={pointCoach} momentScope={momentScope} onModule={moduleId => { setModuleEntry({ moduleId, entry: crypto.randomUUID() }); setView('modules') }} onCoachChange={setPointCoach} onCountChange={setPointCount}/>
          {view === 'lecture' && !activeLecture && <section className="card module-guidance"><h1>Live Lecture</h1><p>Select a module and open lecture slides to begin.</p><button className="module-button" onClick={() => setView('modules')}>Choose lecture slides</button><button className="module-secondary" onClick={() => { if (recording) { window.alert('Stop recording or subtitle demo first.'); return } setPointCoach(false); setActiveLecture(null); setMessages(initialMessages); setView('sample') }}>View sample lecture</button></section>}
          {view === 'sample' && <>
            <div className="page-heading"><div><div className="eyebrow"><span className="live-dot" /> YOUR LEARNING SPACE</div><h1>Stay curious. <em>We’ve got you.</em></h1><p>Every question is a good place to start.</p></div><span className="date-pill">✦ &nbsp; Your lecture companion</span></div>
            <div className="demo-notice">✧ &nbsp; You’re exploring a demo lecture. Your saved moments stay in this browser.</div>
            <div className="lecture-layout"><section className="card lecture-card"><div className="card-top"><div><div className="section-kicker">CURRENT LECTURE <span className="sample-tag">SAMPLE</span></div><h2>Introduction to Calculus</h2><p>Week 03 · Multivariable functions</p></div><div className="subject-icon">∑</div></div>
              <div className="slide"><div className="slide-top"><span>CALCULUS · WEEK 03</span><span>{String(slide.number).padStart(2, '0')} / 03</span></div><div className="slide-content"><span className="slide-chip">TODAY’S CONCEPT</span><h3>{slide.title}</h3><p>{slide.body}</p><div className="formula">f (x, y) <span>=</span> x² + y²</div></div><div className="slide-footer">LEARNING, ONE STEP AT A TIME <span>✳</span></div></div>
              <div className="slide-controls"><span>Slide {slide.number} of {slides.length} <span className="muted"> · {slide.topic}</span></span><div><button aria-label="Previous slide" disabled={slideIndex === 0} onClick={() => setSlideIndex(slideIndex - 1)}>←</button><button aria-label="Next slide" disabled={slideIndex === slides.length - 1} onClick={() => setSlideIndex(slideIndex + 1)}>→</button></div></div>
            </section><aside className="right-column"><section className="card lost-card"><div className="sparkle">✳</div><span className="section-kicker">A LITTLE LOST?</span><h2>It happens to<br />everyone.</h2><p>Save this moment and come back to it when you’re ready. No raised hands required.</p><button className="primary-button" onClick={markLost}>⌁ &nbsp; I’m lost <span>→</span></button><div className="private-note">♡ &nbsp; Just for you, always private</div>{notice && <p className="success" role="status">{notice}</p>}</section>
              <section className="card captions-card"><div className="card-line"><div><span className="section-kicker">FOLLOW ALONG</span><h3>Live captions</h3></div><span className="caption-icon">“ ”</span></div><div className="caption-placeholder">Captions will appear here when a live lecture is connected.</div><div className="caption-foot"><span>◉ &nbsp; English</span><span>Coming soon</span></div></section></aside></div>
            <section className="bottom-banner"><div className="banner-icon">✧</div><div><strong>Understanding takes practice.</strong><p>Your personal coach is here to help you find your own way through.</p></div><button onClick={() => { setPointCoach(false); setView('sampleCoach') }}>Meet your coach <span>→</span></button></section>
          </>}
          {view === 'moments' && moments.length > 0 && <section className="secondary-page"><div className="eyebrow">YOUR LEARNING JOURNEY</div><h1>Sample lost moments<span className="accent">.</span></h1><p>Little reminders that you’re learning something new.</p><div className="card list-card">{moments.length === 0 ? <div className="empty"><div className="sparkle">✳</div><h2>Nothing saved yet</h2><p>When something doesn’t quite click, save the slide and revisit it here.</p><button className="text-button" onClick={() => setView('lecture')}>Go to lecture →</button></div> : moments.map((moment) => <div className="moment" key={moment.id}><div className="moment-number">{String(moment.slide).padStart(2, '0')}</div><div><strong>{moment.topic}</strong><p>Slide {moment.slide} · {new Date(moment.time).toLocaleString()}</p></div><button onClick={() => { if (recording) { window.alert('Stop recording or subtitle demo first.'); return } setPointCoach(false); setActiveLecture(null); setSlideIndex(moment.slide - 1); setMessages(initialMessages); setView('sampleCoach') }}>Explore →</button><button onClick={() => toggleMoment(moment.id)}>{moment.resolved ? 'Reopen' : 'Mark understood'}</button></div>)}</div></section>}
          {view === 'sampleCoach' && <section className="secondary-page"><div className="eyebrow">A LITTLE GUIDANCE GOES A LONG WAY</div><h1>Meet your coach<span className="accent">.</span></h1><p>Think it through, one question at a time.</p><div className="card chat-card"><div className="chat-header"><div className="coach-avatar">✧</div><div><strong>Learning coach</strong><p>Demo prompts · {activeLecture ? `${activeLecture.moduleName}: ${activeLecture.title}` : `Sample slide ${slide.number}: ${slide.topic}`}</p></div><span className="guide-badge">GUIDE MODE</span></div><div className="chat-messages">{messages.map((message, index) => <div className={`message ${message.from}`} key={index}><span>{message.from === 'coach' ? '✧' : 'You'}</span><p>{message.text}</p></div>)}</div><form className="chat-form" onSubmit={sendMessage}><label className="sr-only" htmlFor="message">Your message</label><input id="message" value={input} onChange={(event) => setInput(event.target.value)} placeholder="Share what you’re thinking..." /><button type="submit">Send ↑</button></form><p className="chat-disclaimer">Demo coach uses preset prompts; AI and slide search are not connected yet.</p></div></section>}
          {view === 'insights' && <section className="secondary-page"><div className="eyebrow">FOR LECTURERS</div><h1>Lecture insights<span className="accent">.</span></h1><p>See where your students might need a little more support.</p><div className="card insights-card"><span className="sample-tag">SAMPLE DATA</span><h2>Introduction to Calculus</h2><p>This preview illustrates the lecture heatmap. Real, anonymised class data is not connected yet.</p><div className="heatmap">{[12, 40, 22, 8, 31, 16, 45, 26].map((value, index) => <div key={index}><div className="bar-track"><div className="bar" style={{ height: `${value * 2}%` }} /></div><span>{index + 1}</span></div>)}</div><div className="heatmap-label">SAMPLE SLIDES <span>Counts below 5 students will be hidden in the real dashboard.</span></div></div></section>}
        </div>
      </main>
    </div>
  )
}

export default App
