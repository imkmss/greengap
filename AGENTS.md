# AGENTS.md

## Project overview
This repository contains a green-space / urban-environment analysis project with three main parts:

- `api/`: FastAPI service that exposes cached data endpoints.
- `ggfweb/`: React frontend for the dashboard / map-based experience.
- `pipeline/` and `greengap/`: data processing, feature engineering, and analysis scripts.
- `data/`, `model/`, and `output/`: raw data, model artifacts, and derived outputs.

The app is designed to support Seoul district green-gap analysis and visualization.

## Tech stack
- Backend: Python 3.11, FastAPI, PostgreSQL, psycopg2
- Frontend: React 19, Create React App, React Router
- Container orchestration: Docker Compose

## Working conventions
- Prefer small, targeted edits over broad refactors.
- Keep backend and frontend changes isolated unless the API contract changes.
- When you modify data shapes, check both the server responses and the frontend consumers.
- Preserve existing Korean labels / district names and the current data schema unless a change is explicitly requested.

## Local development
### Backend API
From the repo root:

```bash
docker compose up --build db api
```

The API is exposed on http://localhost:8000.

### Frontend app
From the repo root:

```bash
cd ggfweb
npm install
npm start
```

The frontend is exposed on http://localhost:3000.

## Key entry points
- API startup and endpoints: `api/main.py`
- Database schema: `api/schema.sql`
- Frontend app shell: `ggfweb/src/App.js`
- Frontend navigation/data screens: `ggfweb/src/*.js`
- Data pipeline: `pipeline/`
- Analysis docs: `docs/` and `greengap/docs/`

## Validation guidance
- Validate with the smallest relevant command. Do not run broad suites if a targeted check is enough.
- For Python changes: prefer a focused import or smoke check for the changed endpoint or module.
- For React changes: prefer a targeted build or test if available.
- If a bug is caused by a schema or data contract mismatch, verify both the server result and the frontend rendering path.

## Change guidance
- Respect the current project structure and naming conventions.
- Prefer existing patterns used in sibling files.
- Update documentation when behavior, API endpoints, or data fields change meaningfully.
- Do not add unused dependencies without clear justification.

## Typical tasks
- Fix API or data issues: inspect `api/main.py` and relevant pipeline scripts first.
- Fix frontend UI or data visualization issues: inspect `ggfweb/src` and the API contract.
- Update data processing or feature engineering: inspect the scripts under `pipeline/` and relevant docs before editing outputs.

## Important notes
- This repo contains generated output CSVs in `model/` and `output/`; do not blindly overwrite them unless the task specifically requires regenerating derived outputs.
- Data files are large and domain-specific; prefer reading the relevant pipeline and docs before editing processing logic.
