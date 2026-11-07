// Modules and lecture PDFs are kept in this browser (IndexedDB) so they open
// instantly and work offline. Each PDF is also sent to the server, which reads
// its text so the coach can search it and cite its slides.
import { fetchLibraryLecture, uploadLecturePdf } from './api'

let database
function db() {
  if (!database) database = new Promise((resolve, reject) => {
    const request = indexedDB.open('lostpoint-library', 1)
    request.onupgradeneeded = () => request.result.createObjectStore('library')
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => { database = null; reject(new Error('Device storage is unavailable. Please enable browser storage and retry.')) }
  }).catch(error => { database = null; throw error })
  return database
}
export async function transaction(update) {
  const database = await db()
  return new Promise((resolve, reject) => {
    const tx = database.transaction('library', 'readwrite')
    const store = tx.objectStore('library')
    let result
    const request = store.get('state')
    request.onsuccess = () => {
      try {
        const state = request.result || { modules: ['Symbolic AI', 'Data Engineering', 'Uncertainty'].map(name => ({ id: crypto.randomUUID(), name })), lectures: [] }
        result = update(state)
        store.put(state, 'state')
      } catch (error) { reject(error); tx.abort() }
    }
    tx.oncomplete = () => resolve(result)
    tx.onerror = () => reject(new Error('Could not save on this device. Check available storage and retry.'))
  })
}
export const loadLibrary = () => transaction(state => state)
export const createModule = (name) => transaction(state => {
  name = name.trim()
  if (!name) throw new Error('Enter a module name.')
  if (state.modules.some(item => item.name.toLowerCase() === name.toLowerCase())) throw new Error('A module with this name already exists.')
  const module = { id: crypto.randomUUID(), name }
  state.modules.push(module)
  return module
})
export async function saveLecture(moduleId, title, file, { assessed = false } = {}) {
  if (!file || !/\.pdf$/i.test(file.name) || (file.type && file.type !== 'application/pdf')) throw new Error('Choose a PDF file.')
  if (!file.size || !(await file.slice(0, 1024).text()).includes('%PDF-')) throw new Error('This file does not contain a valid PDF header. Choose another PDF.')
  if (!title.trim()) throw new Error('Enter a lecture title.')
  return transaction(state => {
    if (!state.modules.some(item => item.id === moduleId)) throw new Error('Module no longer exists. Reload and retry.')
    const lecture = { id: crypto.randomUUID(), moduleId, title: title.trim(), fileName: file.name, size: file.size, addedAt: new Date().toISOString(), blob: file, assessed }
    state.lectures.push(lecture)
    return lecture
  }).then(lecture => connectLecture(lecture.id))
}

// Check the server still has this lecture's slides. If the server was reset,
// forget the old id so "Let the coach read it" can send the PDF again.
// Network errors leave the lecture as it is.
export async function checkLecture(lectureId) {
  const state = await loadLibrary()
  const lecture = state.lectures.find(item => item.id === lectureId)
  if (!lecture?.serverId) return lecture
  try {
    await fetchLibraryLecture(lecture.serverId)
    return lecture
  } catch (error) {
    if (error.status !== 404) return lecture
  }
  return forgetServerCopy(lectureId)
}

export const forgetServerCopy = lectureId => transaction(state => {
  const item = state.lectures.find(value => value.id === lectureId)
  if (item) { item.serverId = null; item.serverError = 'The server no longer has these slides.' }
  return item
})

// Send a saved PDF to the server so the coach can read it. Safe to retry.
export async function connectLecture(lectureId) {
  const state = await loadLibrary()
  const lecture = state.lectures.find(item => item.id === lectureId)
  if (!lecture?.blob) throw new Error('This PDF is no longer on this device. Upload it again.')
  if (lecture.serverId) return lecture
  const module = state.modules.find(item => item.id === lecture.moduleId)
  let update
  try {
    const result = await uploadLecturePdf({ moduleId: lecture.moduleId, moduleName: module?.name || 'Module', title: lecture.title, file: lecture.blob, assessed: !!lecture.assessed })
    update = { serverId: result.lecture_id, readableSlides: result.slides_with_text, serverError: null }
  } catch (error) {
    update = { serverError: error.message }
  }
  return transaction(next => {
    const item = next.lectures.find(value => value.id === lectureId)
    if (item) Object.assign(item, update)
    return item
  })
}
