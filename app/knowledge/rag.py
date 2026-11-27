import hashlib, json, math, re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.safety import detect_prompt_injection

def chunk_text(content: str, size: int = 800, overlap: int = 120) -> list[str]:
    clean = re.sub(r"\s+", " ", content).strip()
    if not clean:
        return []
    chunks = []
    start = 0
    while start < len(clean):
        chunks.append(clean[start : start + size])
        start += max(1, size - overlap)
    return chunks

def deterministic_embedding(text_val: str, dim: int = 768) -> list[float]:
    vec = [0.0] * dim
    tokens = re.findall(r"[a-z0-9]+", text_val.lower())
    for tok in tokens:
        h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if ((h >> 8) & 1) == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [round(x / norm, 6) for x in vec]

async def get_embedding(text_val: str) -> list[float]:
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            r = await client.post(
                f"{settings.ollama_base_url.rstrip('/')}/api/embeddings",
                json={"model": "nomic-embed-text", "prompt": text_val[:2000]},
            )
            if r.status_code == 200 and r.json().get("embedding"):
                emb = r.json()["embedding"]
                if len(emb) == 768:
                    return emb
    except Exception:
        pass
    return deterministic_embedding(text_val, 768)

async def preview_sitemap(sitemap_url: str) -> dict:
    urls: list[str] = []
    nested_sitemaps: list[str] = []
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers={"User-Agent": "AICustomerExpertBot/1.0"}) as client:
        r = await client.get(sitemap_url)
        r.raise_for_status()
        body = r.text
        if "<urlset" in body or "<sitemapindex" in body:
            root = ET.fromstring(body)
            for elem in root.iter():
                tag = elem.tag.split("}")[-1]
                if tag == "loc" and elem.text:
                    loc = elem.text.strip()
                    if loc.endswith(".xml"):
                        nested_sitemaps.append(loc)
                    else:
                        urls.append(loc)
            for sub in nested_sitemaps[:5]:
                try:
                    sr = await client.get(sub)
                    sroot = ET.fromstring(sr.text)
                    for elem in sroot.iter():
                        if elem.tag.split("}")[-1] == "loc" and elem.text and not elem.text.strip().endswith(".xml"):
                            urls.append(elem.text.strip())
                except Exception:
                    continue
        else:
            soup = BeautifulSoup(body, "html.parser")
            domain = urlparse(sitemap_url).netloc
            urls.append(sitemap_url)
            for a in soup.find_all("a", href=True):
                href = urljoin(sitemap_url, a["href"]).split("#")[0]
                if urlparse(href).netloc == domain and href not in urls:
                    urls.append(href)
    unique_urls = list(dict.fromkeys(urls))
    duplicates = len(urls) - len(unique_urls)
    return {
        "sitemap_url": sitemap_url,
        "nested_count": len(nested_sitemaps),
        "total_urls": len(unique_urls),
        "duplicates_skipped": duplicates,
        "first_url": unique_urls[0] if unique_urls else sitemap_url,
        "last_url": unique_urls[-1] if unique_urls else sitemap_url,
        "est_minutes": max(1, round(len(unique_urls) / 20)),
        "urls": unique_urls,
    }

async def index_page_content(
    db: AsyncSession,
    business_id: str,
    url: str,
    title: str,
    raw_text: str,
    sitemap_id: str | None = None,
    status: str = "active",
) -> str:
    if detect_prompt_injection(raw_text):
        raw_text = "[SANITIZED_UNTRUSTED_WEB_TEXT] " + raw_text

    content_hash = hashlib.sha256(raw_text.encode()).hexdigest()
    existing = (
        await db.execute(
            text("SELECT id, content_hash FROM knowledge_pages WHERE business_id = :bid AND url = :url"),
            {"bid": business_id, "url": url},
        )
    ).mappings().first()

    if existing:
        page_id = str(existing["id"])
        if existing["content_hash"] != content_hash:
            await db.execute(
                text("INSERT INTO page_change_history (business_id, page_id, old_hash, new_hash, diff_summary) VALUES (:bid, :pid, :oh, :nh, :ds)"),
                {"bid": business_id, "pid": page_id, "oh": existing["content_hash"], "nh": content_hash, "ds": f"Updated ({len(raw_text)} chars)"},
            )
            await db.execute(
                text("UPDATE knowledge_pages SET title = :t, raw_markdown = :rm, content_hash = :ch, status = :st, updated_at = now() WHERE id = :pid"),
                {"t": title[:500], "rm": raw_text, "ch": content_hash, "st": status, "pid": page_id},
            )
            await db.execute(text("DELETE FROM knowledge_chunks WHERE page_id = :pid"), {"pid": page_id})
        else:
            await db.execute(text("UPDATE knowledge_pages SET status = :st WHERE id = :pid"), {"st": status, "pid": page_id})
            return page_id
    else:
        res = await db.execute(
            text("INSERT INTO knowledge_pages (business_id, sitemap_id, url, title, raw_markdown, content_hash, status) VALUES (:bid, :sid, :url, :t, :rm, :ch, :st) RETURNING id"),
            {"bid": business_id, "sid": sitemap_id, "url": url, "t": title[:500], "rm": raw_text, "ch": content_hash, "st": status},
        )
        page_id = str(res.scalar_one())

    chunks = chunk_text(raw_text)
    for idx, ch in enumerate(chunks):
        emb = await get_embedding(ch)
        vec_literal = "[" + ",".join(str(x) for x in emb) + "]"
        await db.execute(
            text("INSERT INTO knowledge_chunks (business_id, page_id, chunk_index, content, metadata_json, embedding) VALUES (:bid, :pid, :idx, :content, CAST(:meta AS jsonb), CAST(:emb AS halfvec))"),
            {
                "bid": business_id,
                "pid": page_id,
                "idx": idx,
                "content": ch,
                "meta": json.dumps({"url": url, "title": title, "status": status}),
                "emb": vec_literal,
            },
        )
    return page_id

