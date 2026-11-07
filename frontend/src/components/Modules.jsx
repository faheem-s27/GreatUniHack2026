import { useEffect, useRef, useState } from 'react'
import { checkLecture, connectLecture, createModule, loadLibrary, saveLecture } from '../data/modules'
const sizeLabel = size => size < 1024 * 1024 ? `${(size / 1024).toFixed(1)} KB` : `${(size / 1024 / 1024).toFixed(1)} MB`
export default function Modules({ onOpen, onMoments, requestedModule }) {
  const [library, setLibrary] = useState(null)
  const [selected, setSelected] = useState(null)
  const [appliedEntry, setAppliedEntry] = useState(null)
  const [error, setError] = useState('')
  const [modalError, setModalError] = useState('')
  const [name, setName] = useState('')
  const [file, setFile] = useState(null)
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [status, setStatus] = useState('')
  const [assessed, setAssessed] = useState(false)
  const [connecting, setConnecting] = useState('')
  const dialog = useRef(null)
  const nameInput = useRef(null)
  const addButton = useRef(null)
  const fileInput = useRef(null)
  const urls = useRef([])
  async function reload() {
    try { setLibrary(await loadLibrary()); setError('') } catch (err) { setError(err.message) }
  }
  useEffect(() => { let cancelled = false; loadLibrary().then(async value => { if (!cancelled) setLibrary(value); const checked = await Promise.all(value.lectures.filter(item => item.serverId).map(item => checkLecture(item.id).catch(() => item))); if (!cancelled && checked.some(item => item && !item.serverId)) setLibrary(await loadLibrary()) }).catch(err => { if (!cancelled) setError(err.message) }); const opened = urls.current; return () => { cancelled = true; opened.forEach(URL.revokeObjectURL) } }, [])
  if (requestedModule !== appliedEntry) {
    setAppliedEntry(requestedModule)
    if (requestedModule?.moduleId) {
      if (file || busy) setError('Remove or save your selected PDF before switching modules.')
      else { setSelected(requestedModule.moduleId); setError('') }
    }
  }
  const module = library?.modules.find(item => item.id === selected)
  const lectures = library?.lectures.filter(item => item.moduleId === selected) || []
  function chooseModule(id) {
    if (id === selected) return
    if (file || busy) { setError('Remove or save your selected PDF before switching modules.'); return }
    setSelected(id); setError(''); setStatus('')
  }
  function chooseFile(files) {
    setStatus('')
    if (busy) return
    if (files.length !== 1 || !/\.pdf$/i.test(files[0].name) || (files[0].type && files[0].type !== 'application/pdf')) { setError('Choose one PDF file at a time. Other file types are not supported.'); return }
    setFile(files[0]); setTitle(files[0].name.replace(/\.pdf$/i, '')); setError('')
  }
  function removeFile() { setFile(null); setTitle(''); setAssessed(false); fileInput.current.value = ''; setError('') }
  async function create(event) {
    event.preventDefault(); if (busy) return; setBusy(true); setModalError('')
    try { const item = await createModule(name); const next = await loadLibrary(); setLibrary(next); setSelected(item.id); dialog.current.close(); setName(''); setStatus('Module created.'); } catch (err) { setModalError(`${err.message} Please check the name or retry.`) } finally { setBusy(false) }
  }
  async function upload(event) {
    event.preventDefault(); if (busy) return; setBusy(true); setError(''); setStatus('Uploading and reading your PDF…')
    try { const item = await saveLecture(selected, title, file, { assessed }); setLibrary(previous => ({ ...previous, lectures: [...previous.lectures, item] })); removeFile(); setStatus(item.serverId ? `“${item.title}” is ready. The coach can read ${item.readableSlides} of its slides.` : `“${item.title}” is saved on this device, but the coach can’t read it yet: ${item.serverError} Use “Let the coach read it” to try again.`) } catch (err) { setError(err.message); setStatus('') } finally { setBusy(false) }
  }
  async function connect(lecture) {
    setConnecting(lecture.id); setError('')
    try {
      const item = await connectLecture(lecture.id)
      setLibrary(previous => ({ ...previous, lectures: previous.lectures.map(value => value.id === item.id ? item : value) }))
      setStatus(item.serverId ? `The coach can now read “${item.title}”.` : `The coach still can’t read “${item.title}”: ${item.serverError}`)
    } catch (err) { setError(err.message) }
    finally { setConnecting('') }
  }
  function open(lecture) {
    if (!lecture.blob) { setError('This PDF is unavailable on this device. Please select the file again.'); return }
    const url = URL.createObjectURL(lecture.blob); urls.current.push(url)
    onOpen({ ...lecture, lectureId: lecture.id, moduleName: module.name, url })
  }
  return <section className="modules-page"><div className="modules-heading"><h1>My Modules</h1><button ref={addButton} className="module-button" disabled={!library || busy} onClick={() => { if (file) { setError('Remove or save your selected PDF before adding a module.'); return } setModalError(''); dialog.current.showModal(); nameInput.current.focus() }}>+ Add module</button></div><p className="modules-intro">Choose a module, then add your lecture slides as PDFs. The coach reads them so it can point you to the right slide.</p>{error && <div className="module-error" role="alert">{error}{!library && <button onClick={reload}>Retry loading</button>}</div>}{!library && !error && <p role="status">Loading modules…</p>}<div className="module-grid">{library?.modules.map(item => { const count = library.lectures.filter(lecture => lecture.moduleId === item.id).length; return <button key={item.id} className={`module-card ${selected === item.id ? 'selected' : ''}`} aria-pressed={selected === item.id} onClick={() => chooseModule(item.id)}><span className="module-card-icon" aria-hidden="true">▤</span><strong>{item.name}</strong><span>{count} {count === 1 ? 'lecture' : 'lectures'} · {count} {count === 1 ? 'PDF' : 'PDFs'}</span><span className="selection-label">{selected === item.id ? '✓ Selected' : 'Select module →'}</span></button> })}</div>{module && <section className="module-detail" aria-labelledby="selected-module"><div className="modules-heading"><h2 id="selected-module">{module.name}</h2><button className="module-secondary" onClick={() => onMoments(module.id)}>View lost moments</button></div><div className="module-detail-grid"><section className="card lecture-list"><h3>Lecture slides <span>({lectures.length})</span></h3>{!lectures.length && <p>No lecture slides yet. Choose a PDF to add your first lecture.</p>}{lectures.map(lecture => <article className="lecture-row" key={lecture.id}><h4>{lecture.title}</h4><p>{lecture.fileName}</p><small>Added {new Date(lecture.addedAt).toLocaleString()}{lecture.assessed ? ' · Assessed coursework (hints only)' : ''}</small>{lecture.serverId ? <span className="lp-ready">✓ Coach can read it</span> : <span className="lp-not-ready">Coach can’t read it yet<button className="module-secondary" disabled={connecting === lecture.id} onClick={() => connect(lecture)}>{connecting === lecture.id ? 'Sending…' : 'Let the coach read it'}</button></span>}<button className="module-button" onClick={() => open(lecture)}>Open lecture</button></article>)}</section><section className="card upload-panel"><h3>Upload to {module.name}</h3><p>One PDF at a time. It opens from this device, and the server reads its text so the coach can search it.</p><form onSubmit={upload}><div className={`pdf-drop ${dragging ? 'dragging' : ''}`} onDragOver={event => { event.preventDefault(); setDragging(true) }} onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false) }} onDrop={event => { event.preventDefault(); setDragging(false); chooseFile(event.dataTransfer.files) }}><span aria-hidden="true">↑</span><p>Drag a PDF here or choose a file</p><button type="button" className="module-secondary" disabled={busy} onClick={() => fileInput.current.click()}>Choose PDF</button><input ref={fileInput} type="file" accept="application/pdf,.pdf" hidden onChange={event => { if (event.target.files.length) chooseFile(event.target.files) }}/></div>{file && <div className="file-details"><strong>{file.name}</strong><small>{sizeLabel(file.size)}</small><button type="button" disabled={busy} className="remove-file" onClick={removeFile}>Remove file</button><label htmlFor="lecture-title">Lecture title</label><input id="lecture-title" required value={title} disabled={busy} onChange={event => setTitle(event.target.value)}/><button className="module-button" disabled={busy || !title.trim()}>{busy ? 'Uploading…' : 'Upload PDF'}</button><label className="lp-check"><input type="checkbox" checked={assessed} disabled={busy} onChange={event => setAssessed(event.target.checked)} />This is assessed coursework: the coach will only give hints, never the solution</label></div>}</form></section></div></section>}{status && <p role="status" className="module-status">{status}</p>}<dialog ref={dialog} aria-labelledby="add-module-heading" className="module-dialog" onCancel={event => { if (busy) event.preventDefault() }} onClose={() => addButton.current?.focus()}><form onSubmit={create}><h2 id="add-module-heading">Add module</h2><label htmlFor="module-name">Module name</label><input ref={nameInput} id="module-name" value={name} disabled={busy} onChange={event => setName(event.target.value)} required autoComplete="off"/>{modalError && <p role="alert" className="module-error">{modalError}</p>}<div className="dialog-actions"><button type="button" className="module-secondary" disabled={busy} onClick={() => dialog.current.close()}>Cancel</button><button className="module-button" disabled={busy || !name.trim()}>{busy ? 'Creating…' : 'Create module'}</button></div></form></dialog></section>
}
