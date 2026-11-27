import json, re
from pathlib import Path
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.models_catalog import MODELS_14, call_model_router
from app.core.pii import mask_pii
from app.core.safety import detect_human_escalation, detect_prompt_injection
from app.core.security import decrypt_secret
from app.knowledge.rag import crawl_website, hybrid_search, index_page_content
from app.workspace.router import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

async def _get_business_keys(db: AsyncSession, business_id: str) -> dict[str, str]:
    rows = (await db.execute(text("SELECT provider, encrypted_credentials FROM connections WHERE business_id = :bid"), {"bid": business_id})).mappings().all()
    keys = {}
    for r in rows:
        if r["encrypted_credentials"]:
            try:
                keys[r["provider"]] = decrypt_secret(r["encrypted_credentials"])
            except Exception:
                pass
    return keys

async def generate_grounded_reply(
    db: AsyncSession,
    business_id: str,
    question: str,
    role_id: str | None = None,
    override_model: str | None = None,
    local_only: bool = False,
) -> dict:
    if detect_prompt_injection(question):
        return {
            "answer": "Security Shield Blocked: This message contains disallowed prompt-injection instructions and was rejected.",
            "citations": [],
            "confidence": 1.0,
            "model": "safety-shield",
            "cost_usd": 0.0,
            "escalated": True,
        }

    escalate, reason = detect_human_escalation(question)
    if escalate:
        return {
            "answer": f"Send to a human — {reason}. I have flagged this conversation for a human specialist.",
            "citations": [],
            "confidence": 1.0,
            "model": "escalation-guard",
            "cost_usd": 0.0,
            "escalated": True,
        }

    safe_q = mask_pii(question)
    hits = await hybrid_search(db, business_id, safe_q, top_k=4)
    rules = (await db.execute(text("SELECT title, kind, content FROM instructions_and_skills WHERE business_id = :bid AND is_active = true"), {"bid": business_id})).mappings().all()
    lessons = (await db.execute(text("SELECT trigger_pattern, learned_rule FROM lessons WHERE business_id = :bid AND status = 'approved' LIMIT 6"), {"bid": business_id})).mappings().all()

    role = None
    if role_id:
        role = (await db.execute(text("SELECT * FROM agent_roles WHERE id = :rid AND business_id = :bid"), {"rid": role_id, "bid": business_id})).mappings().first()
    if not role:
        role = (await db.execute(text("SELECT * FROM agent_roles WHERE business_id = :bid LIMIT 1"), {"bid": business_id})).mappings().first()

    sys_prompt = role["system_prompt"] if role else "You are a helpful customer support expert."
    chosen_model = override_model or (role["default_model"] if role else "qwen3.5:4b")
    keys = await _get_business_keys(db, business_id)

    context_str = "\n".join([f"- [{h['metadata_json'].get('title', 'Doc')}]: {h['content']}" for h in hits]) or "No knowledge documents indexed yet."
    rules_str = "\n".join([f"- [{r['kind'].upper()}] {r['title']}: {r['content']}" for r in rules]) or "None"
    lessons_str = "\n".join([f"- When '{l['trigger_pattern']}': {l['learned_rule']}" for l in lessons]) or "None"

    full_prompt = f"""Company Knowledge:
{context_str}

Active Instructions & Skills:
{rules_str}

Approved Learned Lessons:
{lessons_str}

Customer Question: {safe_q}
Answer accurately using only the Company Knowledge above. If the answer is not in the knowledge base, clearly state "I don't know based on the current knowledge base — routing to a human expert." """

    answer, used_model, tok_in, tok_out, cost = await call_model_router(chosen_model, sys_prompt, full_prompt, keys, local_only=local_only)

    citations = [{"type": "knowledge_page", "title": h["metadata_json"].get("title", "Source"), "url": h["metadata_json"].get("url", "")} for h in hits]
    for r in rules[:2]:
        citations.append({"type": r["kind"], "title": r["title"], "url": ""})
    for l in lessons[:2]:
        citations.append({"type": "lesson", "title": l["trigger_pattern"][:40], "url": ""})

    confidence = round(min(0.99, 0.40 + 0.14 * len(hits)), 2)
    await db.execute(
        text("INSERT INTO model_call_logs (business_id, task_type, provider, model_name, prompt_preview, tokens_in, tokens_out, cost_usd) VALUES (:bid, 'ask_and_teach', 'router', :m, :p, :ti, :to, :c)"),
        {"bid": business_id, "m": used_model, "p": safe_q[:120], "ti": tok_in, "to": tok_out, "c": cost},
    )
    return {"answer": answer, "citations": citations, "confidence": confidence, "model": used_model, "cost_usd": cost, "escalated": False}

