# GROUP 6 — Issue Tracker with Kanban Board

**Stack:** Flask · React (Vite) · MongoDB + PyMongo · JWT · Docker Compose  
**Team size:** 3  |  **Duration:** 7 days

## Team Members

| # | Name | GitHub username |
| --- | --- | --- |
| 1 | Sorav |  |
| 2 | Satrajeet Kumar |  |
| 3 | Rishu Kumar |  |

## Project Description

A lightweight Jira: projects hold issues that move through a defined workflow on a drag-and-drop board, with comments, mentions and a complete activity trail of every field change.

## Roles

| Role | Responsibility |
| --- | --- |
| Admin | Creates projects, manages all members and workflow configuration. |
| Project Member | Creates and works on issues in projects they belong to. |
| Reporter | Raises issues and comments, but cannot move or assign them. |

## Data Model

- **users** - credentials, role, display name, avatar colour.
- **projects** - key, name, description, owner, embedded members array with per-project role.
- **issues** - project_id, key (PROJ-14), title, description, type (bug / task / story), priority, state, assignee, reporter, labels, due date, embedded comments array, embedded activity array.
- **labels** - project_id, name, colour.

## Features

- Project CRUD with member invite and per-project role.
- Issue create and edit: type, priority, assignee, labels, due date, description.
- Kanban board with drag and drop across columns (Backlog, To Do, In Progress, In Review, Done).
- Comments with @mention of a project member.
- Filter bar: assignee, label, priority, type and full-text search on title/description.
- Per-project activity feed and a personal "My issues" view.
- Issue counts per state for a simple project health strip.

## Core Technical Challenge

**A real state machine plus an immutable activity trail.** Allowed transitions are declared in configuration; an illegal jump (Backlog straight to Done) is rejected with 422, not silently accepted. Only the assignee, the project owner or an admin may move an issue, and only a member of that project may see it. Every change - state, assignee, priority, labels - appends an entry (field, old value, new value, actor, timestamp) that can never be edited or deleted, and the drag on the board is reverted in React if the API rejects the move.

## React Screens

- Board with drag-and-drop columns and compact issue cards.
- Issue detail drawer: fields, comment thread, activity timeline.
- Filter bar with active-filter chips.
- Project settings and member management.
- My issues list.

## Authentication Specification

- Passwords hashed with bcrypt - plain text passwords must never touch the database.
- Endpoints: `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `GET /auth/me`.
- The access token carries a `role` claim; a custom decorator `@role_required("admin")` guards privileged routes on top of `@jwt_required()`.
- Refresh rotation: a refresh call issues a new access token; logout adds the token JTI to a blocklist so it cannot be reused.
- React side: Axios request interceptor attaches the token, response interceptor catches 401, calls refresh once, retries the original request, and logs the user out if refresh also fails.
- Route protection in React by role - a seeker must never be able to open an admin screen, even by typing the URL.

## Docker Specification

- `backend/Dockerfile` - Python slim base, requirements installed first for layer caching, served by `gunicorn` (not the Flask dev server).
- `frontend/Dockerfile` - multi-stage: Node stage runs `npm run build`, nginx stage serves the static build and proxies `/api` to the backend.
- `docker-compose.yml` - services `api`, `web`, `db` on one network, a named volume for database data, a healthcheck on `db`, and `depends_on` so the API waits for it.
- All secrets (DB URL, JWT secret key) come from `.env`; `.env.example` is committed, `.env` is not.
- Acceptance test: on a clean machine, `git clone` then `docker compose up --build` gives a working app with seeded demo data.

## Execution Plan

### Phase 1 - Day 1: Foundation

- Finalise the data model and draw the ER diagram / collection diagram before writing code.
- Repo and folder structure: `backend/`, `frontend/`, `docker-compose.yml`, `README.md`.
- Docker skeleton up early - database container running and reachable from the API container on day one.
- User model + full JWT auth flow + role seeding. Do not move on until login and refresh work in Postman.

### Phase 2 - Day 2 to 3: Core API

- Every core CRUD endpoint with request validation and clear error responses (400 / 401 / 403 / 404 / 409).
- Role guards on every write route; ownership checks so a user can only touch their own records.
- Pagination, filtering and sorting on all list endpoints - never return the whole table.
- Test every endpoint in Postman and save the collection before you write a single React component.

### Phase 3 - Day 3 to 5: React Application

- Routing, auth context, protected route wrapper, login and register screens.
- List, detail and create/edit screens for the main entities with client-side form validation.
- Loading, empty and error states on every screen - no blank page while data is fetching.
- Shared Axios instance; no API URL hardcoded in components.

### Phase 4 - Day 5 to 6: Core Business Logic

- Implement the core rule described above - this is what separates this project from a CRUD demo.
- Dashboard and aggregation endpoints computed in the database layer, not in JavaScript.
- Search and filters wired end to end.

### Phase 5 - Day 6 to 8: Harden and Ship

- Full dockerization verified from a clean clone; fix anything that only worked on your laptop.
- Seed script that creates demo users for each role plus realistic sample data.
- README: architecture overview, setup steps, environment variables, API endpoint table, demo credentials.
- Postman collection, bug fixing pass, and a 5-minute demo recording walking through each role.

## Suggested Work Split

| Owner | Suggested responsibility |
| --- | --- |
| Member 1 | Auth, roles, projects, members, labels. |
| Member 2 | Issues, workflow state machine, comments, mentions, activity trail, search. |
| Member 3 | React board, drag-and-drop, issue drawer, filters. |

---

## Contribution Log — to be filled in by the team

> Fill this in yourselves before submission. Be specific: name the modules, endpoints, components or files you actually built. One line per item.

| Member | Modules / features built | Files or folders owned | Approx. commits |
| --- | --- | --- | --- |
| Sorav |  |  |  |
| Satrajeet Kumar |  |  |  |
| Rishu Kumar |  |  |  |

### Individual summaries

**Sorav**

- What I built: 
- What I found hardest: 
- What I would do differently: 

**Satrajeet Kumar**

- What I built: 
- What I found hardest: 
- What I would do differently: 

**Rishu Kumar**

- What I built: 
- What I found hardest: 
- What I would do differently: 

### Shared / pair work

- 
- 

### Declaration

We confirm the above split is accurate and every member contributed code to this repository.

| Member | Signature / date |
| --- | --- |
| Sorav |  |
| Satrajeet Kumar |  |
| Rishu Kumar |  |

---

## Deliverables Checklist

- [ ] GitHub repository containing both applications with a readable commit history from every member.
- [ ] README.md with setup instructions, environment variables and an API endpoint table.
- [ ] ER diagram (SQL) or collection diagram (MongoDB).
- [ ] Seed script with demo data and demo credentials per role.
- [ ] Postman collection covering every endpoint.
- [ ] Working `docker compose up --build` on a clean machine.
- [ ] 5-minute demo video.

## Evaluation

| Area | Weight | What is checked |
| --- | --- | --- |
| Functionality | 30% | All listed features work end to end without manual database edits |
| API design & JWT | 20% | Correct status codes, validation, role guards, refresh and blocklist working |
| Core business logic | 20% | The project-specific core rule is correctly and safely implemented |
| React frontend | 15% | Component structure, state handling, validation, loading and error states |
| Docker & docs | 15% | One-command startup, clean compose file, complete README and seed data |

## Setup

```bash
git clone <repo-url>
cd <repo>
cp .env.example .env
docker compose up --build
```

| Service | URL |
| --- | --- |
| Frontend | http://localhost:3000 |
| API | http://localhost:5000/api |

**Demo credentials:** _(fill in after seeding)_
