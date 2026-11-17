# AI Content Generation Workflow

FastAPI service for creating an authenticated Doctor profile and generating a
monthly social-media content plan. The service generates content ideas, design
prompts, captions, and images through OpenRouter, then stores profile and
generated-content data in PostgreSQL and Supabase Storage. Generated images go
through a human review step before they are stored permanently.

## Features

- JWT registration, login, and logout with per-user ownership checks.
- Create or update one Doctor profile per authenticated user.
- JPG/JPEG profile-picture validation, size limits, and Supabase Storage upload.
- Monthly Doctor offers and confusing matters as inputs to the planning agent.
- Structured content ideas and post types based on the requested posts per week.
- Design prompts and captions generated from the latest ideas batch.
- Batch image generation: all missing designs are generated in parallel (bounded
  concurrency), and a single failure never discards the successful images.
- Human-in-the-loop review: list the current state of every design, approve
  (store) designs, or regenerate individual designs with optional feedback.
- Retry-safe generation: calling the batch endpoint again only generates the
  missing designs and never re-bills images that already exist.
- Async SQLAlchemy sessions with Alembic migrations.

## Architecture

```text
Client
  |
  v
FastAPI
  |-- /auth/* -> JWT authentication and token revocation
  |-- /api/v1/companies/ -> Doctor profile and monthly inputs
  |-- /api/v1/companies/start_planning -> ideas and post types
  |-- /api/v1/companies/design-prompts -> image prompts
  |-- /api/v1/companies/captions -> captions
  |-- /api/v1/companies/design-images/* -> image generation, review, approval
  |
  |-- PostgreSQL (profiles, users, monthly inputs, ideas, images)
  |-- Supabase Storage (Doctor pictures and generated images)
  `-- OpenRouter (text and image models)
```

### Main components

| Path | Responsibility |
| --- | --- |
| [`src/main.py`](src/main.py) | Creates the FastAPI app, mounts legacy uploads, and registers routers. |
| [`src/routes/`](src/routes/) | Defines authentication, profile, content, and image routes. |
| [`src/controllers/`](src/controllers/) | Coordinates validation, persistence, agent calls, and storage operations. |
| [`src/models/companies.py`](src/models/companies.py) | Defines users, Doctor profiles, monthly ideas, content batches, and image records. |
| [`src/schemas/companies.py`](src/schemas/companies.py) | Defines API request and response models. |
| [`src/agents/`](src/agents/) | Implements the planning, design-prompt, caption, and design-image agents. |
| [`src/prompts/`](src/prompts/) | Stores prompt templates separately from Python code. |
| [`src/database/companies.py`](src/database/companies.py) | Creates the async SQLAlchemy engine and session factory. |
| [`src/models/alembic/`](src/models/alembic/) | Contains the Alembic environment and migrations. |

## Requirements

- Python 3.12 or 3.13
- PostgreSQL
- Supabase project with a public Storage bucket named `doctor-designs`
- OpenRouter API key
- Tavily API key for trend and occasion research
- [`uv`](https://docs.astral.sh/uv/) recommended for dependency management

The supported Python range and dependencies are defined in
[`pyproject.toml`](pyproject.toml) and locked in [`uv.lock`](uv.lock).

## Installation

```powershell
git clone https://github.com/Mans404/AI_Content_Generation_Agent.git
cd AI_Content_Generation_Agent
uv sync
```

If `uv` is not available, use a Python 3.12/3.13 virtual environment and
install the project dependencies with your preferred package manager.

## Configuration

Copy [`.env.example`](.env.example) to `.env`, replace every placeholder with
your own value, and never commit credentials:

```powershell
Copy-Item .env.example .env
```

The application reads these environment variables:

| Variable | Required | Purpose |
| --- | --- | --- |
| `JWT_SECRET_KEY` | Yes | JWT signing key; must contain at least 32 characters. |
| `JWT_ISSUER` | No | JWT issuer; defaults to `content-generation-api`. |
| `OPENROUTER_API_KEY` | Yes for AI | OpenRouter access for text and image generation. |
| `TAVILY_API_KEY` | Yes for planning | Trend and occasion research. |
| `SUPABASE_URL` | Yes for uploads | Supabase project URL. |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes for uploads | Server-side Supabase Storage key. |
| `DESIGN_IMAGE_MODEL` | No | Image model; defaults to `google/gemini-2.5-flash-image`. |
| `DESIGN_IMAGE_MODALITIES` | No | Image response modalities; defaults to `image,text`. Use `image` for image-only models (FLUX, Recraft, ...). |
| `DESIGN_IMAGE_CONCURRENCY` | No | Maximum concurrent image requests; defaults to `3`. Tune to your OpenRouter rate limits. |

The database URL is currently read from
[`src/models/alembic.ini`](src/models/alembic.ini):

```ini
sqlalchemy.url = postgresql://USER:PASSWORD@HOST:5432/DATABASE
```

The application converts a `postgresql://` URL to the async
`postgresql+psycopg://` dialect automatically. The Supabase service-role key
must remain server-side and must not be exposed to clients.

