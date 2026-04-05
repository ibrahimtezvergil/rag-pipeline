from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.api.router import api_router
from app.middleware.auth import AuthMiddleware
from app.services.chat import create_default_chat_store
from app.services.dispatch import create_default_dispatcher, create_default_evaluation_dispatcher
from app.services.health import collect_health_status


_OPENAPI_TAGS = [
    {"name": "Ingestion", "description": "Document ingestion — ingest, status, delete"},
    {"name": "Query", "description": "Single-turn question answering and multi-turn chat"},
    {"name": "Collections", "description": "Qdrant collection management"},
    {"name": "Schedules", "description": "Cron-based re-index schedules"},
    {"name": "Evaluations", "description": "RAG evaluation runs (faithfulness, relevancy, recall)"},
    {"name": "Feedback", "description": "Chunk-level feedback for retrieval quality improvement"},
    {"name": "Health", "description": "Service health probe"},
]


def create_app() -> FastAPI:
    app = FastAPI(
        title="RAG Service",
        version="0.1.0",
        description=(
            "Multimodal RAG pipeline — ingest PDF, web, image, audio; "
            "hybrid dense+sparse retrieval with Cohere reranking; "
            "LLM-powered answer generation.\n\n"
            "**Authentication:** All endpoints (except `/health`, `/docs`, `/openapi.json`) "
            "require `X-API-Key` and `X-Application-ID` headers."
        ),
        openapi_tags=_OPENAPI_TAGS,
    )
    app.state.health_checkers = collect_health_status
    app.state.chat_store = create_default_chat_store()
    app.state.ingestion_dispatcher = create_default_dispatcher()
    app.state.evaluation_dispatcher = create_default_evaluation_dispatcher()
    app.add_middleware(AuthMiddleware)
    app.include_router(api_router)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"service": "rag-service"}

    def _custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            tags=_OPENAPI_TAGS,
            routes=app.routes,
        )
        schema.setdefault("components", {})["securitySchemes"] = {
            "ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"},
            "ApplicationIdAuth": {"type": "apiKey", "in": "header", "name": "X-Application-ID"},
        }
        schema["security"] = [{"ApiKeyAuth": [], "ApplicationIdAuth": []}]
        app.openapi_schema = schema
        return schema

    app.openapi = _custom_openapi  # type: ignore[method-assign]

    return app


app = create_app()
