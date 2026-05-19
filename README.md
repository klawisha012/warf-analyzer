# Warframe Riven Scanner

A web-based scanner for Warframe.market riven auctions. Polls the market API across four scan modes (groll / base / fast-weapon / price-history), classifies alerts (`good stats`, `endo`, `pod roll`), broadcasts them in real time over WebSocket, and renders price-history charts. Rewrite of a legacy PySide6 desktop app; the new stack is FastAPI + Postgres + React (Vite + Tailwind v4 + shadcn/ui).

## Quickstart

```sh
cp .env.example .env
docker compose up --build --wait
```

Then open <http://localhost:8080>.

### First-run setup (seed defaults)

After the stack is healthy, import the legacy `settings.json` (`good_weapons` + `fast_weapons_list`) into the database. The seeder is idempotent — safe to re-run.

```sh
docker compose exec backend uv run python -m app.seed
```

## Service URLs

| Service     | URL                              | Notes                                                     |
|-------------|----------------------------------|-----------------------------------------------------------|
| Frontend    | <http://localhost:8080>          | nginx serving the Vite bundle + proxying `/api` & `/ws`   |
| Backend API | <http://localhost:8000/api/...>  | FastAPI; reachable directly for debugging                 |
| WebSocket   | `ws://localhost:8080/ws/alerts`  | Live alert feed (also exposed at `ws://localhost:8000`)   |
| Postgres    | `localhost:5432`                 | User/db/pwd from `.env`                                   |
| pgAdmin     | <http://localhost:5050>          | `docker compose --profile tools up -d pgadmin` first      |

## Environment variables

Configured in `.env` (copy from `.env.example`):

| Var                 | Default  | Purpose                                       |
|---------------------|----------|-----------------------------------------------|
| `POSTGRES_USER`     | `riven`  | Postgres role used by the backend             |
| `POSTGRES_PASSWORD` | `riven`  | Password for the above                        |
| `POSTGRES_DB`       | `riven`  | Database name                                 |

The backend reads additional config from its own env (set in `docker-compose.yml`):

- `DATABASE_URL` — assembled from the three Postgres vars above
- `CORS_ORIGINS` — JSON array of allowed origins
- `WS_PATH` — defaults to `/ws/alerts`
- `WARFRAME_API_BASE` — defaults to `https://api.warframe.market/v1`

## Common operations

```sh
# Tail logs
docker compose logs -f backend

# Stop the stack
docker compose down

# Stop + wipe the Postgres volume (next `up` re-runs Alembic from scratch)
docker compose down -v

# Run the test suite inside the backend container
docker compose exec backend uv run pytest -q

# Open a psql shell
docker compose exec postgres psql -U riven -d riven
```

## Legacy files

The Python files at the repo root (`db.py`, `myplot.py`, `rivenwidgets.py`, `scanner2.py`, `uis3.py`, `run_mongo.bat`) are the original PySide6 app, kept only as historical reference. The new stack does not import them; once you've verified the rewrite works, they can be deleted.