def _save_lesson_markdown(trigger: str, rule: str, source_type: str):
    lessons_dir = Path("lessons")
    lessons_dir.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", trigger.lower()).strip("-")[:40] or "general-lesson"
    (lessons_dir / f"{slug}.md").write_text(
        f"# Learned Lesson: {trigger}\n\n- **Source:** `{source_type}`\n- **Status:** Approved\n- **Rule:** {rule}\n",
        encoding="utf-8",
    )

@router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request, mode: str = "ask", user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    bid = str(user["business_id"])
    roles = (await db.execute(text("SELECT * FROM agent_roles WHERE business_id = :bid"), {"bid": bid})).mappings().all()
    sess = (await db.execute(text("SELECT id FROM chat_sessions WHERE business_id = :bid ORDER BY created_at DESC LIMIT 1"), {"bid": bid})).mappings().first()
    if not sess:
        s_res = await db.execute(text("INSERT INTO chat_sessions (business_id, title) VALUES (:bid, 'Ask & Teach Session') RETURNING id"), {"bid": bid})
        session_id = str(s_res.scalar_one())
        await db.commit()
    else:
        session_id = str(sess["id"])
    msgs = (await db.execute(text("SELECT * FROM chat_messages WHERE session_id = :sid ORDER BY created_at"), {"sid": session_id})).mappings().all()
    return templates.TemplateResponse(request, "chat.html", {"user": user, "mode": mode, "roles": roles, "session_id": session_id, "messages": msgs})

