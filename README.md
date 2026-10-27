# AI Content Generation Agent

An early-stage FastAPI service for creating Doctor content profiles and preparing
them for AI-generated social media strategies.

The project currently accepts a Doctor's basic information and visual reference
design, stores the profile in PostgreSQL, and contains a LangChain agent that is
ready to generate structured content ideas. The agent integration is present but
is not yet enabled in the Doctor-creation request flow.

## Current status

### Implemented

- FastAPI application entry point.
- Versioned Doctor creation endpoint.
- Multipart form handling for Doctor data and JPG reference designs.
- Validation for required fields, JPG content type, file extension, and JPEG
  file signature.
- UUID-based storage names for uploaded designs.
- Asynchronous SQLAlchemy sessions for PostgreSQL.
- Doctor profile persistence with Alembic migrations.
- Pydantic response validation.
- LangChain/OpenRouter agent definitions with structured output models.
- Prompt files separated from Python code.

### Not yet connected

- The Doctor agent is not called by the controller yet; the invocation is
  currently commented out.
- Generated ideas, post types, and the Doctor theme are not returned by the API
  or persisted in the current Doctor-profile schema.
- There are no automated tests or CI workflows in the repository yet.
- There is no authentication, authorization, file-size limit, or image
  processing pipeline.
- There is no endpoint for reading, updating, or deleting companies.

## How the project evolved

The repository history records the following progression:

1. **Initial project** — created the Python package and dependency setup.
2. **Application configuration** — added the FastAPI application entry point.
3. **Initial database model** — introduced a companies table intended to store
   generated ideas, post types, a Doctor theme, doctor_specialization, and a reference
   design.
4. **Doctor-profile redesign** — evolved the database model from generated
   content output to a reusable Doctor profile with language, colors, tone,
   audiences, posting frequency, and logo path.
5. **Doctor creation feature** — added the `/api/v1/companies/` multipart
   endpoint, JPG upload persistence, database insertion, and response schema.
6. **Current stage** — the AI agent and prompts are in place, ready to be
   connected to the creation workflow and expanded into content-generation
   endpoints.

## Architecture

```text
Client
  |
  v
FastAPI route: POST /api/v1/companies/
  |
  v
Doctor controller
  |-- validates and saves JPG -> uploads/Doctor_designs/
  |-- creates DoctorContext for the AI agent
  |-- persists DoctorModel -> PostgreSQL
  |
  v
DoctorDataResponse

AI layer (currently available but not invoked by the controller)
  PromptLoader -> prompts/system.txt + prompts/user.txt
  DoctorAgent -> OpenRouter -> structured AgentOutput
```

### Main components

| Path | Responsibility |
| --- | --- |
| [`src/main.py`](src/main.py) | Creates the FastAPI app and registers routers. |
| [`src/routes/companies.py`](src/routes/companies.py) | Defines the Doctor API route and form fields. |
| [`src/controllers/companies.py`](src/controllers/companies.py) | Validates uploads, stores files, persists companies, and builds responses. |
| [`src/models/companies.py`](src/models/companies.py) | SQLAlchemy base, enums, and `DoctorModel`. |
| [`src/schemas/companies.py`](src/schemas/companies.py) | Pydantic response model for Doctor creation. |
| [`src/schemas/doctor_agent.py`](src/schemas/doctor_agent.py) | AI input and structured output models. |
| [`src/database/companies.py`](src/database/companies.py) | Reads the Alembic database URL and creates the async SQLAlchemy session factory. |
| [`src/agents/doctor_agent.py`](src/agents/doctor_agent.py) | Configures the LangChain agent and OpenRouter chat model. |
| [`src/prompt_loader.py`](src/prompt_loader.py) | Loads and formats prompt files. |
| [`src/prompts/`](src/prompts/) | System and user prompts for social media strategy generation. |
| [`src/models/alembic/`](src/models/alembic/) | Alembic environment and schema migrations. |

## Requirements

