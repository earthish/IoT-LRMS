# IoT Lab Resource Management System (IoT-LRMS)

Web app for the IoT lab at XIM University. Students log in with their university Google account, browse lab instruments, request to issue them (needs approval), and book time slots for shared resources such as the 3D printer. Lab staff and faculty approve requests and manage inventory. An "Oracle" feature suggests project ideas based on the components currently available.

This is a university deliverable. The developer must be able to explain every part of the code. Prefer clear, simple code over clever code, and add short comments where the logic is not obvious (especially auth and booking conflicts).

## Stack

- Backend: Django
- Database: PostgreSQL (SQLite is acceptable for early local dev only)
- Auth: `django-allauth` with the Google provider
- Frontend: **Django templates + Tailwind**, server-rendered. Views query the database directly and render HTML — there is no separate frontend project and no API layer for the core flow (auth, inventory, issue requests, bookings). Django admin is used as the staff/faculty approval interface initially.
- Django REST Framework is installed but used **only** for isolated features that need async JSON calls from a template via `fetch()` — currently just the Oracle endpoint (see below). Do not build DRF serializers/viewsets for inventory, issue requests, bookings, or users. Those are plain Django views returning rendered templates.
- QR codes: `qrcode` (Python)
- Config: environment variables via `python-decouple` or `django-environ`
- Oracle LLM: a fast, lightweight model behind a small provider wrapper (see below)

### Why templates, not an API-consuming frontend
This project has no separate client app (no mobile app, no SPA) right now. A full API layer (serializers, viewsets, a separate frontend fetching and re-rendering JSON) adds a layer of indirection with no payoff here, and is harder for a teammate with no frontend-framework experience to work on. Django's own request → view → template → response cycle is simpler to build, debug, and explain. If an Android app or SPA is ever built later, the DRF layer can be added incrementally app-by-app at that point — it does not need to be designed in now.

## Project layout

```
iot_lrms/               # project settings
users/                  # custom user model, roles, Google auth hooks
inventory/              # Instrument model, categories, QR generation
issue_requests/         # IssueRequest workflow (request -> approve -> return)
bookings/               # Slot booking for shared resources, conflict prevention
notifications/          # email (and optional in-app) alerts
oracle/                 # LLM-powered project idea suggestions
dashboard/              # utilization and admin analytics
```

Build one app at a time in this order: `users` -> `inventory` -> `issue_requests` -> `bookings` -> `notifications` -> `oracle` -> `dashboard`. Stop after each app so the developer can review the diff, run it, and commit.

## Authentication rules (security critical)

- Only accounts with an email on exactly `xim.edu.in` (employees) or `stu.xim.edu.in` (students) may sign in. Everyone else is rejected, including lookalikes such as `notxim.edu.in`, `xim.edu.in.evil.com` and other subdomains.
- Enforce this **server-side**. Passing the `hd` hosted-domain parameter to Google is only a UX hint and can be bypassed, so it is not sufficient on its own. Implement a custom allauth adapter (`DefaultSocialAccountAdapter` / `DefaultAccountAdapter`) that checks the email domain and that the email is verified, and rejects sign-in and sign-up otherwise.
- Disable local username/password signup. Google is the only login method. A superuser created with `createsuperuser` is fine for initial admin access.
- Never trust role or domain information sent from the frontend. Derive it from the authenticated user on the server.
- Google client ID/secret, Django `SECRET_KEY`, DB credentials, and LLM API keys come from environment variables. Never commit them. Provide a `.env.example` with placeholder values and keep `.env` in `.gitignore`.

## Roles and permissions

Use a custom user model from the very first migration (`AUTH_USER_MODEL = "users.User"`), with a `role` field:

- `student`: browse instruments, create issue requests, book slots, view own history
- `lab_assistant`: everything a student can do, plus approve/reject requests and mark instruments returned or under maintenance
- `faculty`: everything a lab assistant can do, plus manage inventory, view the dashboard, and export reports

Enforce permissions in the Django views themselves (e.g. a `role_required` decorator or mixin checked at the top of each view) — not only by hiding buttons in the template. New users default to `student`. Only a superuser or faculty can change roles (via Django admin).

## Data model

```
User
  email (unique), name, role, department, roll_number (nullable)

Instrument
  name, category, description, image, datasheet (optional file),
  status: available | in_use | maintenance | reserved
  is_bookable (bool)   # true for shared resources like the 3D printer -> use bookings
  quantity_total, quantity_available   # for components with multiple units
  qr_code (generated)

IssueRequest            # one request = a basket of one or more instruments
  user -> User, purpose, course_or_project (optional),
  duration_days (set by the student, max 30; due_at = issued_at + duration_days),
  status: pending | approved | rejected | issued | returned
  requested_at, reviewed_by -> User (nullable), reviewed_at,
  issued_at, due_at, returned_at,
  condition_on_issue, condition_on_return

IssueRequestItem        # one line per instrument in the request
  request -> IssueRequest, instrument -> Instrument, quantity (>= 1)

Booking
  resource -> Instrument (is_bookable=True), user -> User,
  start_time, end_time, status: confirmed | cancelled | completed | no_show

UsageLog
  user, instrument, action (requested | approved | rejected | issued | returned | booked | cancelled), timestamp, note

OracleSuggestion
  requested_by -> User, available_components (text snapshot), user_context (optional),
  suggestion_text, created_at
```

