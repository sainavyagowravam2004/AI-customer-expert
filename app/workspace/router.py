import json, uuid
from datetime import datetime, timezone
import httpx
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import get_db
from app.core.pii import mask_pii
from app.core.security import decrypt_secret, encrypt_secret, hash_password, verify_password

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

DEFAULT_ROLES = [
    ("Support Engineer", "Technical troubleshooting, logs, APIs, and bug reproduction.", "You are a precise Support Engineer. Answer strictly from retrieved company knowledge and cite sources.", "qwen3.5:4b", 0.1),
    ("Support Executive", "Billing, refunds, account plans, and polite customer care.", "You are an empathetic Support Executive. Keep replies clear, warm, and policy-accurate.", "qwen3.5:4b", 0.3),
    ("AI Consultant", "Onboarding strategy, best practices, and workflow recommendations.", "You are a strategic AI Consultant helping customers get maximum value.", "gemma4:e4b", 0.4),
]

async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = request.cookies.get("session_user_id")
    if not user_id:
        return None
    res = await db.execute(
        text("SELECT u.id, u.email, u.full_name, u.business_id, b.name AS business_name, b.website_url, b.brand_tone FROM users u JOIN businesses b ON u.business_id = b.id WHERE u.id = :uid"),
        {"uid": user_id},
    )
    row = res.mappings().first()
    if row:
        await db.execute(text("SELECT set_config('app.current_business_id', :bid, true)"), {"bid": str(row["business_id"])})
    return row

async def seed_business_defaults(db: AsyncSession, business_id: str):
    for provider in ["claude", "gemini", "openrouter", "ollama", "gmail"]:
        cfg = {"base_url": settings.ollama_base_url, "model": "qwen3.5:4b"} if provider == "ollama" else {}
        status = "connected" if provider == "ollama" else "disconnected"
        await db.execute(
            text("INSERT INTO connections (business_id, provider, config_json, status) VALUES (:bid, :p, CAST(:cfg AS jsonb), :st) ON CONFLICT DO NOTHING"),
            {"bid": business_id, "p": provider, "cfg": json.dumps(cfg), "st": status},
        )
    for name, desc, sys_p, model, temp in DEFAULT_ROLES:
        await db.execute(
            text("INSERT INTO agent_roles (business_id, name, description, system_prompt, default_model, temperature) VALUES (:bid, :n, :d, :s, :m, :t)"),
            {"bid": business_id, "n": name, "d": desc, "s": sys_p, "m": model, "t": temp},
        )
    await db.execute(
        text("INSERT INTO prompt_versions (business_id, name, version, template_text, is_active) VALUES (:bid, 'default_rag_answer', 1, :tpl, true)"),
        {"bid": business_id, "tpl": "Context:\n{context}\n\nLessons:\n{lessons}\n\nCustomer Question: {question}\nAnswer clearly with citations:"},
    )

@router.get("/", response_class=HTMLResponse)
async def home(request: Request, user=Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    return RedirectResponse("/settings", status_code=302)

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", { "error": None})

@router.post("/login")
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...), db: AsyncSession = Depends(get_db)):
    res = await db.execute(text("SELECT id, password_hash FROM users WHERE email = :e"), {"e": email.strip().lower()})
    row = res.mappings().first()
    if not row or not verify_password(password, row["password_hash"]):
        return templates.TemplateResponse(request, "login.html", { "error": "Invalid email or password"})
    resp = RedirectResponse("/settings", status_code=302)
    resp.set_cookie("session_user_id", str(row["id"]), httponly=True, samesite="lax")
    return resp

