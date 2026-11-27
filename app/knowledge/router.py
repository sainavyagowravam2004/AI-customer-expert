from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.knowledge.rag import crawl_website, hybrid_search, index_page_content
from app.workspace.router import get_current_user

router = APIRouter(prefix="/knowledge")
templates = Jinja2Templates(directory="app/templates")

@router.get("", response_class=HTMLResponse)
async def knowledge_page(request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    bid = str(user["business_id"])
    pages = (await db.execute(text("SELECT id, url, title, status, updated_at, length(raw_markdown) AS chars FROM knowledge_pages WHERE business_id = :bid ORDER BY updated_at DESC"), {"bid": bid})).mappings().all()
    chunks_count = (await db.execute(text("SELECT count(*) FROM knowledge_chunks WHERE business_id = :bid"), {"bid": bid})).scalar_one()
    rules = (await db.execute(text("SELECT * FROM instructions_and_skills WHERE business_id = :bid ORDER BY created_at DESC"), {"bid": bid})).mappings().all()
    changes = (await db.execute(text("SELECT pch.*, kp.url FROM page_change_history pch JOIN knowledge_pages kp ON pch.page_id = kp.id WHERE pch.business_id = :bid ORDER BY pch.detected_at DESC LIMIT 10"), {"bid": bid})).mappings().all()
    return templates.TemplateResponse(request, "knowledge.html", {
        "user": user, "pages": pages, "chunks_count": chunks_count, "rules": rules, "changes": changes
    })

@router.post("/crawl")
async def trigger_crawl(user=Depends(get_current_user), root_url: str = Form(...), db: AsyncSession = Depends(get_db)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    await crawl_website(db, str(user["business_id"]), root_url.strip(), max_pages=8)
    await db.commit()
    return RedirectResponse("/knowledge", status_code=302)

@router.post("/upload")
async def upload_doc(
    user=Depends(get_current_user),
    title: str = Form(""),
    manual_text: str = Form(""),
    file: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login", status_code=302)
    bid = str(user["business_id"])
    content = manual_text.strip()
    doc_title = title.strip() or "Uploaded Knowledge Note"
    if file and file.filename:
        raw_bytes = await file.read()
        content = raw_bytes.decode("utf-8", errors="ignore")
        doc_title = title.strip() or file.filename
    if content:
        await index_page_content(db, bid, f"doc://{doc_title.lower().replace(' ', '-')}", doc_title, content)
        await db.commit()
    return RedirectResponse("/knowledge", status_code=302)

@router.post("/instructions")
async def add_instruction(
    user=Depends(get_current_user),
    kind: str = Form("instruction"),
    title: str = Form(...),
    content: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login", status_code=302)
    await db.execute(
        text("INSERT INTO instructions_and_skills (business_id, kind, title, content) VALUES (:bid, :k, :t, :c)"),
        {"bid": str(user["business_id"]), "k": kind, "t": title, "c": content},
    )
    await db.commit()
    return RedirectResponse("/knowledge", status_code=302)

@router.post("/search", response_class=HTMLResponse)
async def test_hybrid_search(query: str = Form(...), user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)
    hits = await hybrid_search(db, str(user["business_id"]), query, top_k=5)
    if not hits:
        return HTMLResponse('<p class="text-xs text-slate-500 mt-2">No matching chunks found. Crawl a URL or paste knowledge first!</p>')
    items = "".join(
        f'<div class="p-3 bg-slate-50 border rounded mt-2 text-xs"><div class="font-semibold text-indigo-700">{h["metadata_json"].get("title", "Doc")} (RRF: {h["rrf_score"]:.4f})</div><p class="mt-1 text-slate-700">{h["content"][:280]}...</p></div>'
        for h in hits
    )
    return HTMLResponse(items)
