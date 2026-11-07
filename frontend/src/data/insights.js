import { fetchHeatmap, fetchLecture } from './api'
import { loadLibrary } from './modules'

// The sample is only shown when no uploaded lecture is available, and is labelled as such.
const sample = {
  id: 'sample', title: 'Introduction to Calculus (sample data)', totalPages: 3, source: 'Sample data',
  slides: [{ number: 1, count: 3 }, { number: 2, count: 8 }, { number: 3, count: 8 }],
}

// Lectures this browser uploaded that the server has read.
export async function listInsightLectures() {
  const state = await loadLibrary()
  const modules = new Map(state.modules.map(item => [item.id, item.name]))
  return state.lectures.filter(item => item.serverId).map(item => ({ id: item.serverId, title: item.title, moduleName: modules.get(item.moduleId) || 'Module' }))
}

// Real, anonymised counts from the server: distinct students per slide, hidden under 5.
export async function loadLectureInsights(serverId) {
  if (!serverId) return { ...sample, slides: sample.slides.map(slide => ({ ...slide })) }
  const [heat, lecture] = await Promise.all([fetchHeatmap(serverId), fetchLecture(serverId)])
  const totalPages = lecture.slides.length
  const bySlide = new Map(heat.slides.map(slide => [slide.slide_number, slide]))
  const slides = Array.from({ length: totalPages }, (_, index) => {
    const row = bySlide.get(index + 1)
    return { number: index + 1, count: row ? (row.hidden ? null : row.students) : 0, title: lecture.slides[index]?.title }
  })
  return { id: serverId, title: lecture.title, totalPages, source: 'Live data', minStudents: heat.min_students, mostLost: heat.most_lost_slide, slides }
}
