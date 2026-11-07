import { transaction } from './modules'
// Explicit local demo. No chat, teaching-mode or citation API is configured.
export async function sendCoachMessage({ pointId, chatId, moduleId, lectureId, messageId, text, page, pageText, resourceTitle, resourceLectureId = lectureId }) {
  const content = text.trim()
  if (!content) throw new Error('Enter a question before sending.')
  const excerpt = pageText?.replace(/\s+/g, ' ').trim().slice(0, 220)
  const reference = excerpt ? { moduleId, lectureId: resourceLectureId, page, title: resourceTitle, excerpt, source: 'local-pdf-text' } : null
  let prompt
  if (/why|为什么|pourquoi/i.test(content)) prompt = 'Which step is unclear, and what assumption might that step depend on?'
  else if (/example|例子|示例/i.test(content)) prompt = 'Try a small example of the term on this page. What changes if you alter one input?'
  else if (/compar|difference|区别|比较/i.test(content)) prompt = 'Name the two ideas you want to compare. Which words on this page describe each one?'
  else if (/summary|summari|总结|重点/i.test(content)) prompt = 'Choose a term from this page and write a one-sentence explanation. What needs clarification?'
  else prompt = 'Which word or step on this page is confusing? Describe what you already understand about it.'
  const reply = excerpt ? `Demo study prompt for “${resourceTitle}”, page ${page}. Locally extracted text: “${excerpt}”. ${prompt} This is a preset prompt, not an AI interpretation of your PDF.` : `PDF text is unavailable for page ${page}. I cannot give a page-grounded answer. Describe the relevant text or formula in your question. ${prompt} This is a preset demo prompt, not an AI answer.`
  return transaction(state => {
    const point = state.lostPoints?.find(item => item.id === pointId && item.chatId === chatId && item.moduleId === moduleId && item.lectureId === lectureId)
    if (!point) throw new Error('The original Lost Point could not be loaded. Return to Lost Moments and retry.')
    if (!state.lectures.some(item => item.id === lectureId && item.moduleId === moduleId && item.blob)) throw new Error('The original PDF is unavailable. Check the slides in My Modules and retry.')
    if (reference && !state.lectures.some(item => item.id === resourceLectureId && item.moduleId === moduleId && item.blob)) throw new Error('The referenced PDF is unavailable in this module.')
    const chats = state.pointChats ||= {}
    const messages = chats[chatId] ||= []
    if (messages.some(item => item.id === messageId)) return [...messages]
    const historical = point.context?.at(-1)
    const historicalNote = historical ? ` Saved Lost Point subtitle at ${historical.time} (not the latest live caption): “${historical.original}”.` : ''
    const time = new Date().toISOString()
    // Commit the user message and reply atomically; retries reuse messageId.
    messages.push({ id: messageId, from: 'you', text: content, time }, { id: `${messageId}-demo`, from: 'coach', text: reply + historicalNote, time, mode: null, reference, source: 'local-demo' })
    return [...messages]
  })
}