## Database setup

From the repository root, apply all migrations:

```powershell
uv run alembic -c src/models/alembic.ini upgrade head
```

Check the current migration:

```powershell
uv run alembic -c src/models/alembic.ini current
```

## Running the API

```powershell
uv run uvicorn src.main:app --reload
```

Interactive documentation:

- <http://127.0.0.1:8000/docs>
- <http://127.0.0.1:8000/redoc>

## Authentication

Register with JSON:

```powershell
$token = (Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/auth/register" `
  -ContentType "application/json" `
  -Body '{"username":"example","password":"use-a-strong-password"}').access_token
```

Login uses OAuth2 form data:

```powershell
$token = (Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/auth/login" `
  -ContentType "application/x-www-form-urlencoded" `
  -Body "username=example&password=use-a-strong-password").access_token
```

Send the token as `Authorization: Bearer <token>` to protected endpoints.
`POST /auth/logout` revokes the current access token.

## API workflow

All `/api/v1/companies/*` endpoints require a bearer token.

### 1. Create or update a Doctor profile

```http
POST /api/v1/companies/
Content-Type: multipart/form-data
```

The first request creates the profile and returns `201 Created`; subsequent
requests update the same user's profile and return `200 OK`. `yourPicture` is
required on creation and optional on update.

| Field | Type | Required | Default / constraints |
| --- | --- | --- | --- |
| `doctor_name` | string | Yes | 1-200 characters |
| `doctor_specialization` | enum | No | `other`; see values below |
| `yourPicture` | file | Create only | JPG/JPEG, maximum 5 MB |
| `language` | enum | No | `EN` or `AR`; defaults to `EN` |
| `audiences` | repeated string | No | Maximum 20 items |
| `types_of_medical_procedures` | repeated string | No | Maximum 20 items |
| `strengths` | repeated string | No | Maximum 20 items |
| `posts_per_week` | integer | No | 1-21; defaults to `3` |

Supported `doctor_specialization` values are:
`internal_medicine`, `dentistry`, `dermatology`, `cardiology`, `neurology`,
`pediatrics`, `orthopedics`, `ophthalmology`, `obstetrics_and_gynecology`,
`urology`, `general_surgery`, `psychiatry`, `ent`, `physiotherapy`, and `other`.

Example:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/companies/" `
  -H "Authorization: Bearer $token" `
  -F "doctor_name=Dr. Example" `
  -F "doctor_specialization=dermatology" `
  -F "yourPicture=@C:\path\to\reference.jpg" `
  -F "language=EN" `
  -F "audiences=Adults" `
  -F "audiences=Local patients" `
  -F "posts_per_week=3"
```

List fields must be sent as repeated form fields. Each item must be a
non-empty string, and surrounding whitespace is removed.

### 2. Save monthly planning inputs

```http
POST /api/v1/companies/monthly-ideas
Content-Type: application/json
```

```json
{
  "doctor_offers": ["Free consultation this month"],
  "advice_and_matters_that_most_people_find_confusing": [
    "When should a patient see a specialist?"
  ]
}
```

Each list accepts at most 10 items. A Doctor profile must exist first.

### 3. Generate content ideas

```http
POST /api/v1/companies/start_planning
```

The endpoint has no request body. It loads the authenticated Doctor and the
current month's inputs, researches trends and upcoming Egyptian occasions, and
stores a new ideas batch containing `ideas` and matching `post_types`. The
number of returned items is `posts_per_week * 4`.

### 4. Generate design prompts and captions

```http
POST /api/v1/companies/design-prompts
POST /api/v1/companies/captions
```