## Key logic requirements

**Booking conflict prevention.** Two bookings for the same resource must never overlap. Enforce this at the database level, not just in Python, to avoid race conditions when two students book at once. Use PostgreSQL with `django.contrib.postgres.constraints.ExclusionConstraint` on the resource and the time range (`RangeOperators.OVERLAPS`, ignoring cancelled bookings). Also validate in the serializer so users get a clear error message. Enforce `end_time > start_time` and no bookings in the past.

**Issue request workflow.**
1. Student adds available instruments to a basket (kept in the session), then submits it as one request (`pending`). A submitted request cannot be edited; forgotten items go in a new request. A student may have only one open (pending or approved) request per instrument.
2. Lab assistant or faculty approves or rejects the whole request (record who and when). Approving does not reserve stock.
3. On issue, decrement availability for every item, set `due_at`, record condition notes. All or nothing: if any item has too few units left, nothing changes.
4. On return, increment availability, record return condition.
5. Every transition writes a `UsageLog` entry per item and triggers a notification (notifications are wired in when the `notifications` app is built).
6. Wrap state changes that touch quantity in `transaction.atomic()` with `select_for_update()` so two approvals cannot over-issue the same item.

**Notifications.** Send an email on request approved, request rejected, and an upcoming due date. Keep the sending logic in `notifications/` so it can be swapped out later.

## Oracle feature

A "monk/Socrates" style persona that suggests what can be built with the components currently available.

- This is the one place DRF is used. Endpoint: `POST /api/oracle/suggest/` (authenticated, session-based). Optional body field `context` (one line from the student, max 200 characters). Called from a template via `fetch()` so the suggestion can appear without a full page reload.
- Query instruments with `status="available"` (and `quantity_available > 0`), build a compact comma-separated list, and send it to the LLM.
- Put the LLM call in `oracle/llm.py` behind a single function, e.g. `generate_suggestion(system_prompt, user_prompt) -> str`. Read the provider, model name, and API key from environment variables so the provider can be changed without touching the views.
- System prompt: a calm, slightly cryptic lab monk. Suggest 2-3 project ideas buildable this week using only the listed components. 2-3 sentences each, practical and specific. The tone carries the personality; the technical content must stay accurate and must not assume components that are not in the list.
- Treat the student's `context` text as untrusted input. Keep it in the user message only, never in the system prompt.
- Rate-limit per user (for example 5 requests per hour) using DRF throttling, and cache results briefly per unique inventory state.
- Set a request timeout. On any failure, return a friendly fallback message ("The Oracle is meditating. Try again shortly.") with a 200 status and log the error server-side.
- Save each suggestion to `OracleSuggestion`.

## API conventions (Oracle only)

- Lives under `/api/oracle/`, JSON only, session auth via allauth. No other app should add `/api/` endpoints unless a real second client (mobile app, SPA) is actually being built.
- Everywhere else: plain Django views, `select_related` / `prefetch_related` on queries that list or join, and Django's built-in `Paginator` for long lists rendered in templates.

## Code conventions

- Python 3.9 (the current venv). Keep code 3.9-compatible: no `match` statements and no `X | Y` type-hint syntax. Follow PEP 8, format with `black`, sort imports with `isort`.
- Small focused functions; put business logic (approval, booking, availability) in a `services.py` per app rather than inside views.
- Every app gets tests in `tests.py` or `tests/`. At minimum cover: non-`xim.edu.in` login rejected, role permissions, overlapping booking rejected, approval/return updates availability correctly, Oracle fallback on LLM failure.
- Migrations are committed. Never edit an applied migration; add a new one.
- Register all models in Django admin with useful `list_display`, `list_filter`, and `search_fields`. Admin actions for approving/rejecting requests are welcome.

## Model to use in Claude Code

Default to Sonnet for implementation work (apps, serializers, views, migrations, tests) — it's faster, cheaper, and handles well-defined Django work fine. Switch to Opus only for: the Google auth adapter (security-sensitive, worth the extra scrutiny), the booking overlap/race-condition logic in `bookings`, and any case where Sonnet's output is wrong after a couple of attempts. Switch back to Sonnet afterward.

## How to work with me

- Before writing code for a new app, show a short plan and wait for approval.
- Make small, reviewable changes. After each app, list the files changed, how to run it, and how to test it.
- Ask when a requirement is ambiguous instead of guessing.
- Do not add features, dependencies, or refactors that were not requested.
- If something in this file conflicts with what would be simpler or safer, say so and explain why before deviating.

## Out of scope for now

Mobile app, real-time WebSockets, penalty/priority scoring, consumables stock alerts, and PDF/Excel export are planned later. Do not build them unless asked.
