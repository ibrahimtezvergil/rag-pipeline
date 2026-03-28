import pytest
from uuid import uuid4

from app.services.chat import ChatService


class FakeChatStore:
    def __init__(self) -> None:
        self.values: dict[str, list[dict[str, str]]] = {}

    async def get_history(self, session_id: str) -> list[dict[str, str]]:
        return list(self.values.get(session_id, []))

    async def append_turns(self, session_id: str, turns: list[dict[str, str]]) -> None:
        history = self.values.setdefault(session_id, [])
        history.extend(turns)
        self.values[session_id] = history[-6:]


class FakeQueryService:
    async def answer_question(self, question: str, application_id):
        return {
            "answer": f"cevap:{question}",
            "retrieval_mode": "semantic_qdrant",
            "retrieval_context": [
                {
                    "title": "context-title",
                    "snippet": "context-snippet",
                    "parent_context": "",
                }
            ],
            "sources": [],
        }


@pytest.mark.asyncio
async def test_chat_service_persists_session_history():
    service = ChatService(FakeQueryService(), FakeChatStore())

    first = await service.reply("Ilk soru", uuid4())
    second = await service.reply("Ikinci soru", uuid4(), session_id=first["session_id"])

    assert first["session_id"] == second["session_id"]
    assert second["answer"].startswith("cevap:")
    assert second["retrieval_mode"] == "semantic_qdrant"
    assert second["retrieval_context"] == [
        {
            "title": "context-title",
            "snippet": "context-snippet",
            "parent_context": "",
        }
    ]