- Python 3.12 or 3.13
- PostgreSQL
- An OpenRouter API key if the AI agent is enabled
- [`uv`](https://docs.astral.sh/uv/) recommended for dependency and environment
  management

The supported Python range and dependencies are defined in
[`pyproject.toml`](pyproject.toml) and locked in [`uv.lock`](uv.lock).

## Installation

Clone the repository and install the locked dependencies:

```powershell
git clone https://github.com/Mans404/AI_Content_Generation_Agent.git
cd AI_Content_Generation_Agent
uv sync
```

If `uv` is not available, create a Python 3.12/3.13 virtual environment and
install the project with your preferred package manager.

## Configuration

The current database code reads `sqlalchemy.url` from
[`src/models/alembic.ini`](src/models/alembic.ini). Set it to a PostgreSQL
connection string before running the application or migrations:

```ini
sqlalchemy.url = postgresql://USER:PASSWORD@HOST:5432/DATABASE
```

For PostgreSQL, the application converts a `postgresql://` URL to the async
`postgresql+psycopg://` dialect automatically.

When enabling the agent, provide the OpenRouter key through the environment:

```powershell
$env:OPENROUTER_API_KEY = "your-key"
```

Do not commit database credentials or API keys. A local, ignored configuration
file or environment-based configuration should be used for development and
deployment.

## Database setup and migrations

The migration environment imports the SQLAlchemy metadata from
[`src/models/companies.py`](src/models/companies.py). From the repository root,
run:

```powershell
uv run alembic -c src/models/alembic.ini upgrade head
```

To inspect the current migration:

```powershell
uv run alembic -c src/models/alembic.ini current
```

The migration chain currently includes:

- `0be0239c931e` — initial companies/content-output schema.
- `4a3f6c7d8e9b` — converts the table to the Doctor-profile schema.
- `09cfdb09463c` — expands `picture_path` to 1024 characters.

## Running the API

Start the development server from the repository root:

```powershell
uv run uvicorn src.main:app --reload
```

The interactive API documentation is then available at:

- <http://127.0.0.1:8000/docs>
- <http://127.0.0.1:8000/redoc>

## API reference

### Create a Doctor

```http
POST /api/v1/companies/
Content-Type: multipart/form-data
```

Form fields:

| Field | Type | Required | Default / accepted values |
| --- | --- | --- | --- |
| `doctor_name` | string | Yes | At least one character |
| `doctor_specialization` | string | Yes | At least one character |
| `reference_design` | file | Yes | JPG/JPEG image |
| `language` | string | No | `EN`; also accepts `AR` |
| `primary_color` | string | No | `#000000` |
| `secondary_color` | string | No | `#FFFFFF` |
| `tone` | string | No | `professional`; also `friendly`, `playful`, `authoritative`, or `inspirational` |
| `audiences` | string list | No | Empty list |
| `posts_per_week` | integer | No | `3`, minimum `1` |

Example request:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/companies/" `
  -F "doctor_name=Dr. Example" `
  -F "doctor_specialization=Food and beverage" `
  -F "reference_design=@C:\path\to\reference.jpg" `
  -F "language=EN" `
  -F "primary_color=#5B3A29" `
  -F "secondary_color=#F4E8D0" `
  -F "tone=friendly" `
  -F "audiences=Coffee lovers" `
  -F "audiences=Local businesses" `
  -F "posts_per_week=3"
```

Successful requests return `201 Created` with the Doctor data, stored filename,
and uploaded file size. Invalid file types return `415 Unsupported Media Type`;
missing filenames return `422 Unprocessable Entity`.

## AI generation flow

The AI layer is implemented in [`src/agents/doctor_agent.py`](src/agents/doctor_agent.py):

1. `PromptLoader` reads the system and user prompt templates.
2. The agent initializes `gpt-4o-mini` through OpenRouter's OpenAI-compatible
   endpoint.
3. A `DoctorContext` supplies the Doctor UUID, name, doctor_specialization, and design path.
4. LangChain returns a structured `AgentOutput` containing:
   - `ideas`
   - `post_types`
   - `doctor_theme`

At the current stage, the controller creates the context but leaves the agent
call disabled. Connecting that call requires deciding whether generation should
be synchronous during Doctor creation or handled by a background job, then
persisting and exposing the generated output.

## Development notes

- Uploaded files are stored under `uploads/Doctor_designs/` using UUID filenames.
- The upload directory is created automatically when the controller module loads.
- The current database session factory uses SQLAlchemy's async engine and
  `psycopg`.
- The project uses `language` and `DoctorTone` enums shared by the
  route, model, and response schema.
- The repository currently has no test suite; manual API checks through Swagger
  UI or `curl.exe` are the available verification path.

## Suggested next steps

1. Move the database URL out of the Alembic file and into environment-backed
   settings.
2. Add automated tests for validation, upload handling, database persistence,
   and agent responses.
3. Decide on synchronous versus background AI generation.
4. Persist generated ideas, post types, and themes in a dedicated model or
   related table.
5. Add Doctor read/update/delete endpoints and authentication.
6. Add upload size limits, stronger image validation, and storage cleanup.
7. Add linting, CI, and deployment configuration.

## License

No license has been specified in the repository yet.
