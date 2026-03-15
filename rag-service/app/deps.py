from dataclasses import dataclass

from fastapi import Request


@dataclass(slots=True)
class RequestContext:
    project_id: str
    api_key: str


def get_request_context(request: Request) -> RequestContext:
    return RequestContext(
        project_id=request.state.project_id,
        api_key=request.state.api_key,
    )

