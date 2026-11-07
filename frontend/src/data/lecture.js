import { loadLibrary, transaction } from './modules'
// Local browser records only. No speech/translation/chat API is defined yet.
export const languages = { zh: '中文', en: 'English', es: 'Español', fr: 'Français' }
const lines = [
  { en: 'Let us look at the main idea on this page.', zh: '我们来看这一页的主要概念。', es: 'Veamos la idea principal de esta página.', fr: 'Examinons l’idée principale de cette page.' },
  { en: 'Which part of this example needs a closer look?', zh: '这个例子的哪一部分需要进一步说明？', es: '¿Qué parte del ejemplo necesita más explicación?', fr: 'Quelle partie de cet exemple faut-il approfondir ?' },
  { en: 'Take a moment to connect this idea to the previous example.', zh: '花一点时间，将这个概念与前一个例子联系起来。', es: 'Relaciona esta idea con el ejemplo anterior.', fr: 'Reliez cette idée à l’exemple précédent.' },
]
export const demoCaption = index => lines[index % lines.length]
export async function loadLectureData() {
  const state = await loadLibrary()
  return { sessions: state.subtitleSessions || [], points: state.lostPoints || [], chats: state.pointChats || {}, modules: state.modules, lectures: state.lectures.map(({ id, moduleId, title, blob }) => ({ id, moduleId, title, available: !!blob })) }
}
export const saveSession = session => transaction(state => {
  const items = state.subtitleSessions ||= []
  const index = items.findIndex(item => item.id === session.id)
  if (index < 0) items.push(session)
  else items[index] = session
  return session
})
export const saveLostPoint = point => transaction(state => {
  const items = state.lostPoints ||= []
  const existing = items.find(item => item.id === point.id)
  if (existing) return existing
  items.unshift(point)
  state.pointChats ||= {}
  state.pointChats[point.chatId] = []
  return point
})
export const updatePoint = point => transaction(state => {
  const index = (state.lostPoints || []).findIndex(item => item.id === point.id)
  if (index < 0) throw new Error('Lost Point was not found. Reload and retry.')
  state.lostPoints[index] = point
})
export const saveChat = (id, messages) => transaction(state => { state.pointChats ||= {}; state.pointChats[id] = messages })
export async function findLecture(moduleId, lectureId) {
  const state = await loadLibrary()
  const lecture = state.lectures.find(item => item.id === lectureId && item.moduleId === moduleId)
  if (!lecture?.blob) throw new Error('PDF unavailable on this device. Return to My Modules and select it again.')
  return { ...lecture, lectureId, moduleName: state.modules.find(item => item.id === moduleId)?.name || 'Module' }
}
export async function requestRecording() {
  if (!navigator.mediaDevices?.getUserMedia) throw new Error('Microphone unavailable. Use HTTPS and a supported browser.')
  let stream
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }) }
  catch (error) {
    throw new Error(error.name === 'NotAllowedError' ? 'Microphone permission denied. Allow microphone access in browser settings and retry.' : 'Microphone unavailable. Check your device and retry.', { cause: error })
  }
  stream.getTracks().forEach(track => track.stop())
  throw new Error('Connection failed: no speech or translation service is configured. Microphone released; no audio was saved or sent. You can explicitly enable subtitle demo instead.')
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

