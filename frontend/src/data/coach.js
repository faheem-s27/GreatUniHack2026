import { askCoach } from './api'
import { forgetServerCopy, transaction } from './modules'

// Ask the coach about a Lost Point and keep the conversation on this device.
// The coach reads the lecture's slides on the server; the API key never reaches the browser.
export async function sendCoachMessage({ pointId, chatId, moduleId, lectureId, messageId, text, page, serverLectureId }) {
  const content = text.trim()
  if (!content) throw new Error('Type a question first.')
  if (!serverLectureId) throw new Error('The coach can’t read this PDF yet. Open My Modules and choose “Let the coach read it”.')

  const existing = await transaction(state => {
    const point = state.lostPoints?.find(item => item.id === pointId && item.chatId === chatId && item.moduleId === moduleId && item.lectureId === lectureId)
    if (!point) throw new Error('This Lost Point could not be found. Go back to Lost Moments and try again.')
    return state.pointChats?.[chatId] || []
  })
  if (existing.some(item => item.id === messageId)) return [...existing]

  let reply
  try {
    reply = await askCoach({ lectureId: serverLectureId, slideNumber: page, message: content })
  } catch (error) {
    if (error.status === 404) {
      await forgetServerCopy(lectureId)
      const lost = new Error('The server no longer has these slides (it may have been reset). Choose “Let the coach read it” to send the PDF again, then ask once more.')
      lost.lectureMissing = true
      throw lost
    }
    throw error
  }
  const time = new Date().toISOString()
  return transaction(state => {
    const chats = state.pointChats ||= {}
    const messages = chats[chatId] ||= []
    if (!messages.some(item => item.id === messageId)) {
      messages.push(
        { id: messageId, from: 'you', text: content, time },
        { id: `${messageId}-coach`, from: 'coach', text: reply.response, time, mode: reply.mode, citations: reply.citations,
          source: reply.source, provider: reply.provider, wrongAttempts: reply.wrong_attempts, gapClosed: reply.gap_closed },
      )
    }
    return [...messages]
  })
}