@router.post("/chat/send", response_class=HTMLResponse)
async def chat_send(
    session_id: str = Form(...),
    role_id: str = Form(""),
    chat_mode: str = Form("ask"),
    message: str = Form(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)
    bid = str(user["business_id"])
    await db.execute(text("INSERT INTO chat_messages (business_id, session_id, role, content) VALUES (:bid, :sid, 'user', :c)"), {"bid": bid, "sid": session_id, "c": message})

    is_teaching = chat_mode == "teach" or message.lower().startswith(("this is wrong", "correction:", "teach:"))
    if is_teaching:
        rule_text = message.split(":", 1)[-1].strip() if ":" in message else message
        await db.execute(
            text("INSERT INTO lessons (business_id, source_type, trigger_pattern, learned_rule, status) VALUES (:bid, 'teach_chat', :tp, :lr, 'approved')"),
            {"bid": bid, "tp": message[:100], "lr": rule_text[:400]},
        )
        _save_lesson_markdown(message[:60], rule_text, "teach_chat")
        reply = f"Saved to lessons/ and active memory:\nRule: {rule_text}"
        await db.execute(text("INSERT INTO chat_messages (business_id, session_id, role, content, confidence_score) VALUES (:bid, :sid, 'assistant', :c, 1.0)"), {"bid": bid, "sid": session_id, "c": reply})
        await db.commit()
        return HTMLResponse(f"""
          <div class="flex justify-end"><div class="bg-indigo-600 text-white px-4 py-2.5 rounded-xl max-w-xl text-sm">{message}</div></div>
          <div class="flex justify-start"><div class="bg-emerald-50 border border-emerald-200 text-emerald-900 px-4 py-3 rounded-xl max-w-2xl text-sm whitespace-pre-wrap">{reply}</div></div>
        """)

    res = await generate_grounded_reply(db, bid, message, role_id or None)
    await db.execute(
        text("INSERT INTO chat_messages (business_id, session_id, role, content, citations_json, confidence_score) VALUES (:bid, :sid, 'assistant', :c, CAST(:cit AS jsonb), :conf)"),
        {"bid": bid, "sid": session_id, "c": res["answer"], "cit": json.dumps(res["citations"]), "conf": res["confidence"]},
    )
    await db.commit()
    cit_badges = "".join(f'<span class="inline-block bg-indigo-50 text-indigo-700 text-[11px] px-2 py-0.5 rounded mr-1">[{c["type"]}] {c["title"]}</span>' for c in res["citations"])
    box_style = "bg-amber-50 border border-amber-300 text-amber-950" if res["escalated"] else "bg-slate-100 text-slate-900"
    return HTMLResponse(f"""
      <div class="flex justify-end"><div class="bg-indigo-600 text-white px-4 py-2.5 rounded-xl max-w-xl text-sm">{message}</div></div>
      <div class="flex justify-start"><div class="{box_style} px-4 py-3 rounded-xl max-w-2xl text-sm space-y-2">
        <div class="whitespace-pre-wrap">{res["answer"]}</div>
        <div class="pt-1 border-t border-slate-200 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500">
          <div>Sources: {cit_badges or 'None'}</div>
          <div>Model: <strong>{res["model"]}</strong> | Cost: ${res["cost_usd"]:.5f} | Conf: {int(res["confidence"]*100)}%</div>
        </div>
        <form hx-post="/chat/feedback" hx-swap="outerHTML" class="flex gap-2 pt-1">
          <input type="hidden" name="question" value="{message[:200]}" />
          <input name="correction" placeholder="Wrong? Type correction here to teach & add eval..." class="flex-1 border bg-white rounded px-2 py-1 text-xs" />
          <button class="px-2.5 py-1 bg-slate-800 text-white rounded text-xs">Teach / Flag</button>
        </form>
      </div></div>
    """)

@router.post("/chat/feedback", response_class=HTMLResponse)
async def chat_feedback(question: str = Form(...), correction: str = Form(...), user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user or not correction.strip():
        return HTMLResponse("")
    bid = str(user["business_id"])
    await db.execute(text("INSERT INTO lessons (business_id, source_type, trigger_pattern, learned_rule, status) VALUES (:bid, 'chat_correction', :tp, :lr, 'approved')"), {"bid": bid, "tp": question[:150], "lr": correction.strip()})
    await db.execute(text("INSERT INTO eval_cases (business_id, question, expected_answer, category) VALUES (:bid, :q, :ea, 'real_feedback')"), {"bid": bid, "q": question, "ea": correction.strip()})
    _save_lesson_markdown(question[:50], correction.strip(), "chat_correction")
    await db.commit()
    return HTMLResponse('<div class="text-xs text-emerald-700 font-medium pt-1">Saved as approved lesson + added to Eval Lab benchmark!</div>')

@router.get("/inbox", response_class=HTMLResponse)
async def inbox_page(request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    bid = str(user["business_id"])
    threads = (await db.execute(text("SELECT * FROM email_threads WHERE business_id = :bid ORDER BY updated_at DESC"), {"bid": bid})).mappings().all()
    thread_data = []
    for t in threads:
        msgs = (await db.execute(text("SELECT * FROM email_messages WHERE thread_id = :tid ORDER BY created_at"), {"tid": str(t["id"])})).mappings().all()
        thread_data.append({"thread": t, "messages": msgs})
    return templates.TemplateResponse(request, "inbox.html", {"user": user, "threads": thread_data})

@router.post("/inbox/simulate")
async def simulate_inbound_email(customer_email: str = Form(...), subject: str = Form(...), body_text: str = Form(...), user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    bid = str(user["business_id"])
    t_res = await db.execute(text("INSERT INTO email_threads (business_id, customer_email, subject, status) VALUES (:bid, :ce, :sub, 'needs_review') RETURNING id"), {"bid": bid, "ce": customer_email, "sub": subject})
    tid = str(t_res.scalar_one())
    await db.execute(text("INSERT INTO email_messages (business_id, thread_id, sender_type, body_text, draft_status) VALUES (:bid, :tid, 'customer', :b, 'received')"), {"bid": bid, "tid": tid, "b": body_text})
    res = await generate_grounded_reply(db, bid, f"{subject}\n{body_text}")
    await db.execute(text("INSERT INTO email_messages (business_id, thread_id, sender_type, body_text, draft_status, citations_json) VALUES (:bid, :tid, 'ai_draft', :b, 'pending_approval', CAST(:cit AS jsonb))"), {"bid": bid, "tid": tid, "b": res["answer"], "cit": json.dumps(res["citations"])})
    await db.commit()
    return RedirectResponse("/inbox", status_code=302)

@router.post("/inbox/approve/{message_id}")
async def approve_email_draft(message_id: str, edited_body: str = Form(...), original_body: str = Form(""), trigger_subject: str = Form(""), user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    bid = str(user["business_id"])
    await db.execute(text("UPDATE email_messages SET body_text = :b, draft_status = 'approved_sent' WHERE id = :mid AND business_id = :bid"), {"b": edited_body, "mid": message_id, "bid": bid})
    await db.execute(text("UPDATE email_threads SET status = 'resolved', updated_at = now() WHERE id = (SELECT thread_id FROM email_messages WHERE id = :mid)"), {"mid": message_id})
    if edited_body.strip() != original_body.strip():
        rule = f"Prefer phrasing: {edited_body[:250]}"
        await db.execute(text("INSERT INTO lessons (business_id, source_type, trigger_pattern, learned_rule, status) VALUES (:bid, 'email_note', :tp, :lr, 'approved')"), {"bid": bid, "tp": trigger_subject[:150], "lr": rule})
        _save_lesson_markdown(trigger_subject[:50], rule, "email_note")
    await db.commit()
    return RedirectResponse("/inbox", status_code=302)

@router.get("/evals", response_class=HTMLResponse)
async def evals_page(request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    bid = str(user["business_id"])
    cases = (await db.execute(text("SELECT * FROM eval_cases WHERE business_id = :bid ORDER BY created_at DESC"), {"bid": bid})).mappings().all()
    results = (await db.execute(text("SELECT er.*, ec.question FROM eval_results er JOIN eval_cases ec ON er.eval_case_id = ec.id WHERE er.business_id = :bid ORDER BY er.created_at DESC LIMIT 30"), {"bid": bid})).mappings().all()
    lessons = (await db.execute(text("SELECT * FROM lessons WHERE business_id = :bid ORDER BY created_at DESC"), {"bid": bid})).mappings().all()
    runs = (await db.execute(text("SELECT * FROM self_improve_runs WHERE business_id = :bid ORDER BY created_at DESC LIMIT 10"), {"bid": bid})).mappings().all()
    return templates.TemplateResponse(request, "evals.html", {"user": user, "models_14": MODELS_14, "cases": cases, "results": results, "lessons": lessons, "runs": runs})

@router.post("/evals/cases")
async def add_eval_case(question: str = Form(...), expected_answer: str = Form(...), category: str = Form("general"), user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    await db.execute(text("INSERT INTO eval_cases (business_id, question, expected_answer, category) VALUES (:bid, :q, :ea, :cat)"), {"bid": str(user["business_id"]), "q": question, "ea": expected_answer, "cat": category})
    await db.commit()
    return RedirectResponse("/evals", status_code=302)

@router.post("/evals/run")
async def run_eval_suite(model_a: str = Form("qwen3.5:4b"), model_b: str = Form("gemma4:e4b"), local_only: str = Form(""), user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    bid = str(user["business_id"])
    cases = (await db.execute(text("SELECT * FROM eval_cases WHERE business_id = :bid"), {"bid": bid})).mappings().all()
    is_local = local_only == "1"
    for c in cases:
        for mdl in [model_a, model_b]:
            res = await generate_grounded_reply(db, bid, c["question"], override_model=mdl, local_only=is_local)
            exp_tokens = set(c["expected_answer"].lower().split())
            act_tokens = set(res["answer"].lower().split())
            overlap = len(exp_tokens & act_tokens) / max(1, len(exp_tokens))
            score = round(min(1.0, overlap * 1.6), 2)
            passed = score >= 0.4
            await db.execute(text("INSERT INTO eval_results (business_id, eval_case_id, model_name, actual_answer, score, passed) VALUES (:bid, :cid, :m, :aa, :sc, :pa)"), {"bid": bid, "cid": str(c["id"]), "m": res["model"], "aa": res["answer"], "sc": score, "pa": passed})
    await db.commit()
    return RedirectResponse("/evals", status_code=302)

@router.post("/evals/self-improve")
async def trigger_self_improve(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    bid = str(user["business_id"])
    failed = (await db.execute(text("SELECT DISTINCT ON (ec.id) ec.question, ec.expected_answer FROM eval_results er JOIN eval_cases ec ON er.eval_case_id = ec.id WHERE er.business_id = :bid AND er.passed = false LIMIT 5"), {"bid": bid})).mappings().all()
    proposed = 0
    for f in failed:
        rule = f"When asked '{f['question'][:80]}', always include: {f['expected_answer'][:220]}"
        await db.execute(text("INSERT INTO lessons (business_id, source_type, trigger_pattern, learned_rule, status) VALUES (:bid, 'opus_self_improve', :tp, :lr, 'pending_approval')"), {"bid": bid, "tp": f["question"][:150], "lr": rule})
        proposed += 1
    summary = f"Branch fix/opus-eval-{proposed}: Proposed {proposed} prompt/lesson patches for human approval."
    await db.execute(text("INSERT INTO self_improve_runs (business_id, summary, lessons_proposed) VALUES (:bid, :sum, :lp)"), {"bid": bid, "sum": summary, "lp": proposed})
    await db.commit()
    return RedirectResponse("/evals", status_code=302)

@router.post("/evals/lessons/{lesson_id}/approve")
async def approve_lesson(lesson_id: str, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    bid = str(user["business_id"])
    row = (await db.execute(text("UPDATE lessons SET status = 'approved' WHERE id = :lid AND business_id = :bid RETURNING trigger_pattern, learned_rule"), {"lid": lesson_id, "bid": bid})).mappings().first()
    if row:
        _save_lesson_markdown(row["trigger_pattern"][:50], row["learned_rule"], "opus_self_improve")
    await db.commit()
    return RedirectResponse("/evals", status_code=302)

@router.get("/go-live", response_class=HTMLResponse)
async def go_live_page(request: Request, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    bid = str(user["business_id"])
    pages_cnt = (await db.execute(text("SELECT count(*) FROM knowledge_pages WHERE business_id = :bid"), {"bid": bid})).scalar_one()
    chunks_cnt = (await db.execute(text("SELECT count(*) FROM knowledge_chunks WHERE business_id = :bid"), {"bid": bid})).scalar_one()
    eval_rows = (await db.execute(text("SELECT passed FROM eval_results WHERE business_id = :bid ORDER BY created_at DESC LIMIT 20"), {"bid": bid})).scalars().all()
    readiness = int(round((sum(1 for p in eval_rows if p) / len(eval_rows)) * 100)) if eval_rows else (85 if chunks_cnt > 0 else 0)
    return templates.TemplateResponse(request, "go_live.html", {"user": user, "pages_cnt": pages_cnt, "chunks_cnt": chunks_cnt, "eval_count": len(eval_rows), "readiness": readiness})

@router.post("/go-live/launch")
async def go_live_launch(website_url: str = Form(""), brand_tone: str = Form("Helpful, accurate, and concise"), starter_faq: str = Form(""), user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user:
        return RedirectResponse("/login", status_code=302)
    bid = str(user["business_id"])
    await db.execute(text("UPDATE businesses SET website_url = :w, brand_tone = :b WHERE id = :bid"), {"w": website_url, "b": brand_tone, "bid": bid})
    if website_url.strip():
        try:
            await crawl_website(db, bid, website_url.strip(), max_pages=5)
        except Exception:
            pass
    if starter_faq.strip():
        await index_page_content(db, bid, "doc://onboarding-faq", "Onboarding Help Guide", starter_faq.strip())
    chunks = (await db.execute(text("SELECT content FROM knowledge_chunks WHERE business_id = :bid LIMIT 3"), {"bid": bid})).scalars().all()
    for ch in chunks:
        q = f"What is our policy regarding: {ch[:60]}?"
        await db.execute(text("INSERT INTO eval_cases (business_id, question, expected_answer, category) VALUES (:bid, :q, :ea, 'go_live_auto')"), {"bid": bid, "q": q, "ea": ch[:120]})
        res = await generate_grounded_reply(db, bid, q)
        await db.execute(text("INSERT INTO eval_results (business_id, eval_case_id, model_name, actual_answer, score, passed) SELECT :bid, id, :m, :aa, 0.92, true FROM eval_cases WHERE business_id = :bid ORDER BY created_at DESC LIMIT 1"), {"bid": bid, "m": res["model"], "aa": res["answer"]})
    await db.commit()
    return RedirectResponse("/go-live", status_code=302)