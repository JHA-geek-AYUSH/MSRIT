"""
Seed real Indian legal data from Indian Kanoon into Qdrant + PostgreSQL.

Usage:
    cd backend
    python seed_legal_data.py

Fetches landmark cases across key Indian legal domains and indexes them
so the agents have real context to work with.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import httpx
from dotenv import load_dotenv
load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

IK_TOKEN = os.getenv("INDIAN_KANOON_API_TOKEN", "")
IK_BASE  = os.getenv("INDIAN_KANOON_BASE_URL", "https://api.indiankanoon.org").rstrip("/")
DB_URL   = os.getenv("DATABASE_URL", "")
QDRANT_URL        = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "gemmaFin_chunks")
EMBED_MODEL       = os.getenv("EMBEDDING_MODEL", "all-mpnet-base-v2")

# Key Indian legal queries to seed — covers major practice areas
SEED_QUERIES = [
    # Constitutional
    ("fundamental rights article 21 right to life personal liberty", "supremecourt"),
    ("article 14 equality before law reasonable classification", "supremecourt"),
    ("freedom of speech article 19 reasonable restrictions", "supremecourt"),
    # Criminal
    ("bail section 437 crpc non-bailable offence conditions", "supremecourt"),
    ("section 302 ipc murder culpable homicide punishment", "supremecourt"),
    ("anticipatory bail section 438 crpc guidelines", "supremecourt"),
    # Civil / Contract
    ("breach of contract damages specific performance", "supremecourt"),
    ("limitation act 1963 period of limitation civil suit", "supremecourt"),
    ("injunction temporary permanent grounds civil procedure", "supremecourt"),
    # Property / Family
    ("hindu succession act women property rights ancestral", "supremecourt"),
    ("maintenance section 125 crpc wife children parents", "supremecourt"),
    ("transfer of property act sale deed registration", "supremecourt"),
    # Corporate / Commercial
    ("insolvency bankruptcy code 2016 corporate resolution process", "supremecourt"),
    ("companies act director liability winding up", "supremecourt"),
    # Labour
    ("industrial disputes act retrenchment compensation workman", "supremecourt"),
    ("minimum wages act payment wages labour law", "supremecourt"),
    # Consumer
    ("consumer protection act deficiency in service compensation", "supremecourt"),
    # Tax
    ("income tax act assessment penalty evasion", "supremecourt"),
    ("gst goods services tax input tax credit", "supremecourt"),
    # High Court landmark
    ("habeas corpus detention illegal fundamental rights", "delhi"),
    ("dowry prohibition act section 498a cruelty wife", "delhi"),
]

HEADERS = {
    "Authorization": f"Token {IK_TOKEN}",
    "Accept": "application/json",
}

# ── Embedding ─────────────────────────────────────────────────────────────────

def get_embedding(text: str) -> Optional[List[float]]:
    """Generate embedding using sentence-transformers (local, free)."""
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(EMBED_MODEL)
        vec = model.encode(text[:512], normalize_embeddings=True)
        return vec.tolist()
    except ImportError:
        print("  [!] sentence-transformers not installed. Run: pip install sentence-transformers")
        return None
    except Exception as e:
        print(f"  [!] Embedding error: {e}")
        return None

# ── Qdrant ────────────────────────────────────────────────────────────────────

def ensure_qdrant_collection(vector_size: int = 768):
    """Create Qdrant collection if it doesn't exist."""
    import requests
    try:
        r = requests.get(f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}", timeout=5)
        if r.status_code == 200:
            print(f"  [✓] Qdrant collection '{QDRANT_COLLECTION}' already exists")
            return True
        # Create it
        payload = {
            "vectors": {
                "size": vector_size,
                "distance": "Cosine"
            }
        }
        r = requests.put(f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}", json=payload, timeout=10)
        if r.status_code in (200, 201):
            print(f"  [✓] Created Qdrant collection '{QDRANT_COLLECTION}' (dim={vector_size})")
            return True
        print(f"  [!] Failed to create collection: {r.text}")
        return False
    except Exception as e:
        print(f"  [!] Qdrant error: {e}")
        return False


