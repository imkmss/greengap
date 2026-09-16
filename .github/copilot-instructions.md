# Copilot instructions for this repository

## Repository purpose
This project models and visualizes green-space gaps for Seoul districts. It includes a FastAPI backend, a React frontend, and data-processing scripts for park, population, and green-space analysis.

## Stack and conventions
- Use Python for backend and data processing logic.
- Use React for UI work in the frontend.
- Keep data contracts consistent between backend responses and frontend consumers.
- Preserve district names, Korean labels, and the current schema unless the task explicitly changes them.

## Important directories
- `api/` — API service and database setup
- `ggfweb/src/` — React UI components and pages
- `pipeline/` — preprocessing, aggregation, and feature pipeline scripts
- `docs/` and `greengap/docs/` — background documentation
- `output/` and `model/` — generated artifacts; be careful not to overwrite them casually

## Development flow
1. Inspect the relevant existing module before making a change.
2. Keep the fix narrow and aligned with the current architecture.
3. Validate with the smallest relevant command for the changed behavior.
4. Update docs if the change alters endpoints, data fields, or workflow assumptions.

## Commands
- Start backend and DB:
  ```bash
  docker compose up --build db api
  ```
- Start frontend:
  ```bash
  cd ggfweb
  npm install
  npm start
  ```

## Safety rules
- Do not rewrite large generated data files unless the task specifically asks for it.
- Do not add new dependencies without a clear need.
- Prefer existing project patterns and naming conventions.
- If the issue involves both frontend and backend, check both layers before deciding on a fix.
