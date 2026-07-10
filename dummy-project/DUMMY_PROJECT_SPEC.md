# ChatDock — Dummy Target Project Specification

Build a small but production-shaped messaging app. It exists to be a
realistic target for an autonomous agent factory, mirroring a real codebase:
Gradle/Spring Boot backend, Next.js/TypeScript frontend, Postgres in its own
container, docker-compose, real CI. Working code with tests beats fancy
features — keep every part boring and conventional.

## Functional requirements

1. **Accounts — deliberately simple** (no JWT, no email verification, no
   password reset; those arrive later as agent-factory tasks):
   - Create account: email + password + confirm password. Validate the two
     passwords match and the email isn't taken. Display name = the part of
     the email before the @.
   - Log in: email + password. Session = a plain httpOnly session cookie
     (Spring's standard session handling — nothing fancy).
   - Passwords hashed with BCrypt (basic hygiene, still simple).
   - Seed 3 demo users (alice@demo.io, bob@demo.io, carol@demo.io —
     password `demo1234`) via Flyway migration or startup seeder.
2. **User list**: after login, show all other users, ordered by most recent
   conversation first.
3. **Direct messages**: click a user → conversation view → send messages.
   Poll every 3 seconds for new messages (NO websockets — keep it simple).
   Show sender, text, timestamp. Unread count per user in the list.

## Architecture — must follow exactly

```
chatdock/
├── docker-compose.yml        # 3 services: db, backend, frontend
├── CLAUDE.md                 # root: architecture, commands, conventions
├── backend/                  # Spring Boot 3, Java 17, Gradle
│   ├── CLAUDE.md             # how to build/test backend, layer rules
│   └── src/main/java/...     # controller → service → repository layers
│       # entities: User, Message; DTOs separate from entities
│       # endpoints: POST /api/accounts (create), POST /api/auth/login,
│       #   POST /api/auth/logout, GET /api/users, GET /api/me,
│       #   GET /api/messages/{userId}, POST /api/messages/{userId}
│       # GET /actuator/health enabled
├── frontend/                 # Next.js 14+, TypeScript, App Router
│   ├── CLAUDE.md             # how to build/lint, component conventions
│   └── app/                  # pages: /login, /register, /chat
│       # plain fetch() to the backend, Tailwind for styling, no state lib
└── .github/workflows/ci.yml  # see CI section
```

- **db**: `postgres:16-alpine`, named volume, healthcheck; backend waits for
  it (depends_on with condition).
- **backend**: built from `backend/Dockerfile` (multi-stage Gradle build),
  port 8080, config via env vars (`SPRING_DATASOURCE_URL` etc.).
  Schema managed by Flyway migrations.
- **frontend**: built from `frontend/Dockerfile`, port 3000, proxies
  `/api/*` to the backend service (Next.js rewrites).
- `docker compose up -d --build` from the repo root must bring up the whole
  app at http://localhost:3000 with zero manual steps.

## Tests — non-negotiable

- **Backend**: JUnit 5. Unit tests for services (account creation rules,
  message send/list, unread counts) + MockMvc tests for every controller
  endpoint (happy path + one failure case each: password mismatch, duplicate
  email, bad credentials, unauthenticated access, messaging a nonexistent
  user). Use H2 or Testcontainers so
  `./gradlew test` works without docker-compose running.
- **Frontend**: `tsc --noEmit` and ESLint must pass; add a couple of unit
  tests for utility/format functions (vitest or jest).

## CI — .github/workflows/ci.yml

Two parallel jobs, triggered on pull_request and push to main:
- `backend`: JDK 17 → `./gradlew build test`
- `frontend`: Node 20 → `npm ci && npx tsc --noEmit && npm run lint && npm run build`

Both must pass green on the initial commit.

## CLAUDE.md files — write them for future AI agents

Root CLAUDE.md: what the app is, service layout, how to run everything
(compose + per-module test commands), cross-cutting conventions (DTOs at the
boundary, no entity leaks, where auth lives). Module CLAUDE.md files: build/
test commands for that module, layer rules, one worked example of "how to
add an endpoint" / "how to add a page". These files are the primary
interface future agents will use — be concrete, include real commands.

## Definition of done

- `docker compose up -d --build` → create a new account (email + password
  twice), log in as alice@demo.io, see other users, exchange messages
  between two browser sessions.
- `./gradlew test` green from `backend/`, lint+tsc+build green from `frontend/`.
- CI workflow green.
- All CLAUDE.md files written.

Deliberately left out (future agent-factory tasks — do NOT implement):
email verification on signup, email invites, password reset, JWT/hardened
auth, group chats, websockets/live updates, message search, profile
avatars, typing indicators.
