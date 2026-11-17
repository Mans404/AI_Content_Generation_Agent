# AI Content Generation Agent

FastAPI service for creating an authenticated Doctor profile and generating a
monthly social-media content plan. The service can generate content ideas,
design prompts, captions, and images through OpenRouter, then stores profile
and generated-content data in PostgreSQL and Supabase Storage.

## Features

- JWT registration, login, and logout with per-user ownership checks.
- Create or update one Doctor profile per authenticated user.
- JPG/JPEG profile-picture validation, size limits, and Supabase Storage upload.
- Monthly Doctor offers and confusing matters as inputs to the planning agent.
- Structured content ideas and post types based on the requested posts per week.
- Design prompts and captions generated from the latest ideas batch.
- Concurrent generation of all missing design images.
- Human review flow for regenerating an image with optional feedback and approving
  an image for permanent storage.
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
  |-- /api/v1/companies/design-images/* -> image generation and approval
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
| `DESIGN_IMAGE_MODALITIES` | No | Image response modalities; defaults to `image,text`. |
| `DESIGN_IMAGE_CONCURRENCY` | No | Maximum concurrent image requests; defaults to `3`. |

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

Generate all missing images concurrently:

```http
POST /api/v1/companies/design-images/generate-all
```

The response contains a `generation_id`, temporary public `image_url`,
`prompt_index`, and `remaining_prompts` for each successful image. Generation
is retry-safe: existing prompt indexes are returned instead of calling the
paid image model again.

Regenerate one unapproved image, optionally with feedback:

```http
POST /api/v1/companies/design-images/{generation_id}/regenerate
Content-Type: application/json
```

```json
{
  "feedback": "Use a lighter background and fewer decorative elements."
}
```

Approve and move one generated image to its final storage path:

```http
POST /api/v1/companies/design-images/{generation_id}/store
```

Approved images cannot be regenerated. Storage operations use the public
Supabase `doctor-designs` bucket for both profile and generated images.

## Development notes

- The API exposes the existing local `uploads` directory at `/uploads` for
  legacy files; new uploads use Supabase Storage.
- The database uses async SQLAlchemy with `psycopg`.
- The planning, design-prompt, and caption agents use structured Pydantic output.
- Design image generation is bounded by `DESIGN_IMAGE_CONCURRENCY`, and individual
  failures do not discard successful images.
- There are currently no automated tests or CI workflows; use the Swagger UI or
  `curl.exe` for manual API verification.

## License

No license has been specified in the repository yet.
