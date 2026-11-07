# Running Canvas LMS locally

[Canvas LMS](https://github.com/instructure/canvas-lms) is open source under
AGPL-3.0. This runs Instructure's official Docker **development** environment
for local testing. It is not a production deployment.

## One command

From the repository root:

```bash
./scripts/setup-canvas.sh
```

The script is idempotent. It:

1. Installs/starts Docker if needed and handles the `docker` group.
2. Sets SELinux to permissive for this boot if it is enforcing.
3. Adds `127.0.0.1 canvas.docker` to `/etc/hosts` (skip with `CANVAS_ADD_HOSTS=0`).
4. Clones Canvas into `.canvas/canvas-lms` (gitignored).
5. Writes the Docker config and a local override.
6. Builds images, installs gems/JS, compiles assets.
7. Creates and migrates the database.
8. Creates the admin account.
9. Starts Canvas.
10. Creates an admin API token, provisions the `LostPoint` OAuth developer key
    and the demo student, publishes the demo course/modules, and writes the
    values to `backend/.env`.

The first run can take **30–90+ minutes**. Re-running it only starts the
existing install and re-applies the OAuth/demo provisioning.

## Commands

```bash
./scripts/setup-canvas.sh          # install if needed, then start
./scripts/setup-canvas.sh start    # start an existing install
./scripts/setup-canvas.sh stop     # stop Canvas
./scripts/setup-canvas.sh status   # show container status
./scripts/setup-canvas.sh reset    # delete .canvas/ and reinstall (destructive)
```

## Defaults

| Variable | Default |
|---|---|
| `CANVAS_ADMIN_EMAIL` | `admin@lostpoint.local` |
| `CANVAS_ADMIN_PASSWORD` | `lostpoint-canvas` |
| `CANVAS_ACCOUNT_NAME` | `LostPoint` |
| `CANVAS_STUDENT_EMAIL` | `student@lostpoint.local` |
| `CANVAS_STUDENT_PASSWORD` | `lostpoint-student` |
| `CANVAS_HOST_PORT` | `80` |
| `CANVAS_ADD_HOSTS` | `1` |

Override them on the command line:

```bash
CANVAS_ADMIN_EMAIL=me@example.com CANVAS_ADMIN_PASSWORD=secret ./scripts/setup-canvas.sh
```

## Access

- <http://localhost/>
- <http://canvas.docker/>
- Admin login: the credentials printed by the script.
- Demo student: `student@lostpoint.local` / `lostpoint-student` (enrolled in the
  demo course and used by the LostPoint login flow).

## Seed a course with PDF slides

1. Log in as the admin.
2. Open the demo course (id `1`) or **Courses → + Course**.
3. **Modules → + Module**.
4. **Files → Upload** your PDF decks.
5. In a module, **+ → File** and pick the PDF. Repeat per module.
6. If you used a different course, enroll the demo student and publish it:

   ```bash
   python3 backend/scripts/setup_canvas_oauth.py --course <course-id>
   ```

The provisioning script publishes the course and its modules so the student can
see them through the Canvas API.

## LostPoint OAuth and backend

The setup script creates the `LostPoint` developer key, turns on its account
binding, creates the demo student, enrolls the student in the demo course,
publishes the demo course/modules, and writes the settings to `backend/.env`:

```dotenv
CANVAS_BASE_URL=http://localhost
CANVAS_API_TOKEN=...
CANVAS_CLIENT_ID=...
CANVAS_CLIENT_SECRET=...
CANVAS_REDIRECT_URI=http://localhost:5173/api/auth/canvas/callback
FRONTEND_ORIGIN=http://localhost:5173
SESSION_SECRET=...
```

`backend/.env` is gitignored. Re-run provisioning at any time with:

```bash
python3 backend/scripts/setup_canvas_oauth.py
```

Start the backend from `backend/`:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --reload
```

### Login flow

1. `GET /api/auth/canvas/login` redirects the browser to Canvas.
2. The student signs in and authorizes the `LostPoint` app.
3. Canvas redirects to `/api/auth/canvas/callback`; the backend exchanges the
   code for an access token and stores it in SQLite.
4. The browser receives only an HttpOnly, signed `lostpoint_session` cookie.

By default `CANVAS_REDIRECT_URI` points at the Vite dev server, which proxies
`/api` to the backend. For a backend-only test, set it to
`http://localhost:8000/api/auth/canvas/callback`; both URIs are registered on
the developer key.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Service health |
| `GET` | `/api/auth/canvas/login` | Start Canvas OAuth |
| `GET` | `/api/auth/canvas/callback` | OAuth callback |
| `GET` | `/api/auth/me` | Current Canvas user |
| `POST` | `/api/auth/logout` | Revoke the Canvas token and end the session |
| `GET` | `/api/courses` | Active enrolled courses |
| `GET` | `/api/courses/{id}/modules` | Modules with PDF slide items |
| `GET` | `/api/files/{id}/content` | Proxied PDF (`application/pdf`) |

The Canvas access token never reaches the browser. PDFs are proxied through the
backend, so they can be rendered directly in an iframe.

Verify the demo data at any time:

```bash
python3 backend/scripts/inspect_canvas.py
```

If automatic OAuth provisioning could not run (for example, `python3` is
missing), create an API token manually under **Account → Settings → + New Access
Token**, put it in `backend/.env` as `CANVAS_API_TOKEN`, then run
`python3 backend/scripts/setup_canvas_oauth.py`.

## Requirements

- Docker Engine + Docker Compose v2
- 8 GB RAM minimum (16 GB recommended); 4+ CPU cores
- 30 GB free disk (Instructure recommends up to 150 GB)

If Docker is not installed and the script cannot install it automatically,
follow <https://docs.docker.com/engine/install/> and re-run the script.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `permission denied` on Docker socket | `newgrp docker` or log out/in, then re-run |
| SELinux denials in container logs | `sudo setenforce 0`, or add `:z` to bind mounts |
| Build killed / OOM | Close apps; ensure 8 GB+ free RAM |
| `canvas.docker` does not resolve | `echo "127.0.0.1 canvas.docker" \| sudo tee -a /etc/hosts` |
| Port 80 busy | `CANVAS_HOST_PORT=3000 ./scripts/setup-canvas.sh` |
| Long URLs return 502 behind a proxy | Increase proxy buffers |

## Notes

- `.canvas/` is gitignored — never commit the Canvas checkout.
- The installer does not start the `webpack` watcher; start it only if you are
  changing Canvas source/assets: `cd .canvas/canvas-lms && docker compose start webpack`.
- Canvas is heavy. For a quick demo, Canvas Free-for-Teacher is an alternative.