def upsert_to_qdrant(points: List[Dict[str, Any]]) -> bool:
    """Upsert points into Qdrant."""
    import requests
    try:
        r = requests.put(
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points",
            json={"points": points},
            timeout=30,
        )
        return r.status_code in (200, 201)
    except Exception as e:
        print(f"  [!] Qdrant upsert error: {e}")
        return False

# ── PostgreSQL ────────────────────────────────────────────────────────────────

async def get_db_conn():
    """Get asyncpg connection."""
    import asyncpg
    url = DB_URL.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")
    return await asyncpg.connect(url, timeout=15)


async def upsert_authority(conn, doc: Dict[str, Any]) -> Optional[str]:
    """Insert authority into PostgreSQL, return its UUID."""
    try:
        docid = str(doc.get("docid", ""))
        title = (doc.get("title") or "Unknown")[:500]
        court = _map_court(doc.get("court", ""))
        neutral_cite = (doc.get("citation") or "")[:200]
        date_val = _parse_date(doc.get("date"))
        url = doc.get("url") or f"https://indiankanoon.org/doc/{docid}/"
        content_hash = hashlib.sha256(f"{docid}{title}".encode()).hexdigest()[:64]

        row = await conn.fetchrow(
            "SELECT id FROM authorities WHERE hash_keccak256 = $1", content_hash
        )
        if row:
            return str(row["id"])

        auth_id = str(uuid.uuid4())
        await conn.execute("""
            INSERT INTO authorities (id, court, title, neutral_cite, date, url,
                                     storage_path, hash_keccak256, metadata_json)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            ON CONFLICT DO NOTHING
        """, auth_id, court, title, neutral_cite, date_val, url,
            f"ik/{docid}", content_hash, '{}')
        return auth_id
    except Exception as e:
        print(f"    [!] DB upsert error: {e}")
        return None


async def upsert_chunk(conn, authority_id: str, text: str, para: int, vector_id: str) -> bool:
    """Insert chunk into PostgreSQL."""
    try:
        await conn.execute("""
            INSERT INTO chunks (id, authority_id, para_from, para_to, text, tokens, vector_id,
                                statute_tags, has_citation)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            ON CONFLICT DO NOTHING
        """, str(uuid.uuid4()), authority_id, para, para, text[:2000],
            len(text.split()), vector_id, '{}', False)
        return True
    except Exception as e:
        print(f"    [!] Chunk upsert error: {e}")
        return False

# ── Indian Kanoon ─────────────────────────────────────────────────────────────

async def fetch_ik_results(query: str, doctype: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """Fetch search results from Indian Kanoon."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                f"{IK_BASE}/search/",
                data={"formInput": query, "pagenum": 0, "doctypes": doctype},
                headers=HEADERS,
            )
            r.raise_for_status()
            data = r.json()
            results = data.get("results", [])[:max_results]
            # Normalize
            for res in results:
                res["url"] = f"https://indiankanoon.org/doc/{res.get('docid')}/"
            return results
    except Exception as e:
        print(f"  [!] IK search failed for '{query[:40]}': {e}")
        return []


async def fetch_ik_doc(docid: int) -> Optional[str]:
    """Fetch document text from Indian Kanoon."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{IK_BASE}/doc/{docid}/", headers=HEADERS)
            r.raise_for_status()
            data = r.json()
            # Extract text from doc field
            text = data.get("doc", "") or data.get("judgment", "") or ""
            # Strip HTML tags
            import re
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:3000] if text else None
    except Exception:
        return None

# ── Helpers ───────────────────────────────────────────────────────────────────

def _map_court(court_str: str) -> str:
    s = court_str.upper()
    if "SUPREME" in s:
        return "SC"
    if "DELHI" in s:
        return "HC-DEL"
    if "BOMBAY" in s:
        return "HC-BOM"
    if "MADRAS" in s:
        return "HC-MAD"
    if "CALCUTTA" in s:
        return "HC-CAL"
    if "ALLAHABAD" in s:
        return "HC-ALL"
    if "KARNATAKA" in s:
        return "HC-KAR"
    if "KERALA" in s:
        return "HC-KER"
    if "GUJARAT" in s:
        return "HC-GUJ"
    if "TRIBUNAL" in s:
        return "TRIBUNAL"
    return "UNKNOWN"


