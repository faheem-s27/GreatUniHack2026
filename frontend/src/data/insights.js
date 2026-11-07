// One explicit demo lecturer assignment: the existing three-slide calculus demo.
// No statistics endpoint is defined by the backend; no student data is read.
const assignment = {
  lectureId: 'sample-introduction-to-calculus',
  title: 'Introduction to Calculus',
  totalPages: 3,
  source: 'Sample data',
  slides: [{ number: 1, count: 3 }, { number: 2, count: 8 }, { number: 3, count: 8 }],
}
export async function loadLectureInsights() {
  return { ...assignment, slides: assignment.slides.map(slide => ({ ...slide })) }
}
