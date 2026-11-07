// Everything the frontend asks the LostPoint backend. In development Vite
// proxies /api to FastAPI; in production both are served from the same origin.

const STUDENT_KEY = 'lostpoint-student-id'

// No accounts for students yet: a random id kept in this browser.
export function getStudentId() {
  try {
    let id = localStorage.getItem(STUDENT_KEY)
    if (!id) { id = crypto.randomUUID(); localStorage.setItem(STUDENT_KEY, id) }
    return id
  } catch {
    return 'anonymous'
  }
}

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`/api${path}`, options)
  } catch {
    throw new Error('Can’t reach the LostPoint server. Check that the backend is running, then try again.')
  }
  if (!response.ok) {
    let detail = ''
    try { detail = (await response.json()).detail } catch { /* not JSON */ }
    const error = new Error(detail || `The server answered ${response.status}.`)
    error.status = response.status
    throw error
  }
  return response.status === 204 ? null : response.json()
}

const json = (method, body) => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

// Send a PDF to the server so the coach can read and search it.
export function uploadLecturePdf({ moduleId, moduleName, title, file, assessed = false }) {
  const params = new URLSearchParams({ student_id: getStudentId(), module_id: moduleId, module_name: moduleName, title, assessed: String(assessed) })
  return request(`/library/lectures?${params}`, { method: 'POST', headers: { 'Content-Type': 'application/pdf' }, body: file })
}

// Ask the coach about a page of a lecture. Without a lectureId it uses the built-in demo slides.
export function askCoach({ lectureId, slideNumber, message, concept }) {
  return request('/coach', json('POST', {
    student_id: getStudentId(),
    ...(lectureId ? { lecture_id: lectureId } : {}),
    slide_number: slideNumber,
    message,
    ...(concept ? { concept } : {}),
  }))
}

// Lost moments on the server feed the lecturer heatmap (counts only, 5+ students).
export function saveLostMoment({ id, lectureId, slideNumber, topic }) {
  return request('/lost-moments', json('POST', { id, student_id: getStudentId(), lecture_id: lectureId, slide_number: slideNumber, topic: topic?.slice(0, 200) || null }))
}

export function setLostMomentResolved(id, resolved) {
  return request(`/lost-moments/${encodeURIComponent(id)}`, json('PATCH', { student_id: getStudentId(), resolved }))
}

export const fetchHeatmap = lectureId => request(`/lectures/${encodeURIComponent(lectureId)}/heatmap`)
export const fetchLecture = lectureId => request(`/lectures/${encodeURIComponent(lectureId)}`)

// Whether the server still has a PDF this browser uploaded (it may have been reset since).
export const fetchLibraryLecture = serverId => request(`/library/lectures/${encodeURIComponent(serverId)}?student_id=${encodeURIComponent(getStudentId())}`)
