from pathlib import Path


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