def _parse_date(date_str: Any) -> Optional[datetime]:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y"):
        try:
            return datetime.strptime(str(date_str)[:10], fmt)
        except ValueError:
            continue
    return None

# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    print("\n🇮🇳  GemmaFinOS Indian Legal Data Seeder")
    print("=" * 50)

    if not IK_TOKEN:
        print("[✗] INDIAN_KANOON_API_TOKEN not set in .env")
        return

    # Check Qdrant
    print("\n[1] Checking Qdrant...")
    import requests as _req
    try:
        _req.get(f"{QDRANT_URL}/healthz", timeout=3).raise_for_status()
        print("  [✓] Qdrant is running")
    except Exception:
        print("  [✗] Qdrant is not running. Start it with: cd infra && docker-compose up -d qdrant")
        return

    # Get embedding dimension
    print("\n[2] Loading embedding model (first run downloads ~420MB)...")
    sample_vec = get_embedding("test")
    if not sample_vec:
        return
    vec_dim = len(sample_vec)
    print(f"  [✓] Embedding model ready (dim={vec_dim})")

    # Ensure collection
    print("\n[3] Ensuring Qdrant collection...")
    if not ensure_qdrant_collection(vec_dim):
        return

    # Connect to DB
    print("\n[4] Connecting to PostgreSQL...")
    try:
        conn = await get_db_conn()
        print("  [✓] Connected")
    except Exception as e:
        print(f"  [✗] DB connection failed: {e}")
        print("  Make sure PostgreSQL is running and DATABASE_URL is correct in .env")
        return

    # Seed data
    print(f"\n[5] Fetching {len(SEED_QUERIES)} legal topic areas from Indian Kanoon...\n")
    total_docs = 0
    total_chunks = 0

    for query, doctype in SEED_QUERIES:
        print(f"  → {query[:60]}...")
        results = await fetch_ik_results(query, doctype, max_results=5)
        if not results:
            print("    (no results)")
            continue

        qdrant_points = []
        for doc in results:
            docid = doc.get("docid")
            if not docid:
                continue

            # Upsert authority to PostgreSQL
            auth_id = await upsert_authority(conn, doc)
            if not auth_id:
                continue

            # Get document text (snippet or full)
            text = doc.get("snippet") or doc.get("headnote") or ""
            import re
            text = re.sub(r'<[^>]+>', ' ', text).strip()

            if len(text) < 100:
                # Try fetching full doc
                full_text = await fetch_ik_doc(docid)
                if full_text:
                    text = full_text

            if not text:
                text = f"{doc.get('title', '')} - {doc.get('citation', '')}"

            # Generate embedding
            vec = get_embedding(text[:512])
            if not vec:
                continue

            vector_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ik-{docid}"))

            # Upsert chunk to PostgreSQL
            await upsert_chunk(conn, auth_id, text, 1, vector_id)

            # Prepare Qdrant point
            qdrant_points.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, vector_id)),
                "vector": vec,
                "payload": {
                    "chunk_id": vector_id,
                    "authority_id": auth_id,
                    "docid": str(docid),
                    "title": doc.get("title", ""),
                    "court": _map_court(doc.get("court", "")),
                    "citation": doc.get("citation", ""),
                    "text": text[:500],
                    "para_from": 1,
                    "para_to": 1,
                    "source": "indian_kanoon",
                }
            })
            total_docs += 1

        if qdrant_points:
            ok = upsert_to_qdrant(qdrant_points)
            total_chunks += len(qdrant_points)
            status = "✓" if ok else "✗"
            print(f"    [{status}] Indexed {len(qdrant_points)} docs")

        await asyncio.sleep(0.5)  # Rate limit

    await conn.close()

    print(f"\n{'='*50}")
    print(f"✅  Seeding complete!")
    print(f"   Documents indexed : {total_docs}")
    print(f"   Qdrant points     : {total_chunks}")
    print(f"\nRestart the backend and try a legal query like:")
    print('   "What are the bail conditions under Section 437 CrPC?"')
    print('   "What are a woman\'s rights in ancestral property under Hindu Succession Act?"')
    print()


if __name__ == "__main__":
    asyncio.run(main())
