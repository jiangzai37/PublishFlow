from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.schemas import GenerateRequest
from app.core.content_gen.openai_provider import OpenAICompatibleProvider

router = APIRouter(tags=["content"])


@router.post("/generate")
async def generate_article(request: GenerateRequest):
    try:
        article = await OpenAICompatibleProvider().generate(
            topic=request.topic,
            style=request.style,
            length=request.length,
            with_headings=request.with_headings,
            with_tags=request.with_tags,
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except Exception:
        return JSONResponse(
            status_code=502, content={"detail": "模型服务调用失败，请检查本机配置。"}
        )
    return {"title": article.title, "body": article.body, "tags": article.tags}
