from pathlib import Path

from app.models.db import RagApplication


def test_compose_routes_runtime_services_via_pgbouncer():
    compose = Path(__file__).resolve().parents[1] / "docker-compose.yml"
    content = compose.read_text()

    assert "pgbouncer:" in content
    assert "DATABASE_URL: postgresql+asyncpg://rag:rag@pgbouncer:6432/ragdb" in content
    assert "DATABASE_DIRECT_URL: postgresql+asyncpg://rag:rag@postgres:5432/ragdb" in content
    assert "pool_mode = transaction" in content or "PGBOUNCER_POOL_MODE: transaction" in content


def test_pgbouncer_dockerfile_installs_envsubst_dependency():
    dockerfile = Path(__file__).resolve().parents[1] / "docker" / "pgbouncer" / "Dockerfile"
    content = dockerfile.read_text()

    assert "gettext" in content
    assert "pgbouncer" in content


def test_requirements_pin_httpx_for_crawl4ai_compatibility():
    requirements = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text()

    assert "httpx==0.27.2" in requirements


def test_pgbouncer_container_does_not_run_as_root():
    dockerfile = (Path(__file__).resolve().parents[1] / "docker" / "pgbouncer" / "Dockerfile").read_text()
    entrypoint = (Path(__file__).resolve().parents[1] / "docker" / "pgbouncer" / "entrypoint.sh").read_text()

    assert "adduser" in dockerfile or "USER pgbouncer" in dockerfile
    assert "su-exec" in entrypoint or "gosu" in entrypoint or "USER pgbouncer" in dockerfile


def test_langfuse_uses_separate_database_service():
    compose = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text()

    assert "langfuse_db:" in compose
    assert "DATABASE_URL: postgresql://langfuse:langfuse@langfuse_db:5432/langfuse" in compose


def test_alembic_history_has_single_head():
    versions_dir = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    revisions: dict[str, str | None] = {}
    referenced: set[str] = set()

    for path in versions_dir.glob("*.py"):
        if path.name == "__init__.py":
            continue
        content = path.read_text()
        revision = None
        down_revision = None
        for line in content.splitlines():
            if line.startswith("revision = "):
                revision = line.split("=", 1)[1].strip().strip('"').strip("'")
            if line.startswith("down_revision = "):
                raw = line.split("=", 1)[1].strip()
                if raw in {"None", "null"}:
                    down_revision = None
                elif raw.startswith("("):
                    values = [item.strip().strip('"').strip("'") for item in raw.strip("()").split(",") if item.strip()]
                    referenced.update(values)
                    down_revision = None
                else:
                    down_revision = raw.strip('"').strip("'")
                    referenced.add(down_revision)
        assert revision is not None, f"missing revision in {path.name}"
        revisions[revision] = down_revision

    heads = [revision for revision in revisions if revision not in referenced]
    assert len(heads) == 1, heads


def test_staging_compose_exists_and_uses_isolated_ports_and_volumes():
    compose = Path(__file__).resolve().parents[1] / "docker-compose.staging.yml"
    content = compose.read_text()

    assert "18000:8000" in content
    assert "15432:5432" in content
    assert "16432:6432" in content
    assert "16333:6333" in content
    assert "staging_postgres_data" in content
    assert "staging_qdrant_data" in content
    assert "staging_langfuse_postgres_data" in content


def test_env_staging_example_exists_with_required_keys():
    env_example = Path(__file__).resolve().parents[1] / ".env.staging.example"
    content = env_example.read_text()

    assert "DATABASE_URL=" in content
    assert "DATABASE_DIRECT_URL=" in content
    assert "QDRANT_URL=" in content
    assert "REDIS_URL=" in content
    assert "API_KEYS=" in content
    assert "GEMINI_API_KEY=" in content
    assert "COHERE_API_KEY=" in content
    assert "LANGFUSE_HOST=" in content


def test_staging_runbook_exists_with_migration_and_smoke_steps():
    runbook = Path(__file__).resolve().parents[2] / "docs" / "operations" / "rag-service-staging-runbook.md"
    content = runbook.read_text()

    assert "docker-compose -f docker-compose.staging.yml up -d --build" in content
    assert "alembic upgrade head" in content
    assert "/health" in content
    assert "/ingest" in content
    assert "/query" in content


def test_models_expose_rag_application():
    assert RagApplication.__tablename__ == "rag_applications"


def test_application_refactor_migration_renames_projects_table_and_columns():
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "008_refactor_projects_to_applications.py"
    )
    content = migration.read_text()

    assert 'op.rename_table("rag_projects", "rag_applications")' in content
    assert 'op.alter_column("rag_documents", "project_id", new_column_name="application_id")' in content
    assert 'op.alter_column("rag_schedules", "project_id", new_column_name="application_id")' in content
