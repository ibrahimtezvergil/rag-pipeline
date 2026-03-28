from __future__ import annotations

import json
from typing import Protocol
from uuid import uuid4

from redis.asyncio import Redis

from app.config import get_settings
from app.services.query import QueryService


class ChatStore(Protocol):
    async def get_history(self, session_id: str) -> list[dict[str, str]]: ...
    async def append_turns(self, session_id: str, turns: list[dict[str, str]]) -> None: ...


class RedisChatStore:
    def __init__(self, redis_url: str, ttl_seconds: int = 1800) -> None:
        self.client = Redis.from_url(redis_url, decode_responses=True)
        self.ttl_seconds = ttl_seconds

    def _key(self, session_id: str) -> str:
        return f"rag:chat:{session_id}"

    async def get_history(self, session_id: str) -> list[dict[str, str]]:
        items = await self.client.lrange(self._key(session_id), 0, -1)
        return [json.loads(item) for item in items]

    async def append_turns(self, session_id: str, turns: list[dict[str, str]]) -> None:
        key = self._key(session_id)
        if turns:
            await self.client.rpush(key, *[json.dumps(turn, sort_keys=True) for turn in turns])
        await self.client.ltrim(key, -6, -1)
        await self.client.expire(key, self.ttl_seconds)


def create_default_chat_store() -> ChatStore:
    return RedisChatStore(get_settings().redis_url)


class ChatService:
    def __init__(self, query_service: QueryService, store: ChatStore):
        self.query_service = query_service
        self.store = store

    async def reply(
        self,
        message: str,
        application_id,
        session_id: str | None = None,
    ) -> dict[str, object]:
        active_session_id = session_id or str(uuid4())
        history = await self.store.get_history(active_session_id)
        contextual_question = self._build_contextual_question(message, history)
        result = await self.query_service.answer_question(contextual_question, application_id)
        await self.store.append_turns(
            active_session_id,
            [
                {"role": "user", "content": message},
                {"role": "assistant", "content": str(result["answer"])},
            ],
        )
        return {
            "session_id": active_session_id,
            "answer": result["answer"],
            "retrieval_mode": result.get("retrieval_mode", "metadata_fallback"),
            "retrieval_context": result.get("retrieval_context", []),
            "sources": result["sources"],
        }

    def _build_contextual_question(self, message: str, history: list[dict[str, str]]) -> str:
        if not history:
            return message

        recent_user_messages = [
            turn["content"] for turn in history if turn.get("role") == "user"
        ][-3:]
        prefix = " ".join(recent_user_messages).strip()
        return f"{prefix}\n{message}".strip()
