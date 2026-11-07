import { saveLostMoment, setLostMomentResolved } from './api'
import { loadLibrary, transaction } from './modules'
// Lost Points and coach conversations are kept in this browser. Each Lost Point
// is also sent to the server (page number only), which counts them for the
// lecturer heatmap. Live captions come from the captions socket and are never stored.

export async function loadLectureData() {
  const state = await loadLibrary()
  return { sessions: state.subtitleSessions || [], points: state.lostPoints || [], chats: state.pointChats || {}, modules: state.modules, lectures: state.lectures.map(({ id, moduleId, title, blob, serverId }) => ({ id, moduleId, title, available: !!blob, serverId })) }
}
export async function saveLostPoint(point) {
  const saved = await transaction(state => {
    const items = state.lostPoints ||= []
    const existing = items.find(item => item.id === point.id)
    if (existing) return existing
    items.unshift(point)
    state.pointChats ||= {}
    state.pointChats[point.chatId] = []
    return point
  })
  // Count it for the lecturer heatmap. A failure here never loses the Lost Point.
  if (point.serverLectureId) saveLostMoment({ id: point.id, lectureId: point.serverLectureId, slideNumber: point.page, topic: point.lectureTitle }).catch(() => {})
  return saved
}
export async function updatePoint(point) {
  await transaction(state => {
    const index = (state.lostPoints || []).findIndex(item => item.id === point.id)
    if (index < 0) throw new Error('This Lost Point was not found. Reload the page and try again.')
    state.lostPoints[index] = point
  })
  if (point.serverLectureId) setLostMomentResolved(point.id, point.resolved).catch(() => {})
}
export const saveChat = (id, messages) => transaction(state => { state.pointChats ||= {}; state.pointChats[id] = messages })
export async function findLecture(moduleId, lectureId) {
  const state = await loadLibrary()
  const lecture = state.lectures.find(item => item.id === lectureId && item.moduleId === moduleId)
  if (!lecture?.blob) throw new Error('This PDF is no longer on this device. Upload it again in My Modules.')
  return { ...lecture, lectureId, moduleName: state.modules.find(item => item.id === moduleId)?.name || 'Module' }
}
export function readMomentFilters() {
  try {
    const saved = JSON.parse(localStorage.getItem('lostpoint-moment-filters') || '{}')
    return { moduleId: typeof saved.moduleId === 'string' ? saved.moduleId : '', lectureId: typeof saved.lectureId === 'string' ? saved.lectureId : '', status: ['all', 'review', 'understood'].includes(saved.status) ? saved.status : 'all' }
  } catch { return { moduleId: '', lectureId: '', status: 'all' } }
}
export async function rememberMomentFilters(filters) {
  localStorage.setItem('lostpoint-moment-filters', JSON.stringify(filters))
}

