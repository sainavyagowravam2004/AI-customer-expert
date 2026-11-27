import httpx
from fastapi import FastAPI
from sqlalchemy import text
from app.core.config import settings
from app.core.database import engine
from app.workspace.router import router as workspace_router
from app.knowledge.router import router as knowledge_router
from app.support.router import router as support_router

app = FastAPI(title="AI Customer Expert")
app.include_router(workspace_router)
app.include_router(knowledge_router)
app.include_router(support_router)

@app.get("/health")
async def health():
    pg_ok, vec_ok, vec_ver, ollama_ok = False, False, "missing", False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            pg_ok = True
            res = await conn.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
            v = res.scalar_one_or_none()
            if v:
                vec_ok, vec_ver = True, v
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
            ollama_ok = r.status_code == 200
    except Exception:
        pass
    return {
        "status": "ok" if pg_ok else "degraded",
        "postgres": {"ok": pg_ok, "detail": "connected"},
        "pgvector": {"ok": vec_ok, "detail": vec_ver},
        "ollama": {"ok": ollama_ok, "detail": "reachable" if ollama_ok else "unreachable"},
    }