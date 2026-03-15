from fastapi import APIRouter, Request, Response


router = APIRouter()


@router.get("/health")
async def healthcheck(request: Request, response: Response) -> dict[str, object]:
    services = await request.app.state.health_checkers()
    overall_status = (
        "ok" if all(service["status"] == "up" for service in services.values()) else "degraded"
    )

    if overall_status != "ok":
        response.status_code = 503

    return {
        "status": overall_status,
        "services": services,
    }

