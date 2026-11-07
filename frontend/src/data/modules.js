// Explicit local demo adapter. No module/upload API exists in the backend yet.
export const dataMode = 'local-demo'
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
export async function saveLecture(moduleId, title, file) {
  if (!file || !/\.pdf$/i.test(file.name) || (file.type && file.type !== 'application/pdf')) throw new Error('Choose a PDF file.')
  if (!file.size || !(await file.slice(0, 1024).text()).includes('%PDF-')) throw new Error('This file does not contain a valid PDF header. Choose another PDF.')
  if (!title.trim()) throw new Error('Enter a lecture title.')
  return transaction(state => {
    if (!state.modules.some(item => item.id === moduleId)) throw new Error('Module no longer exists. Reload and retry.')
    const lecture = { id: crypto.randomUUID(), moduleId, title: title.trim(), fileName: file.name, size: file.size, addedAt: new Date().toISOString(), blob: file }
    state.lectures.push(lecture)
    return lecture
  })
}
