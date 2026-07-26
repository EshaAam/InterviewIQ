# Migrations

Alembic, async. The DB URL and target metadata are wired in `env.py` from
`app.core.config` and `app.models` — don't hard-code a URL here.

```bash
# Autogenerate after a model change (Postgres must be reachable):
uv run alembic revision --autogenerate -m "describe change"

# Apply / roll back:
uv run alembic upgrade head
uv run alembic downgrade -1
```
