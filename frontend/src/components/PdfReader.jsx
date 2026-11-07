import { useEffect, useRef, useState } from 'react'
import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
GlobalWorkerOptions.workerSrc = workerUrl

export default function PdfReader({ lecture, page, onPage, onReady, readOnly = false }) {
  const canvas = useRef(null)
  const container = useRef(null)
  const [document, setDocument] = useState(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  const [width, setWidth] = useState(600)
  const [draft, setDraft] = useState('')
  const [rendering, setRendering] = useState(false)
  useEffect(() => {
    const observer = new ResizeObserver(entries => setWidth(Math.max(120, entries[0].contentRect.width - 24)))
    observer.observe(container.current)
    return () => observer.disconnect()
  }, [])
  useEffect(() => {
    let cancelled = false
    let task
    lecture.blob.arrayBuffer().then(data => {
      if (cancelled) return
      task = getDocument({ data, isEvalSupported: false })
      return task.promise
    }).then(pdf => { if (pdf && !cancelled) { setDocument(pdf); setError('') } }).catch(() => { if (!cancelled) setError('Unable to load this PDF. It may be damaged, encrypted, or unsupported. Retry or select another file in My Modules.') })
    return () => { cancelled = true; task?.destroy() }
  }, [lecture.blob, retry])
  useEffect(() => { if (document) onReady(document.numPages) }, [document, onReady])
  useEffect(() => {
    if (!document) return
    let cancelled = false
    let renderingTask
    let pdfPage
    async function render() {
      setRendering(true)
      try {
        pdfPage = await document.getPage(Math.min(page, document.numPages))
        if (cancelled) return
        const original = pdfPage.getViewport({ scale: 1 })
        const viewport = pdfPage.getViewport({ scale: width / original.width })
        const ratio = Math.min(window.devicePixelRatio || 1, 2)
        const target = canvas.current
        target.width = Math.floor(viewport.width * ratio)
        target.height = Math.floor(viewport.height * ratio)
        target.style.width = `${viewport.width}px`
        target.style.height = `${viewport.height}px`
        renderingTask = pdfPage.render({ canvasContext: target.getContext('2d'), viewport, transform: [ratio, 0, 0, ratio, 0, 0] })
        await renderingTask.promise
        if (!cancelled) { setError(''); setRendering(false) }
      } catch (err) { if (!cancelled && err.name !== 'RenderingCancelledException') { setError('Unable to render this page. Retry loading the PDF.'); setRendering(false) } }
    }
    render()
    return () => { cancelled = true; renderingTask?.cancel(); if (renderingTask) renderingTask.promise.catch(() => {}).finally(() => pdfPage?.cleanup()); else pdfPage?.cleanup() }
  }, [document, page, width])
  function jump(event) {
    event.preventDefault()
    const value = Number(draft)
    if (!Number.isInteger(value) || value < 1 || value > document.numPages) { setError(`Enter a page from 1 to ${document.numPages}.`); return }
    onPage(value); setDraft(''); setError('')
  }
  return <section className="lp-pdf" ref={container} aria-label="PDF reader">
    <div className="lp-page-controls"><button disabled={readOnly || !document || page <= 1} onClick={() => onPage(page - 1)}>Previous page</button><span>Viewing page <strong>{page}</strong> / {document?.numPages || '…'}</span><button disabled={readOnly || !document || page >= document.numPages} onClick={() => onPage(page + 1)}>Next page</button><form onSubmit={jump}><label htmlFor="pdf-page">Go to page</label><input id="pdf-page" type="number" min="1" max={document?.numPages} value={draft} placeholder={String(page)} onChange={event => setDraft(event.target.value)} disabled={readOnly || !document}/><button disabled={readOnly || !document || !draft}>Go</button></form></div>
    {error && <div className="module-error" role="alert">{error}<button onClick={() => { setDocument(null); setError(''); setRetry(value => value + 1) }}>Retry PDF</button></div>}
    {!document && !error && <p role="status">Loading PDF…</p>}
    {rendering && <span className="lp-render-status" role="status">Rendering page…</span>}
    <div className="lp-canvas" tabIndex={0} role="region" aria-label="Scrollable PDF page"><canvas ref={canvas} aria-label={`PDF page ${page}`}/></div>
    <p className="lp-note">Only the current page is rendered. PDF text is displayed visually; use your original PDF reader for text accessibility.</p>
  </section>
}