Both endpoints have no request body and operate on the latest ideas batch.
`design_prompts[i]` and `captions[i]` correspond to the idea and post type at
the same index. Design prompts must be generated before requesting design
images.

### 5. Generate, review, and store design images

Image generation follows a human-in-the-loop flow:

```text
GET  /design-images                      <- current state + missing_indexes
  |
  v  (if missing_indexes is not empty)
POST /design-images/generate-all         <- generates only the missing designs
  |
  v
User reviews all designs
  |-- approve -> POST /design-images/{generation_id}/store       (stored = true)
  `-- reject  -> POST /design-images/{generation_id}/regenerate  (+ optional feedback)
                    `-> back to review
  |
  v
Every item has stored = true -> continue to the next step
```

#### List the current state

```http
GET /api/v1/companies/design-images
```

Use it when the page loads or refreshes. It returns every generated design with
its review state and the indexes that have not been generated yet.

```json
{
  "total": 12,
  "items": [
    {
      "generation_id": "6f1c...",
      "image_url": "https://.../pending/6f1c....png",
      "prompt_index": 0,
      "prompt": "A clean minimal poster about ...",
      "stored": false
    }
  ],
  "missing_indexes": [3, 7]
}
```

`stored: false` means the design is waiting for review; `stored: true` means it
was approved.

#### Generate all missing images

```http
POST /api/v1/companies/design-images/generate-all
```

Generates every design that does not exist yet, in parallel and bounded by
`DESIGN_IMAGE_CONCURRENCY`. The response contains a `generation_id`, a temporary
public `image_url`, `prompt_index`, and `remaining_prompts` for each available
image.

- **Retry-safe:** existing prompt indexes are returned as they are; the paid
  image model is only called for missing ones.
- **Partial failures:** if some images fail, the successful ones are saved and
  returned. Compare `len(generations)` with the number of prompts (or call
  `GET /design-images` and read `missing_indexes`) and call the endpoint again to
  complete the rest.
- Returns `502` only if no image could be generated at all.

#### Regenerate one image

```http
POST /api/v1/companies/design-images/{generation_id}/regenerate
Content-Type: application/json
```

```json
{
  "feedback": "Use a lighter background and fewer decorative elements."
}
```

The body is optional. The feedback (max 1000 characters) is appended to the
original prompt for this generation only; the prompt stored in the ideas batch is
not modified. The previous image file is deleted after the new one is saved.

Returns `409` if the design was already approved.

#### Approve (store) one image

```http
POST /api/v1/companies/design-images/{generation_id}/store
```

Moves the image from `pending/` to its final storage path and creates the
permanent design record. The call is idempotent: approving an already-approved
design returns the stored image again. If the database write fails after the
file was moved, the file is moved back.

Approved images cannot be regenerated. Storage operations use the public
Supabase `doctor-designs` bucket for both profile and generated images.

#### Status codes

| Code | Meaning |
| --- | --- |
| `404` | No company profile, no design prompts yet, or the generation was not found. |
| `409` | Trying to regenerate an image that is already approved. |
| `502` | The image model failed for every requested design. |

## Development notes

- The API exposes the existing local `uploads` directory at `/uploads` for
  legacy files; new uploads use Supabase Storage.
- The database uses async SQLAlchemy with `psycopg`.
- The planning, design-prompt, and caption agents use structured Pydantic output.
- No database lock is held while images are being generated; sessions are only
  opened for short reads and writes.
- All generated images of one request are saved in a single commit.
- `design_image_generations` and `design_images` both have a unique constraint on
  `(ideas_id, prompt_index)`. This is the real protection against duplicate
  images when several workers run; the in-process `asyncio.Lock` only covers a
  single process.
- There are currently no automated tests or CI workflows; use the Swagger UI or
  `curl.exe` for manual API verification.

## Known limitations / roadmap

- `generate-all` runs inside the request. For a large number of designs it may hit
  the gateway timeout; moving it to a background task that returns `202` plus a
  progress endpoint is the planned improvement.
- Images that were generated but never approved remain in the `pending/` folder
  of the bucket. A periodic cleanup job or a storage lifecycle rule is
  recommended.
- Regeneration currently accepts free-text feedback only; editing the design
  prompt itself is not supported yet.

## License

No license has been specified in the repository yet.