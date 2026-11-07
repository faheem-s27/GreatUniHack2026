import { useRef, useState } from 'react'

// One tap saves the slide and the time. A photo of the projector is optional
// and offered *after* the tap, so saving the moment never waits on the camera.
export default function LostButton({ slide, lectureStartedAt, onLost, onAttachScreenshot }) {
  const [last, setLast] = useState(null) // { moment, synced }
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)
  const fileInput = useRef(null)

  async function handleTap() {
    const lectureTimeS = Math.round((Date.now() - lectureStartedAt) / 1000)
    const result = await onLost({ slideNumber: slide.number, topic: slide.topic, lectureTimeS })
    setLast(result)
    setStatus(result.synced
      ? `Saved slide ${slide.number}. You can come back to it later.`
      : `Saved slide ${slide.number} on this device. It will sync when you are back online.`)
  }

  async function handlePhoto(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || !last) return
    setBusy(true)
    try {
      const uploaded = await onAttachScreenshot(last.moment.id, file)
      setStatus(uploaded ? `Photo added to slide ${last.moment.slide_number}.` : 'Photo saved on this device. It will upload when you are back online.')
    } catch {
      setStatus('Could not read that photo. Try another one.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <button className="primary-button" onClick={handleTap}>⌁ &nbsp; I’m lost <span>→</span></button>
      {last && (
        <>
          <button className="secondary-button" disabled={busy} onClick={() => fileInput.current?.click()}>
            {busy ? 'Adding photo…' : '◫  Add a photo of the slide'}
          </button>
          <input ref={fileInput} type="file" accept="image/*" capture="environment" hidden onChange={handlePhoto} />
        </>
      )}
      <div className="private-note">♡ &nbsp; Just for you, always private</div>
      {status && <p className="success" role="status">{status}</p>}
    </>
  )
}