async def crawl_website(db: AsyncSession, business_id: str, root_url: str, max_pages: int = 8) -> int:
    prev = await preview_sitemap(root_url)
    s_res = await db.execute(
        text("INSERT INTO sitemaps (business_id, root_url, status, last_crawled_at) VALUES (:bid, :u, 'crawled', now()) RETURNING id"),
        {"bid": business_id, "u": root_url},
    )
    sitemap_id = str(s_res.scalar_one())
    indexed_count = 0
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=False, headers={"User-Agent": "AICustomerExpertBot/1.0"}) as client:
        for current in prev["urls"][:max_pages]:
            try:
                resp = await client.get(current)
                if resp.status_code == 404:
                    await db.execute(text("UPDATE knowledge_pages SET status = 'watch' WHERE business_id = :bid AND url = :u"), {"bid": business_id, "u": current})
                    continue
                if resp.status_code in (301, 302) and resp.headers.get("location"):
                    new_url = urljoin(current, resp.headers["location"])
                    await db.execute(text("UPDATE knowledge_pages SET status = 'quarantined' WHERE business_id = :bid AND url = :u"), {"bid": business_id, "u": current})
                    resp = await client.get(new_url)
                    current = new_url
                if resp.status_code != 200 or "text/html" not in resp.headers.get("content-type", ""):
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")
                img_alts = [img.get("alt", "").strip() for img in soup.find_all("img") if img.get("alt")]
                for tag in soup(["script", "style", "nav", "footer", "noscript"]):
                    tag.decompose()
                title = (soup.title.string.strip() if soup.title and soup.title.string else current)
                body_text = soup.get_text(separator=" ", strip=True)
                if img_alts:
                    body_text += "\n[Screenshot Captions]: " + " | ".join(img_alts[:10])
                if len(body_text) > 40:
                    await index_page_content(db, business_id, current, title, body_text, sitemap_id, status="active")
                    indexed_count += 1
            except Exception:
                continue
    return indexed_count

async def hybrid_search(db: AsyncSession, business_id: str, query: str, top_k: int = 5) -> list[dict]:
    emb = await get_embedding(query)
    vec_literal = "[" + ",".join(str(x) for x in emb) + "]"
    sql = text("""
        WITH vec AS (
            SELECT kc.id, ROW_NUMBER() OVER (ORDER BY kc.embedding <=> CAST(:emb AS halfvec)) AS rank_v
            FROM knowledge_chunks kc
            LEFT JOIN knowledge_pages kp ON kc.page_id = kp.id
            WHERE kc.business_id = :bid AND kc.embedding IS NOT NULL
              AND COALESCE(kp.status, 'active') NOT IN ('quarantined', 'archived')
            LIMIT 25
        ),
        kw AS (
            SELECT kc.id, ROW_NUMBER() OVER (ORDER BY ts_rank_cd(kc.search_tsv, plainto_tsquery('english', :q)) DESC) AS rank_k
            FROM knowledge_chunks kc
            LEFT JOIN knowledge_pages kp ON kc.page_id = kp.id
            WHERE kc.business_id = :bid AND kc.search_tsv @@ plainto_tsquery('english', :q)
              AND COALESCE(kp.status, 'active') NOT IN ('quarantined', 'archived')
            LIMIT 25
        )
        SELECT kc.id, kc.content, kc.metadata_json,
               COALESCE(1.0 / (60 + vec.rank_v), 0.0) + COALESCE(1.0 / (60 + kw.rank_k), 0.0) AS rrf_score
        FROM knowledge_chunks kc
        LEFT JOIN vec ON kc.id = vec.id
        LEFT JOIN kw ON kc.id = kw.id
        WHERE kc.business_id = :bid AND (vec.id IS NOT NULL OR kw.id IS NOT NULL)
        ORDER BY rrf_score DESC
        LIMIT :k
    """)
    rows = (await db.execute(sql, {"bid": business_id, "emb": vec_literal, "q": query, "k": top_k})).mappings().all()
    return [dict(r) for r in rows]