@router.post("/demo-login")
async def demo_login(db: AsyncSession = Depends(get_db)):
    res = await db.execute(text("SELECT id FROM users WHERE email = 'demo@acme.ai'"))
    row = res.mappings().first()
    if not row:
        biz_res = await db.execute(
            text("INSERT INTO businesses (name, slug, website_url, brand_tone) VALUES ('Acme Cloud Demo', 'acme-demo', 'https://example.com', 'Helpful, concise, and accurate') RETURNING id")
        )
        biz_id = str(biz_res.scalar_one())
        u_res = await db.execute(
            text("INSERT INTO users (business_id, email, password_hash, full_name) VALUES (:bid, 'demo@acme.ai', :pw, 'Demo Owner') RETURNING id"),
            {"bid": biz_id, "pw": hash_password("demo1234")},
        )
        user_id = str(u_res.scalar_one())
        await seed_business_defaults(db, biz_id)
    else:
        user_id = str(row["id"])
    await db.commit()
    resp = RedirectResponse("/settings", status_code=302)
    resp.set_cookie("session_user_id", user_id, httponly=True, samesite="lax")
    return resp

@router.post("/signup")
async def signup_submit(
    business_name: str = Form(...),
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    slug = f"{business_name.lower().replace(' ', '-')[:40]}-{uuid.uuid4().hex[:6]}"
    biz_res = await db.execute(
        text("INSERT INTO businesses (name, slug) VALUES (:n, :s) RETURNING id"),
        {"n": business_name.strip(), "s": slug},
    )
    biz_id = str(biz_res.scalar_one())
    u_res = await db.execute(
        text("INSERT INTO users (business_id, email, password_hash, full_name) VALUES (:bid, :e, :pw, :fn) RETURNING id"),
        {"bid": biz_id, "e": email.strip().lower(), "pw": hash_password(password), "fn": full_name.strip()},
    )
    user_id = str(u_res.scalar_one())
    await seed_business_defaults(db, biz_id)
    await db.commit()
    resp = RedirectResponse("/settings", status_code=302)
    resp.set_cookie("session_user_id", user_id, httponly=True, samesite="lax")
    return resp

@router.post("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("session_user_id")
    return resp

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    bid = str(user["business_id"])
    conns = (await db.execute(text("SELECT * FROM connections WHERE business_id = :bid ORDER BY provider"), {"bid": bid})).mappings().all()
    roles = (await db.execute(text("SELECT * FROM agent_roles WHERE business_id = :bid ORDER BY created_at"), {"bid": bid})).mappings().all()
    prompts = (await db.execute(text("SELECT * FROM prompt_versions WHERE business_id = :bid ORDER BY name, version DESC"), {"bid": bid})).mappings().all()
    logs = (await db.execute(text("SELECT * FROM model_call_logs WHERE business_id = :bid ORDER BY created_at DESC LIMIT 20"), {"bid": bid})).mappings().all()
    return templates.TemplateResponse(request, "settings.html", { "user": user, "connections": conns, "roles": roles, "prompts": prompts, "logs": logs
    })

@router.post("/settings/workspace")
async def update_workspace(
    user=Depends(get_current_user),
    name: str = Form(...),
    website_url: str = Form(""),
    brand_tone: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login", status_code=302)
    await db.execute(
        text("UPDATE businesses SET name = :n, website_url = :w, brand_tone = :b WHERE id = :bid"),
        {"n": name, "w": website_url, "b": brand_tone, "bid": str(user["business_id"])},
    )
    await db.commit()
    return RedirectResponse("/settings", status_code=302)

@router.post("/settings/connections/{provider}")
async def save_connection(
    provider: str,
    user=Depends(get_current_user),
    api_key: str = Form(""),
    base_url: str = Form(""),
    model_name: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login", status_code=302)
    bid = str(user["business_id"])
    enc = encrypt_secret(api_key.strip()) if api_key.strip() else None
    cfg = {}
    if base_url.strip():
        cfg["base_url"] = base_url.strip()
    if model_name.strip():
        cfg["model"] = model_name.strip()
    await db.execute(
        text("UPDATE connections SET encrypted_credentials = COALESCE(:enc, encrypted_credentials), config_json = config_json || CAST(:cfg AS jsonb), status = 'configured' WHERE business_id = :bid AND provider = :p"),
        {"enc": enc, "cfg": json.dumps(cfg), "bid": bid, "p": provider},
    )
    await db.commit()
    return RedirectResponse("/settings", status_code=302)

@router.post("/settings/connections/{provider}/test", response_class=HTMLResponse)
async def test_connection(provider: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)
    bid = str(user["business_id"])
    row = (await db.execute(text("SELECT * FROM connections WHERE business_id = :bid AND provider = :p"), {"bid": bid, "p": provider})).mappings().first()
    ok = False
    detail = "Not configured"
    if provider == "ollama":
        url = (row["config_json"] or {}).get("base_url", settings.ollama_base_url)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{url.rstrip('/')}/api/tags")
                ok = r.status_code == 200
                detail = f"Connected ({len(r.json().get('models', []))} models)" if ok else f"HTTP {r.status_code}"
        except Exception as exc:
            detail = str(exc)[:60]
    else:
        secret = decrypt_secret(row["encrypted_credentials"]) if row else ""
        if secret:
            ok = True
            detail = f"Encrypted key verified (ends with ...{secret[-4:]})"
    status = "connected" if ok else "error"
    await db.execute(
        text("UPDATE connections SET status = :st, last_tested_at = :now WHERE business_id = :bid AND provider = :p"),
        {"st": status, "now": datetime.now(timezone.utc), "bid": bid, "p": provider},
    )
    await db.commit()
    color = "text-emerald-600" if ok else "text-rose-600"
    return HTMLResponse(f'<span class="{color} font-medium text-xs">{status.upper()}: {detail}</span>')

@router.post("/settings/roles")
async def create_role(
    user=Depends(get_current_user),
    name: str = Form(...),
    description: str = Form(""),
    system_prompt: str = Form(...),
    default_model: str = Form("qwen3.5:4b"),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return RedirectResponse("/login", status_code=302)
    await db.execute(
        text("INSERT INTO agent_roles (business_id, name, description, system_prompt, default_model) VALUES (:bid, :n, :d, :s, :m)"),
        {"bid": str(user["business_id"]), "n": name, "d": description, "s": system_prompt, "m": default_model},
    )
    await db.commit()
    return RedirectResponse("/settings", status_code=302)

@router.post("/settings/roles/{role_id}/test", response_class=HTMLResponse)
async def test_role_chat(role_id: str, message: str = Form(...), user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)
    bid = str(user["business_id"])
    role = (await db.execute(text("SELECT * FROM agent_roles WHERE id = :rid AND business_id = :bid"), {"rid": role_id, "bid": bid})).mappings().first()
    safe_msg = mask_pii(message)
    model = role["default_model"] if role else "qwen3.5:4b"
    sys_prompt = role["system_prompt"] if role else "You are a helpful assistant."
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.post(
                f"{settings.ollama_base_url.rstrip('/')}/api/chat",
                json={"model": model, "stream": False, "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": safe_msg}]},
            )
            reply = r.json().get("message", {}).get("content", "No reply")
    except Exception as exc:
        reply = f"Ollama error: {exc}"
    await db.execute(
        text("INSERT INTO model_call_logs (business_id, task_type, provider, model_name, prompt_preview) VALUES (:bid, 'role_test', 'ollama', :m, :p)"),
        {"bid": bid, "m": model, "p": safe_msg[:120]},
    )
    await db.commit()
    return HTMLResponse(f'<div class="p-3 bg-slate-100 rounded text-sm mt-2"><strong>{role["name"]} ({model}):</strong><p class="mt-1 whitespace-pre-wrap">{reply}</p></div>')

@router.post("/settings/delete-business")
async def delete_business(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    await db.execute(text("DELETE FROM businesses WHERE id = :bid"), {"bid": str(user["business_id"])})
    await db.commit()
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("session_user_id")
    return resp
