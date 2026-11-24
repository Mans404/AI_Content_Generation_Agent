# AI Content Generation Agent

A FastAPI backend for creating healthcare social media content from a doctor's profile. It connects structured text generation, image generation, PostgreSQL persistence, image review, and an optional Facebook Page publishing step.

Given a profile and monthly topics, the API generates post ideas, captions, design prompts, and standalone images. A user can regenerate an image with feedback before approving it, then preview a Facebook post locally or request immediate publication or future scheduling through the Graph API.

> **Status: active development.** This repository contains a backend, not a complete publishing platform. This README reflects the source at commit `f5bc22c`, including the Facebook scheduling update. Setup, migrations, and external-service calls have not been verified end to end. Facebook live publishing remains unverified against Meta. Generated health content requires human review before publication.

## Contents

- [Implemented features](#implemented-features)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Local setup](#local-setup)
- [API workflow](#api-workflow)
- [Facebook publishing and scheduling](#facebook-publishing-and-scheduling)
- [Endpoint reference](#endpoint-reference)
- [Data and storage](#data-and-storage)
- [Project structure](#project-structure)
- [Current limitations and next steps](#current-limitations-and-next-steps)

## Implemented features

- **Account authentication:** registration, password login, 30-minute JWT access tokens, and token revocation on logout. Password hashing uses `pwdlib` with Argon2 support.
- **Doctor profiles:** one profile per account, with specialization, language (`AR` or `EN`), audiences, procedures, strengths, posting frequency, and a JPEG profile picture.
- **Monthly inputs:** offers and topics patients find confusing, saved for the current UTC calendar month.
- **Content planning:** structured lists of post ideas and post types, validated against a four-week plan of `posts_per_week × 4` items.
- **Caption generation:** one caption per idea, preserving the idea order.
- **Design prompt generation:** one prompt per idea for a single static image, rather than a carousel or video.
- **Image generation:** bounded parallel generation through OpenRouter, with persisted results and retries for missing indexes.
- **Image review:** regenerate an unapproved image with optional text feedback, then approve it through a separate endpoint.
- **Facebook post preview and submission:** use an approved image and its matching saved caption to create a database-only preview, publish immediately, or submit a future schedule to one server-configured Facebook Page. Live calls are opt-in with `live: true`.
- **Persistence:** SQLAlchemy models and Alembic migrations for accounts, profiles, monthly inputs, content batches, image records, and Facebook scheduling requests. Image files use Supabase Storage.

The prompts request educational, non-diagnostic content and avoid invented credentials, outcomes, and patient stories. These are prompt instructions, not a medical fact-checking system or a guarantee about model output.

## Architecture

```text
API client / Swagger UI
        |
        v
FastAPI + JWT authentication
        |
        +--> Doctor profile + current-month inputs
        |              |
        |              v
        |        Idea planning agent
        |              |
        |              +--> Caption agent --> Captions
        |              |
        |              +--> Design prompt agent
        |                            |
        |                            v
        |                    Image generation service
        |                            |
        |                    Review / regenerate
        |                            |
        |                          Approve
        |                            |
        |                    Facebook post request
        |                            |
        |                  +---------+---------+
        |                  |                   |
        |             Local preview     Graph API submission
        |                               (now / future time)
        |
        +--> PostgreSQL: accounts, inputs, content, images, Facebook request records
        +--> Supabase Storage: profile pictures and generated images
```

Each content stage is triggered by a separate API request. Caption and design prompt generation both depend on the latest saved idea batch, but do not depend on each other. The routed Facebook controller calls Meta directly when `live` is enabled; it does not start a local scheduling worker. A successful future request delegates the schedule to Facebook.

### Model integration

| Stage | Current implementation |
| --- | --- |
| Ideas, captions, design prompts | LangChain `create_agent`, structured Pydantic responses, and `gpt-4o-mini` through OpenRouter |
| Images | Direct HTTP requests to OpenRouter's chat completions endpoint; default model `google/gemini-2.5-flash-image` |
| Occasion context | Upcoming Egyptian holidays from the `holidays` package |

The text model is currently hardcoded in the three text-agent modules. Image model, modalities, and batch concurrency are configurable with environment variables. Provider availability and billing depend on your own account.

## Tech stack

- Python 3.12 (`pyproject.toml` allows `>=3.12,<3.14`)
- FastAPI, Uvicorn, Pydantic
- LangChain and OpenRouter
- SQLAlchemy async sessions, PostgreSQL, Psycopg, Alembic
- Supabase Storage
- HTTPX for direct OpenRouter and Facebook Graph API requests
- PyJWT and `pwdlib`
- `uv` for dependency management, with a committed `uv.lock`

## Local setup

Run the commands below from the repository root unless stated otherwise. They describe the current source layout; they are not a claim of a tested deployment.

### 1. Prerequisites

You need:

- Python 3.12 and `uv`
- A reachable PostgreSQL database and permission to apply schema migrations
- An OpenRouter API key with access to the configured text and image models
- A Supabase project with a Storage bucket named **`doctor-designs`**
- For optional live Facebook requests: a Facebook Page ID and a Page access token accepted by Meta for the requested publishing operation. The API does not provide a Page-connection or OAuth flow.

The current storage service returns **public object URLs**, including URLs for images awaiting approval. Configure the bucket for public reads if using this implementation unchanged. Do not upload patient data or other private material. A `pending/` path is a workflow state, not access control. Keep the Supabase service-role key server-side only.

### 2. Clone and install dependencies

```bash
git clone https://github.com/Mans404/AI_Content_Generation_Agent.git
cd AI_Content_Generation_Agent
uv sync --locked --no-install-project
```

The application runs directly from the repository's `src` package. `--no-install-project` installs the locked dependencies without requiring the repository itself to be installed as a distribution.

### 3. Configure environment variables

Create a new `.env` file in the repository root. Use your own credentials, not values from a sample file:

```dotenv
OPENROUTER_API_KEY=replace-with-your-openrouter-key
JWT_SECRET_KEY=replace-with-a-random-secret-at-least-32-characters-long
JWT_ISSUER=content-generation-api
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=replace-with-your-server-side-service-role-key

# Optional image-generation settings; these are the implementation defaults.
DESIGN_IMAGE_MODEL=google/gemini-2.5-flash-image
DESIGN_IMAGE_MODALITIES=image,text
DESIGN_IMAGE_CONCURRENCY=3

# Optional: required only for live Facebook publication / scheduling.
FACEBOOK_PAGE_ID=replace-with-your-page-id
FACEBOOK_PAGE_ACCESS_TOKEN=replace-with-your-page-access-token
```

| Variable | Purpose |
| --- | --- |
| `OPENROUTER_API_KEY` | Required for text and image generation |
| `JWT_SECRET_KEY` | Required at application import; at least 32 characters |
| `JWT_ISSUER` | Optional token issuer; default `content-generation-api` |
| `SUPABASE_URL` | Required when accessing Supabase Storage |
| `SUPABASE_SERVICE_ROLE_KEY` | Required server-side Storage credential |
| `DESIGN_IMAGE_MODEL` | Optional image-model override |
| `DESIGN_IMAGE_MODALITIES` | Optional comma-separated modalities supported by the selected image model |
| `DESIGN_IMAGE_CONCURRENCY` | Optional integer limit for batch image calls; default `3`, clamped to at least `1` |
| `FACEBOOK_PAGE_ID` | Target Page for every live Facebook request in this deployment |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | Server-side Page access token; required with the Page ID when `live` is `true` |

`MODEL_NAME` and `TAVILY_API_KEY` are not read by the current application source. Setting `MODEL_NAME` does not change the text agents. The routed Facebook controller uses Graph API `v22.0` directly; the `FACEBOOK_GRAPH_VERSION` and `FACEBOOK_TOKEN_KEY` settings referenced in the separate, unwired service module do not configure this endpoint.

Never commit `.env` or credentials. The JWT placeholder above must be replaced with a real random secret, not used as-is.

### 4. Configure the database

```bash
cp src/models/alembic.ini.example src/models/alembic.ini
```

Edit the `[alembic]` section in `src/models/alembic.ini` and set your database connection string:

```ini
[alembic]
# Keep the other settings from the copied template.
sqlalchemy.url = postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE
```

**Important:** both the runtime database module and migrations read this file. A `DATABASE_URL` environment variable alone does not configure the application, despite the wording of the current error message. Keep the local `alembic.ini` private; it is excluded by `src/models/.gitignore`.

Use URL-encoded credentials where required by your database connection string. Preserve the template's migration and logging settings.

### 5. Apply migrations

```bash
uv run --no-sync alembic -c src/models/alembic.ini upgrade head
```

Migrations create the schema; the application does not call `create_all()` on startup. The Supabase Storage bucket must be provisioned separately.

### 6. Start the API

```bash
mkdir -p uploads
uv run --no-sync uvicorn src.main:app --reload
```

For the default local Uvicorn address:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- OpenAPI schema: `http://127.0.0.1:8000/openapi.json`

`--reload` is for local development. The `uploads` directory supports the existing static mount; active profile and generated-image storage uses Supabase.

## API workflow

Use Swagger UI for an interactive walkthrough. Generation endpoints can incur charges on your configured provider account.

### 1. Register or log in

`POST /auth/register` accepts JSON:

```json
{
  "username": "demo_doctor",
  "password": "replace-with-a-unique-demo-password"
}
```

Username length is 3-255 characters; password length is 12-128 characters. Registration returns `access_token` and `token_type`. Existing users can call `POST /auth/login` with form-encoded `username` and `password` fields.

For protected requests, send:

```http
Authorization: Bearer <access_token>
```

In Swagger UI, use **Authorize** to log in. Logout revokes the current token; it does not log out every session for that account.

### 2. Create the doctor profile

`POST /api/v1/companies/` accepts `multipart/form-data`. The route retains the legacy `companies` name, but represents the authenticated user's doctor profile.

| Field | Type and behavior |
| --- | --- |
| `doctor_name` | Required string, 1-200 characters after trimming |
| `doctor_specialization` | Enum value such as `dentistry`, `dermatology`, or `other`; default `other` |
| `yourPicture` | JPEG file, required for initial creation; optional on update; maximum 5 MiB |
| `language` | `AR` or `EN`; default `EN` |
| `audiences` | Repeated form field, up to 20 strings |
| `types_of_medical_procedures` | Repeated form field, up to 20 strings |
| `strengths` | Repeated form field, up to 20 strings |
| `posts_per_week` | Integer from 1 to 21; default `3` |

Profile list items must be 1-500 characters after trimming. The picture validator checks filename extension, declared content type, size, and JPEG boundary signatures. See `src/models/enums.py` or the API schema for all specialization values.

The same endpoint creates or updates the profile. Updates use the supplied values and defaults, so send the complete intended profile rather than treating this as a partial `PATCH`. An omitted picture keeps the existing picture.

The current image-generation request sends a design prompt only. It does not send the uploaded profile picture to the image model.

### 3. Save inputs for the current month

`POST /api/v1/companies/monthly-ideas` accepts JSON:

```json
{
  "doctor_offers": [],
  "advice_and_matters_that_most_people_find_confusing": [
    "How often should adults schedule a routine dental check-up?",
    "What is the difference between plaque and tartar?"
  ]
}
```

Each list allows up to 10 items. A profile must already exist. The endpoint creates or replaces that profile's input lists for the current UTC month; there is no request field for choosing another month.

### 4. Generate the content plan

Call `POST /api/v1/companies/start_planning` with no body.

The response includes the monthly inputs and `agent_output`, containing aligned `ideas` and `post_types` lists. The validated plan contains `posts_per_week × 4` items. This is a four-week content plan, not an exact calendar schedule.

Each call saves a new ideas batch. The caption, design-prompt, and batch-image endpoints operate on the latest batch for the current profile.

### 5. Generate captions and design prompts

Call either or both, with no body:

```http
POST /api/v1/companies/captions
POST /api/v1/companies/design-prompts
```

The responses contain `captions` or `design_prompts`, respectively, with one item per idea in the same order. Results are saved to the ideas batch.

Generate design prompts before images. Avoid generating a new plan or replacing prompts halfway through image review: downstream work is tied to the saved batch and prompt indexes. Replacing prompts deletes approved-image database records for that batch, but does not reset all generation records or remove their storage objects.

### 6. Generate images

Call `POST /api/v1/companies/design-images/generate-all` with no body.

The response has a `generations` list. Each item includes:

- `generation_id`: identifier used for regeneration and approval
- `image_url`: URL to preview the image
- `prompt_index`: zero-based index into the design prompts
- `remaining_prompts`: number of prompt positions after this index, **not** a count of outstanding jobs

The implementation attempts only missing indexes and returns existing results too. A batch can return partial success; compare returned indexes with the design prompt list and retry to request missing images. If no results exist after an attempt, the controller returns `502`.

Keep the returned generation IDs. There is no separate list/status retrieval endpoint in the current router.

### 7. Review, regenerate, and approve

To replace an unapproved image:

```http
POST /api/v1/companies/design-images/{generation_id}/regenerate
Content-Type: application/json
```

```json
{
  "feedback": "Use fewer icons, more whitespace, and a clearer headline area."
}
```

Feedback is optional and limited to 1,000 characters. Regeneration makes a new image request using the original design prompt plus the latest feedback; it is not an image-to-image editing call or a persistent revision conversation. Approved images cannot be regenerated through this endpoint.

To approve an image:

```http
POST /api/v1/companies/design-images/{generation_id}/store
```

Approval moves the object out of `pending/` and saves an approved-image record. Approval alone does not publish anything. Use the separate Facebook endpoint only after reviewing both the image and its saved caption.

## Facebook publishing and scheduling

`POST /api/v1/companies/facebook-posts/schedule` requires bearer authentication and JSON. The generation must belong to the authenticated user's profile, already be approved with `/design-images/{generation_id}/store`, and have a non-empty caption at the same `prompt_index` in its original ideas batch. Generate captions before this step.

### Preview without contacting Facebook

```json
{
  "generation_id": "00000000-0000-0000-0000-000000000001",
  "schedule_for": "now",
  "live": false
}
```

Replace the example UUID with a real `generation_id`. `live` defaults to `false`, and `schedule_for` defaults to `"now"`. Preview mode saves a `facebook_post_schedules` database row with status `preview`, but does not call Facebook, validate Page credentials, render a Facebook preview, or queue a later post. It does not require Facebook environment variables.

### Publish now or request a future schedule

After reviewing the content, set `live` to `true` to request immediate publication:

```json
{
  "generation_id": "00000000-0000-0000-0000-000000000001",
  "schedule_for": "now",
  "live": true
}
```

To request future scheduling, replace `"now"` with an ISO 8601 datetime at least 10 minutes and at most 75 days after the request time. For example, `"2026-12-01T10:00:00Z"` illustrates the format only; choose a valid future time when making the request.

- Include `Z` or an explicit UTC offset. Offset-aware values are converted to UTC; naive datetimes are treated as UTC, not local time.
- The optional datetime field `scheduled_for` is also accepted and takes precedence over `schedule_for` when provided. Prefer `schedule_for` and do not send both.
- Time-window validation also applies to preview requests with a future datetime.
- Live mode reads `FACEBOOK_PAGE_ID` and `FACEBOOK_PAGE_ACCESS_TOKEN` from the server environment. Every user of the deployment targets that same Page; there is no per-user Page mapping in the active route.
- The controller sends the approved image URL and matching caption to Graph API `v22.0` at `/{page_id}/photos`. It uses `published=true` for immediate requests, or `published=false` plus a Unix `scheduled_publish_time` for future requests.

The response includes `schedule_id`, `generation_id`, `image_url`, `caption`, `scheduled_for`, `live`, `status`, and nullable `facebook_post_id`. The controller records `published` for a successful immediate Graph response or `scheduled` for a successful future Graph response. These are submission results, not independent confirmation of later delivery. Meta can reject requests based on token permissions, Page configuration, image accessibility, or platform rules; the backend's local time check does not guarantee Meta acceptance.

| Condition | Current response |
| --- | --- |
| Missing profile, owned generation, stored image/content batch, or matching caption | `404` |
| Design not approved | `409` |
| Empty caption or datetime outside the local scheduling window | `422` |
| Live mode without Page ID or token | `500` |
| Facebook returns an HTTP error | `502`, with Facebook error details |

**Operational limits:** repeated requests create separate records and may create duplicate live posts. There is no idempotency key, schedule list/status endpoint, cancel endpoint, or webhook reconciliation. The Graph call occurs before the database commit, so Facebook may accept a post even if saving its local record subsequently fails. Verify the Page before retrying an uncertain live request. Preview records do not automatically become live requests.

The separate `src/services/facebook.py` and `src/services/publisher.py` files are unfinished worker scaffolding, not the active endpoint path. They reference model names absent from the current ORM (`FacebookPageModel`, `ScheduledPostModel`, and `ScheduledPostStatus`), have incompatible publisher call signatures, and are not started by `src/main.py`. Do not run or describe them as a working retry worker without completing that integration.

## Endpoint reference

All business routes require bearer authentication. No route below is implied to be a background task.

| Method | Path | Request | Purpose |
| --- | --- | --- | --- |
| `POST` | `/auth/register` | JSON | Create an account and return a token |
| `POST` | `/auth/login` | Form | Authenticate and return a token |
| `POST` | `/auth/logout` | No body; bearer token | Revoke the current token |
| `POST` | `/api/v1/companies/` | Multipart form | Create or update the doctor profile |
| `POST` | `/api/v1/companies/monthly-ideas` | JSON | Save current-month inputs |
| `POST` | `/api/v1/companies/start_planning` | No body | Generate and save ideas/post types |
| `POST` | `/api/v1/companies/captions` | No body | Generate and save captions |
| `POST` | `/api/v1/companies/design-prompts` | No body | Generate and save design prompts |
| `POST` | `/api/v1/companies/design-images/generate-all` | No body | Generate missing images in the latest batch |
| `POST` | `/api/v1/companies/design-images/{generation_id}/regenerate` | Optional JSON | Regenerate an unapproved image |
| `POST` | `/api/v1/companies/design-images/{generation_id}/store` | No body | Approve an image |
| `POST` | `/api/v1/companies/facebook-posts/schedule` | JSON: `generation_id`, optional `schedule_for` / `scheduled_for`, `live` | Save a preview or submit an approved image and matching caption to Facebook |

Use the generated OpenAPI schema for response details and validation rules.

## Data and storage

The main database entities are:

- `users` and `revoked_tokens`: credentials and revoked access-token identifiers
- `companies`: doctor profiles, retaining the earlier table name
- `monthly_ideas`: one input record per profile and UTC month
- `ideas`: generated idea batches, including post types, captions, and design prompts
- `design_image_generations`: generated candidates with a `stored` approval flag
- `design_images`: approved-image records
- `facebook_post_schedules`: snapshots of requested captions, image URLs, target times, local statuses, and Facebook IDs when returned; migration `c4d5e6f7a8b9` adds this table

The two image tables enforce uniqueness on `(ideas_id, prompt_index)`. Image controllers also use in-process locks and compensating cleanup for some storage/database failures. These mechanisms do not establish exactly-once execution across workers or eliminate duplicate paid provider calls.

Profile pictures and generated images share the `doctor-designs` bucket. API authentication does not make the returned public Storage URLs private.

## Project structure

```text
src/
├── main.py                    # FastAPI entry point and router assembly
├── agents/                    # Ideas, captions, design prompts, image generation
├── routes/                    # HTTP endpoints
├── controllers/               # Profile, content, image review, Facebook submission
├── database/                  # Async SQLAlchemy engine/session configuration
├── jwt/                       # Authentication and token revocation
├── models/
│   ├── companies.py           # ORM entities
│   ├── enums.py               # Language and specialization values
│   ├── alembic/               # Migration environment and version history
│   └── alembic.ini.example     # Local database configuration template
├── schemas/                   # Request, response, and structured AI output models
├── prompts/                   # Text prompt templates
├── prompt_loader.py           # Template loading and formatting
└── services/                  # Storage, holiday context, unfinished publisher modules
tests/
└── test_agent.ipynb            # Exploratory notebook, not an automated test suite
pyproject.toml
uv.lock
```

## Current limitations and next steps

This is a work-in-progress backend. It now includes a direct Facebook publishing/scheduling request path, but does not include a frontend, Page OAuth connection flow, per-user Page configuration, working local publisher worker, Docker configuration, CI workflow, or an automated test suite. Live Facebook behavior has not been verified end to end.

Priorities for further development:

- [ ] Add automated tests for authentication, ownership boundaries, validation, migrations, and the complete content-to-approval flow.
- [ ] Test Facebook preview, time-window validation, Page/token failures, duplicate requests, and database failures after Graph acceptance without publishing real content.
- [ ] Validate live publishing and future scheduling against the target Page; add per-user Page authorization, idempotency, schedule retrieval/cancellation, and delivery reconciliation before shared deployment.
- [ ] Complete or remove the unwired Facebook service and worker scaffolding so it matches the active models and publisher interface.
- [ ] Mock provider and storage failures to test partial batches, retries, concurrent requests, and cleanup.
- [ ] Add measurable evaluations for medical-content safety, relevance, caption quality, and image/prompt alignment.
- [ ] Centralize text-model configuration and remove unused dependencies and legacy naming.
- [ ] Add retrieval/status endpoints for saved content and image review, plus a defined policy for replacing batches and prompts.
- [ ] Add bounded lock lifecycle, distributed coordination where needed, request limits, and provider retry/timeout policies.
- [ ] Review storage privacy, orphan cleanup, and expired-token cleanup before deployment.
- [ ] Add deployment configuration, health checks, and operational monitoring.

A `thread_id` is passed to the text agents, but no checkpointer is configured, so persistent conversational memory is not implemented. The idea validator currently truncates excess output to the requested count and rejects shorter output. Neither behavior replaces output-quality evaluation.

Use this project as a development backend and a demonstration of an integrated AI content workflow, not as an unattended medical publishing system.
