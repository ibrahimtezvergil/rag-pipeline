from fastapi import FastAPI

from app.api.router import api_router
from app.middleware.auth import AuthMiddleware
from app.services.chat import create_default_chat_store
from app.services.dispatch import create_default_dispatcher, create_default_evaluation_dispatcher
from app.services.health import collect_health_status


def create_app() -> FastAPI:
    app = FastAPI(title="RAG Service", version="0.1.0")
    app.state.health_checkers = collect_health_status
    app.state.chat_store = create_default_chat_store()
    app.state.ingestion_dispatcher = create_default_dispatcher()
    app.state.evaluation_dispatcher = create_default_evaluation_dispatcher()
    app.add_middleware(AuthMiddleware)
    app.include_router(api_router)

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"service": "rag-service"}

    return app


app = create_app()
