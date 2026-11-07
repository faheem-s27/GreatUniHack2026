import { transaction } from './modules'
// Simple, explicit local demo. No AI request or PDF text extraction is performed.
export async function sendCoachMessage({ pointId, chatId, moduleId, lectureId, messageId, text, page, resourceTitle }) {
  const content = text.trim()
  if (!content) throw new Error('Enter a question before sending.')
  return transaction(state => {
    const point = state.lostPoints?.find(item => item.id === pointId && item.chatId === chatId && item.moduleId === moduleId && item.lectureId === lectureId)
    if (!point) throw new Error('The original Lost Point could not be loaded. Return to Lost Moments and retry.')
    if (!state.lectures.some(item => item.id === lectureId && item.moduleId === moduleId && item.blob)) throw new Error('The original PDF is unavailable. Check the slides in My Modules and retry.')
    const chats = state.pointChats ||= {}
    const messages = chats[chatId] ||= []
    if (messages.some(item => item.id === messageId)) return [...messages]
    const time = new Date().toISOString()
    const reply = `Demo coach — AI not connected. Your question about “${resourceTitle}”, page ${page}, is saved on this device. I cannot read this PDF or generate an AI answer. You can describe the specific step or idea here to continue this demo conversation.`
    messages.push({ id: messageId, from: 'you', text: content, time }, { id: `${messageId}-demo`, from: 'coach', text: reply, time, source: 'local-demo' })
    return [...messages]
  })
}
