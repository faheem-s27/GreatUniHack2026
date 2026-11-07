// "I'm lost" moments: API client, offline queue and React hook.
//
// A tap is saved on the device first, then sent to the backend. If the
// backend is down (or the lecture hall Wi-Fi is), the moment stays queued
// with synced: false and is retried on the next load or when the browser
// comes back online. The client-generated id makes retries idempotent.

import { useCallback, useEffect, useState } from 'react'

const STORAGE_KEY = 'lostpoint-moments-v2'
const STUDENT_KEY = 'lostpoint-student-id'

export function getStudentId() {
  try {
    let id = localStorage.getItem(STUDENT_KEY)
    if (!id) {
      id = crypto.randomUUID()
      localStorage.setItem(STUDENT_KEY, id)
    }
    return id
  } catch {
    return 'anonymous'
  }
}

function loadLocal() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]') } catch { return [] }
}

function saveLocal(moments) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(moments)) } catch { /* storage full or blocked: keep in memory */ }
}

async function api(path, options = {}) {
  const res = await fetch(`/api${path}`, { headers: { 'Content-Type': 'application/json' }, ...options })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export function screenshotUrl(moment) {
  if (moment.screenshotDataUrl) return moment.screenshotDataUrl
  if (moment.has_screenshot) return `/api/lost-moments/${moment.id}/screenshot?student_id=${encodeURIComponent(getStudentId())}`
  return null
}

// Phone photos are 3-12 MB; shrink to a JPEG the vision model can still read.
export function downscaleImage(file, maxSide = 1280, quality = 0.8) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => {
      const scale = Math.min(1, maxSide / Math.max(img.width, img.height))
      const canvas = document.createElement('canvas')
      canvas.width = Math.round(img.width * scale)
      canvas.height = Math.round(img.height * scale)
      canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height)
      URL.revokeObjectURL(url)
      resolve(canvas.toDataURL('image/jpeg', quality))
    }
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Could not read that image')) }
    img.src = url
  })
}

export function useLostMoments(lectureId) {
  const [moments, setMomentsState] = useState(loadLocal)
  const [online, setOnline] = useState(true)

  const setMoments = useCallback((update) => {
    setMomentsState((prev) => {
      const next = typeof update === 'function' ? update(prev) : update
      saveLocal(next)
      return next
    })
  }, [])

  // Push one moment (and its pending screenshot / resolved state) to the server.
  const pushMoment = useCallback(async (moment) => {
    const studentId = getStudentId()
    let saved = moment
    if (!moment.synced) {
      const server = await api('/lost-moments', {
        method: 'POST',
        body: JSON.stringify({ id: moment.id, student_id: studentId, lecture_id: moment.lecture_id, slide_number: moment.slide_number, topic: moment.topic, lecture_time_s: moment.lecture_time_s }),
      })
      saved = { ...moment, ...server, resolved: moment.resolved, synced: true }
      if (moment.resolved !== server.resolved) {
        await api(`/lost-moments/${server.id}`, { method: 'PATCH', body: JSON.stringify({ student_id: studentId, resolved: moment.resolved }) })
      }
    }
    if (moment.screenshotDataUrl) {
      const server = await api(`/lost-moments/${saved.id}/screenshot`, { method: 'PUT', body: JSON.stringify({ student_id: studentId, data_url: moment.screenshotDataUrl }) })
      saved = { ...saved, has_screenshot: server.has_screenshot, screenshotDataUrl: undefined }
    }
    return saved
  }, [])

  // Replace a local moment with its synced version. The server may return a
  // different id when it merged a double tap into an earlier moment.
  const applySynced = useCallback((localId, saved) => {
    setMoments((prev) => {
      const without = prev.filter((m) => m.id !== localId && m.id !== saved.id)
      const index = prev.findIndex((m) => m.id === localId)
      without.splice(Math.max(0, index), 0, saved)
      return without
    })
  }, [setMoments])

  const sync = useCallback(async () => {
    const pending = loadLocal().filter((m) => !m.synced || m.screenshotDataUrl)
    for (const moment of pending) {
      try { applySynced(moment.id, await pushMoment(moment)) } catch { setOnline(false); return }
    }
    try {
      const server = await api(`/lost-moments?student_id=${encodeURIComponent(getStudentId())}`)
      setOnline(true)
      setMoments((prev) => {
        const unsynced = prev.filter((m) => !m.synced || m.screenshotDataUrl)
        const ids = new Set(unsynced.map((m) => m.id))
        return [...unsynced, ...server.filter((m) => !ids.has(m.id)).map((m) => ({ ...m, synced: true }))]
          .sort((a, b) => b.created_at.localeCompare(a.created_at))
      })
    } catch {
      setOnline(false)
    }
  }, [applySynced, pushMoment, setMoments])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial sync with the server
    sync()
    window.addEventListener('online', sync)
    return () => window.removeEventListener('online', sync)
  }, [sync])

  const markLost = useCallback(async ({ slideNumber, topic, lectureTimeS }) => {
    const moment = {
      id: crypto.randomUUID(),
      lecture_id: lectureId,
      slide_number: slideNumber,
      topic,
      lecture_time_s: lectureTimeS,
      created_at: new Date().toISOString(),
      resolved: false,
      has_screenshot: false,
      synced: false,
    }
    setMoments((prev) => [moment, ...prev])
    try {
      const saved = await pushMoment(moment)
      applySynced(moment.id, saved)
      setOnline(true)
      return { moment: saved, synced: true }
    } catch {
      setOnline(false)
      return { moment, synced: false }
    }
  }, [lectureId, applySynced, pushMoment, setMoments])

  const attachScreenshot = useCallback(async (id, file) => {
    const current = moments.find((m) => m.id === id)
    if (!current) return false
    const target = { ...current, screenshotDataUrl: await downscaleImage(file) }
    setMoments((prev) => prev.map((m) => (m.id === id ? target : m)))
    try {
      applySynced(id, await pushMoment(target))
      return true
    } catch {
      setOnline(false)
      return false
    }
  }, [moments, applySynced, pushMoment, setMoments])

  const toggleResolved = useCallback(async (id) => {
    const current = moments.find((m) => m.id === id)
    if (!current) return
    const resolved = !current.resolved
    setMoments((prev) => prev.map((m) => (m.id === id ? { ...m, resolved } : m)))
    if (!current.synced) return // sent with the moment when it syncs
    try {
      await api(`/lost-moments/${id}`, { method: 'PATCH', body: JSON.stringify({ student_id: getStudentId(), resolved }) })
    } catch {
      setOnline(false)
      setMoments((prev) => prev.map((m) => (m.id === id ? { ...m, resolved: !resolved } : m)))
    }
  }, [moments, setMoments])

  return { moments, online, markLost, attachScreenshot, toggleResolved, sync }
}

export async function fetchHeatmap(lectureId) {
  return api(`/lectures/${encodeURIComponent(lectureId)}/heatmap`)
}
