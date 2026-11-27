# AI Content Generation Agent

A FastAPI backend that creates healthcare social media content from a doctor's profile: post ideas, captions, design prompts and images. Generated posts can go to a Telegram review step, and only an explicit approval publishes them to a Facebook page. An optional "autopilot" runs the whole pipeline for a set of client-chosen post times.

> **Status: active development.** This is a backend only (no frontend yet). The sections below are written from the source code in this repository. Items marked *not verified* were read from the code but not exercised against a real database or real external services. Generated health content needs human review before it is published.

## Contents

- [Safety: what can publish and what cannot](#safety-what-can-publish-and-what-cannot)
- [Features](#features)
- [Pipeline](#pipeline)
- [Tech stack](#tech-stack)
- [Local setup](#local-setup)
- [Environment variables](#environment-variables)
- [Running the processes](#running-the-processes)
- [API reference](#api-reference)
- [Autopilot](#autopilot)
- [Telegram review and approval](#telegram-review-and-approval)
- [Data and storage](#data-and-storage)
- [Project structure](#project-structure)
- [Checks and tests](#checks-and-tests)
- [Known limitations](#known-limitations)

## Safety: what can publish and what cannot

Nothing publishes to Facebook unless you turn it on. These are the only code paths that can post:

1. **Review worker publisher.** Runs only when `REVIEW_FLOW_ENABLED=true` and `REVIEW_PUBLISH_ENABLED=true` are both set in the process that runs `python -m src.review_worker`. It publishes reviews whose status is `approved` to the page in `FACEBOOK_PAGE_ID`, right away, whatever their scheduled time. Pressing **Approve** only marks the review `approved`. The post goes out when a worker with publish enabled runs, which can be later.
2. **`POST /api/v1/companies/facebook-posts/schedule` with `"scheduled_for": "now"` and `"live": true`.** This posts to the page directly. Be careful: if `scheduled_for` is omitted it defaults to `"now"`. With `live` false (the default) it only creates a preview record. With `live` true and a future time (at least 10 minutes, at most 75 days ahead) it creates an `awaiting_review` record and publishes nothing.
3. The **autopilot worker never publishes.** It schedules every post with `live=true` and a future time, so posts only reach Telegram review.

Other safety notes:

- `AUTOPILOT_ENABLED` and the `REVIEW_*` flags are off unless set to exactly `true`. Setting them in a single terminal session (not in `.env`) keeps them temporary.
- Keep `REVIEW_REGENERATE_ENABLED` off unless you accept that pressing **Reject** in Telegram makes a new paid image.
- Before turning publishing on, confirm that `FACEBOOK_PAGE_ID` is the page you intend. `TELEGRAM_REVIEW_PAGE_ID` must equal it, otherwise the review worker refuses to start publishing.
- Never commit `.env`, `src/models/alembic.ini` or any token. Use placeholders in `.env.example`. A token that has been shared anywhere should be rotated.

## Features

- **Authentication:** registration, password login, 30-minute JWT access tokens, token revocation on logout.
- **Doctor profile:** one per account (route name `companies` is a legacy name).
- **Monthly inputs:** offers and confusing topics for the current UTC month.
- **Content planning:** ideas and post types, `posts_per_week x 4` items.
- **Captions and design prompts:** one per idea, in the same order.
- **Image generation:** through OpenRouter, saved as candidates, with optional `limit=N` for the first N prompts.
- **Image review:** regenerate with feedback, then approve (store).
- **Facebook scheduling:** preview, review-gated schedule, or direct post (see Safety).
- **Telegram review flow:** due posts are sent to Telegram with Approve and Reject buttons.
- **Autopilot:** one run generates and schedules up to 10 posts for client-chosen times, with a monthly image budget.

## Pipeline

```text
login -> company profile -> monthly inputs
   -> start_planning (ideas) -> captions + design-prompts
   -> design-images/generate-all -> (regenerate) -> store (approve)
   -> facebook-posts/schedule (live=true, future time)
   -> awaiting_review row -> review worker sends it to Telegram at the due time
   -> Approve -> publisher (only if enabled) posts to the Facebook page
```

Each manual stage is its own API request. Autopilot runs the same steps from one request (see [Autopilot](#autopilot)).

## Tech stack

Python 3.12, FastAPI and Uvicorn, LangChain (text agents through OpenRouter), OpenRouter (images), SQLAlchemy async with PostgreSQL (psycopg), Alembic, Supabase Storage, PyJWT and pwdlib, httpx, `uv` with a committed `uv.lock`.

## Local setup

```bash
git clone https://github.com/Mans404/AI_Content_Generation_Agent.git
cd AI_Content_Generation_Agent
uv sync --locked --no-install-project
```

1. **Database URL.** Copy `src/models/alembic.ini.example` to `src/models/alembic.ini` and set `sqlalchemy.url` (for example `postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE`). The app and the migrations both read this file. A `DATABASE_URL` variable alone does not configure the app.
2. **Environment.** Create `.env` in the repository root (see below).
3. **Migrations:**
   ```bash
   uv run --no-sync alembic -c src/models/alembic.ini upgrade head
   ```
   The newest migration adds the autopilot tables (`a1b2c3d4e5f6`).
4. **Storage.** Create a Supabase Storage bucket named `doctor-designs`. The code returns public object URLs, so the bucket must allow public reads. Do not upload private data.
5. **Uploads folder** (the app mounts it at start): `mkdir -p uploads`.

## Environment variables

Put these in `.env` (read with `python-dotenv`). Values below are placeholders.

| Variable | Needed for |
| --- | --- |
| `OPENROUTER_API_KEY` | Text and image generation |
| `JWT_SECRET_KEY` | Required at import, at least 32 characters |
| `JWT_ISSUER` | Optional, default `content-generation-api` |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Storage (server side only) |
| `DESIGN_IMAGE_MODEL`, `DESIGN_IMAGE_MODALITIES`, `DESIGN_IMAGE_CONCURRENCY` | Optional image settings (defaults in the code) |
| `FACEBOOK_PAGE_ID`, `FACEBOOK_PAGE_ACCESS_TOKEN` | Facebook posting (direct post route and the review publisher) |
| `FACEBOOK_GRAPH_VERSION` | Optional, default `v22.0` |
| `CORS_ORIGINS` | Comma-separated allowed browser origins. Default `http://localhost:5173,http://127.0.0.1:5173`. Setting it replaces the default list. No wildcard, credentials off |
| `AUTOPILOT_ENABLED` | `true` lets `python -m src.autopilot_worker` run. Anything else makes it log and exit |
| `REVIEW_FLOW_ENABLED` | `true` starts the Telegram sender and callback poller in the review worker |
| `REVIEW_PUBLISH_ENABLED` | With the flow flag, also starts the publisher loop. Needs `FACEBOOK_PAGE_ID`, `FACEBOOK_PAGE_ACCESS_TOKEN`, `TELEGRAM_REVIEW_PAGE_ID` |
| `REVIEW_REGENERATE_ENABLED` | With the flow flag, also starts the regenerate loop for rejected posts (paid images, needs `OPENROUTER_API_KEY`) |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_REVIEWER_USER_ID` | Telegram bot, the one chat, and the one allowed reviewer (integer id) |
| `TELEGRAM_REVIEW_OWNER_ID` | UUID of the app user whose reviews are handled |
| `TELEGRAM_REVIEW_PAGE_ID` | Must equal `FACEBOOK_PAGE_ID` when publishing is enabled |

`MODEL_NAME` and `TAVILY_API_KEY` appear in `.env.example` but are not read by the application source. `src/services/facebook.py` reads `FACEBOOK_TOKEN_KEY` when imported, but nothing in `src` imports that module.

## Running the processes

Run each one in its own terminal, from the repository root with the virtual environment active. Only one copy of each worker should run.

```bash
# 1. API
uvicorn src.main:app --reload

# 2. Telegram review worker (needs REVIEW_FLOW_ENABLED=true; add REVIEW_PUBLISH_ENABLED=true only when you want publishing)
python -m src.review_worker

# 3. Autopilot worker (needs AUTOPILOT_ENABLED=true, otherwise it logs and exits)
python -m src.autopilot_worker
```

Setting a flag for one terminal only (PowerShell):

```powershell
$env:REVIEW_FLOW_ENABLED = "true"
$env:REVIEW_PUBLISH_ENABLED = "false"
$env:REVIEW_REGENERATE_ENABLED = "false"
python -m src.review_worker
```

Stop a worker with Ctrl+C, then clear the variables (`Remove-Item Env:NAME`) or close the terminal.

- Swagger UI: `http://127.0.0.1:8000/docs`
- The review worker does not need the API to be running, only the database and Telegram.
- On Windows the workers switch to the selector event loop themselves (needed by the async database driver).

## API reference

All routes need `Authorization: Bearer <token>` except register and login. Business routes are under `/api/v1/companies`.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/auth/register` | Create an account, returns a token |
| POST | `/auth/login` | Form fields `username`, `password`, returns a token |
| POST | `/auth/logout` | Revoke the current token |
| POST | `/api/v1/companies/` | Create or update the doctor profile (multipart) |
| POST | `/api/v1/companies/monthly-ideas` | Save the current month's inputs |
| POST | `/api/v1/companies/start_planning` | Generate ideas and post types |
| POST | `/api/v1/companies/captions` | Generate captions |
| POST | `/api/v1/companies/design-prompts` | Generate design prompts |
| POST | `/api/v1/companies/design-images/generate-all` | Generate missing images (paid) |
| POST | `/api/v1/companies/design-images/{generation_id}/regenerate` | Regenerate one image (paid) |
| POST | `/api/v1/companies/design-images/{generation_id}/store` | Approve (store) an image |
| POST | `/api/v1/companies/facebook-posts/schedule` | Preview, review-gated schedule, or direct post (see Safety) |
| POST | `/api/v1/companies/autopilot/runs/dry-run` | Validate times and budget, writes nothing |
| POST | `/api/v1/companies/autopilot/runs` | Queue a run (202) |
| GET | `/api/v1/companies/autopilot/runs` | List your runs, newest first (`limit` 1 to 50, default 20) |
| GET | `/api/v1/companies/autopilot/runs/{run_id}` | Run status with posts, image URL, caption, review status, budget |
| POST | `/api/v1/companies/autopilot/runs/{run_id}/cancel` | Cancel a queued or parked run |
| POST | `/api/v1/companies/autopilot/runs/{run_id}/posts/{position}/reschedule` | New time for an expired post |

Use the generated OpenAPI schema (`/docs`) for request and response details. Profile and generation details are the same as before: the profile accepts a JPEG up to 5 MiB, `posts_per_week` 1 to 21, language `AR` or `EN`.

## Autopilot

One run generates content and schedules posts for the times the client chooses. Creating a run only queues it and pays nothing. Work starts only when the autopilot worker is running with `AUTOPILOT_ENABLED=true`.

**Request.** `POST /autopilot/runs` with `{"scheduled_for": ["2026-12-01T10:00:00Z", ...], "idempotency_key": "..."}`.

- 1 to 10 times, each with a timezone, from 12 minutes to 30 days ahead, no duplicates.
- One active run per account. A second request returns 409 with the active `run_id`.
- The same key with the same times returns the same run (`created: false`). The same key with different times returns 409.
- Budget: 10 initial images per month. Over budget returns 409.
- Use `/dry-run` first to check the same rules without writing anything.

**Worker steps** (in order): plan ideas, design prompts, captions, images (only as many as posts), store, then schedule each post with `live=true` and its future time. Posts end in Telegram review. The worker never publishes.

**Status values.** Run: `queued`, `running`, `completed`, `partial`, `failed`, `needs_attention`, `cancelled`. A run found `running` when the worker starts is moved to `needs_attention`, because a paid step may have happened. It is not retried.

**Cancel** works for `queued` and `needs_attention` runs and releases the unused reservation. A `running` run returns 409.

**Reschedule** works for a post whose time passed while images were generating (`slot_expired`), once the run has finished. The image already exists, so it costs nothing. The run's own status is not recomputed afterwards.

**Not built:** a resume action for `needs_attention` runs, counting manual regenerations against the monthly budget, a retry on Telegram rate limits (429).

## Telegram review and approval

1. A scheduled post (`awaiting_review`) becomes a pending review. At its scheduled time the review worker's sender posts the image and caption to the configured chat with Approve and Reject buttons.
2. Only the configured chat and the configured reviewer id can press the buttons. A button on an older message is refused.
3. **Approve** marks the review `approved`. **Reject** marks it `rejected`.
4. With publishing enabled, the publisher claims `approved` reviews and posts the photo and caption to the page. Outcomes: `published`, `failed` (Facebook refused), or `needs_attention` (uncertain result, never retried automatically because a duplicate is possible).
5. With regeneration enabled, a rejected review gets a new image (at most 3 regenerations per image) and goes back to the queue.

## Data and storage

Main tables: `users`, `revoked_tokens`, `companies`, `monthly_ideas`, `ideas`, `design_image_generations`, `design_images`, `facebook_post_schedules`, `telegram_post_reviews`, and the autopilot tables (runs, run posts, image ledger). The application does not create tables at startup, use Alembic. Images and profile pictures share the `doctor-designs` bucket and are served through public URLs.

## Project structure

```text
src/
  main.py                 FastAPI app, CORS, routers
  autopilot_worker.py     autopilot process (python -m src.autopilot_worker)
  review_worker.py        review process (python -m src.review_worker)
  review_runtime.py       review flags and config validation
  agents/                 ideas, captions, prompts, image generation
  controllers/            profile, content, images, facebook, autopilot
  routes/                 profile, content, images, autopilot, companies assembly
  services/               storage, telegram_*, review_*, autopilot_state, autopilot_runner
  jwt/                    authentication
  models/                 ORM models, enums, Alembic
  schemas/                request and response models
  prompts/                prompt templates
tests/test_agent.ipynb    exploratory notebook only
```

## Checks and tests

The repository has no automated API test suite. Two small checks that do not need the network can be run from the project root (they are scripts you create, not files in the repo): a scan for undefined names across `src`, and an import of every module in `src`. The first would have caught a missing `or_` import in `src/controllers/facebook.py`, which only failed when scheduling ran. Adding real tests (including the original flow) is still open.

## Known limitations

- No frontend yet. CORS is configured for a local dev origin.
- No automated tests. The autopilot logic was tested outside the repo with fakes and an in-memory database. Postgres lock behaviour and the real controllers inside the autopilot worker are covered only by one real two-post run.
- The monthly image budget does not include manual regenerations.
- Manual `generate-all` and `regenerate` calls are not tied to the autopilot budget.
- Public storage URLs for images, including images not yet approved.
- A task or worker crash can leave paid images that are not recorded. Such runs are parked (`needs_attention`) and need a human decision.

Use this project as a development backend and a human-reviewed workflow, not as an unattended medical publishing system.
