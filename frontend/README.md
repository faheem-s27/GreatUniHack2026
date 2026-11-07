# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.

## My Modules (local demo)

The current backend exposes only `/api/health`. `src/data/modules.js` explicitly
uses `local-demo` mode; it makes no module/upload API requests and never falls
back from a failed server request to simulated success. All library reads and
writes go through this adapter. IndexedDB stores metadata and PDF Blobs together;
PDFs are not encoded into localStorage. The three sample modules are seeded only
when the library has not yet been initialized. Data belongs to this browser and
origin and may be removed by clearing site data. Storage errors are shown with
retry actions or by keeping the entered name/file available for resubmission.

The default view is My Modules. Select a module to show its slides and upload
area. One saved PDF creates one new lecture record; repeated uploads append and
do not replace earlier lectures. Open lecture passes moduleId, lectureId, and a
Blob resource URL into the application's shared active-lecture state. Live
Lecture uses a bundled PDF.js reader with page counts and page navigation. AI
parsing is not implemented. The original calculus demo remains under “View sample lecture” when
no PDF is active. Existing coach, moments, and insights views remain demos.

### Backend integration to confirm with the team

No new API endpoints or backend fields have been approved or implemented.
The adapter's **local-only** records currently contain:

- Module: `id`, `name`.
- Lecture: `id`, `moduleId`, `title`, `fileName`, `size`, `addedAt`, `blob`.
- Active frontend context adds `lectureId`, `moduleName`, and an object `url`.

Confirm the real list/create module operations, duplicate-name semantics,
lecture/PDF relationship, upload mechanism, resource authentication/expiry, and
actual page-count/processing fields before replacing this adapter. Map the
confirmed backend fields here rather than changing backend contracts in UI code.

Run `npm ci`, then `npm run dev` and open the URL reported on your own machine.
`npm run build` and `npm run lint` validate the existing project configuration.

## Live Lecture

PDF.js (`pdfjs-dist` pinned to 5.4.624) now renders one PDF page at a time in a
worker, with previous/next controls and validated page-number navigation. Its
worker and renderer are bundled locally; no PDF is sent to a CDN or server.
The original module/PDF IndexedDB records and IDs are retained.

`src/data/lecture.js` centralizes local subtitle sessions, Lost Points and chat
notes, using the existing IndexedDB transaction adapter. New local-only fields
are `subtitleSessions`, `lostPoints`, and `pointChats`; these are not approved
backend contracts. Lost Points save moduleId, lectureId, viewing page, timestamp,
chatId, selected caption time and a snapshot of the preceding subtitle context.
Each Lost Point has its own persisted note thread. Existing sample moments and
sample coach interactions remain separate.

No recording, speech recognition, translation, teacher page sync or AI coaching
API currently exists. Start recording requires the permission-confirmation
checkbox, then requests microphone permission. If access is granted, tracks are
immediately released and the missing-service connection error is shown. Audio
is not recorded, stored or sent. Only an explicitly enabled and started subtitle
demo generates preset fictional bilingual captions, every four seconds. They do
not describe or parse the uploaded PDF. Language selection changes which preset
translation is emphasized. A demo session continues in Coach and other views
until Stop; opening a different PDF is blocked until the session ends.

Subtitle page associations use the student's viewed PDF page at capture time,
including the fixed context page when in Coach. They never claim to know the
teacher's page. Selecting history does not auto-scroll or auto-follow incoming
captions; Back to live selects the newest session/caption. Saved sessions can be
selected again after reload; recording never resumes automatically. PDF files,
Lost Points, notes and subtitles remain only in the current browser/origin and
can be lost when browser site data is cleared. A failed Lost Point save keeps
its original context and ID for retry rather than claiming success.

## Lost Moments

Lost Moments reads the same persisted Lost Points created in Live Lecture. It
adds module, dependent lecture/PDF and status filters, newest-first ordering,
student self-marked Understood/Reopen actions, and inline save/retry errors.
The unresolved count is derived from the shared points only after successful
writes. Understood records remain stored and explorable. Each Explore reuses the
original chatId, PDF and context without resetting messages. The list remains
mounted during navigation to retain filters and restore its scroll position.
Small filter preferences are saved in localStorage; PDF Blobs and all learning
records stay in IndexedDB. No server success or AI mastery is claimed.

The My Modules course section includes a View lost moments entry that explicitly
selects that module and clears the lecture filter. Global navigation keeps the
last filter selection. Missing PDF resources show a precise message and a
My Modules recovery entry instead of opening another document. Empty libraries,
empty filter results, read failures and status-save failures have distinct UI.

## My Coach

My Coach lists conversations by shared modules and opens each Lost Point's
existing chatId. The chat displays the corresponding PDF beside messages on
desktop, or above a collapsible chat resource area on phones. Messages support
multiline input, IME-safe Enter, Shift+Enter, local persistence and idempotent
retry. Understood/Reopen uses the existing shared state. Navigation back to
Lost Moments, the original lecture/page, and course conversation lists keeps
existing records and the active subtitle session.

This iteration is an explicit simple local demo: AI chat and teaching modes
are not connected. It adds no PDF text extraction, AI source generation,
teaching assessment, audio capability or backend API. Messages remain in the
existing IndexedDB pointChats store and no server success is claimed.
