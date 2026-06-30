import asyncio
import uuid
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor

from app.utils.logger import logger

_executor = ThreadPoolExecutor(max_workers=2)
_vector_store = None
_document_chunks: dict = {}


def _extract_text_from_pdf(pdf_bytes: bytes) -> tuple:
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = "".join(page.get_text() for page in doc)
        page_count = len(doc)
        doc.close()
        return text.strip(), page_count
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        return "", 0


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk:
            chunks.append(chunk)
    return chunks


def _embed_and_store(doc_id: str, chunks: List[str]) -> bool:
    global _vector_store
    try:
        from sentence_transformers import SentenceTransformer
        import faiss
        import numpy as np

        model = SentenceTransformer("all-MiniLM-L6-v2")
        embeddings = model.encode(chunks, show_progress_bar=False).astype(np.float32)
        dim = embeddings.shape[1]

        if _vector_store is None:
            _vector_store = faiss.IndexFlatL2(dim)

        start_idx = _vector_store.ntotal
        _vector_store.add(embeddings)

        for i, chunk in enumerate(chunks):
            _document_chunks[start_idx + i] = {"doc_id": doc_id, "text": chunk}

        return True
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        return False


def _search_similar(query: str, top_k: int = 5) -> List[dict]:
    global _vector_store
    if not _vector_store or _vector_store.ntotal == 0:
        return []
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np

        model = SentenceTransformer("all-MiniLM-L6-v2")
        query_emb = model.encode([query]).astype(np.float32)
        distances, indices = _vector_store.search(query_emb, min(top_k, _vector_store.ntotal))

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx in _document_chunks:
                results.append({
                    "text": _document_chunks[idx]["text"],
                    "doc_id": _document_chunks[idx]["doc_id"],
                    "score": float(1 / (1 + dist)),
                })
        return sorted(results, key=lambda x: x["score"], reverse=True)
    except Exception as e:
        logger.error(f"FAISS search failed: {e}")
        return []


async def process_pdf(pdf_bytes: bytes) -> dict:
    doc_id = str(uuid.uuid4())
    loop = asyncio.get_event_loop()

    text, page_count = await loop.run_in_executor(_executor, _extract_text_from_pdf, pdf_bytes)
    if not text:
        return {"doc_id": doc_id, "text": "", "page_count": 0, "chunks": 0, "success": False}

    chunks = _chunk_text(text)
    success = await loop.run_in_executor(_executor, _embed_and_store, doc_id, chunks)

    return {"doc_id": doc_id, "text": text, "page_count": page_count, "chunks": len(chunks), "success": success}


async def rag_query(query: str, doc_ids: Optional[List[str]] = None, language: str = "en") -> dict:
    loop = asyncio.get_event_loop()
    sources = await loop.run_in_executor(_executor, _search_similar, query, 5)

    if doc_ids:
        sources = [s for s in sources if s["doc_id"] in doc_ids]

    if not sources:
        return {"answer": "No relevant content found. Please upload related documents first.", "sources": [], "confidence": 0.0}

    context = "\n\n".join([f"Source {i+1}: {s['text']}" for i, s in enumerate(sources[:3])])

    from app.services.ai.chat_service import _get_llm_response
    prompt = f"""Based ONLY on the following context, answer the question clearly.
Context:
{context}
Question: {query}
Language: {language}"""

    messages = [
        {"role": "system", "content": "You are a precise Q&A assistant. Answer only from the provided context."},
        {"role": "user", "content": prompt},
    ]

    answer, _ = await _get_llm_response(messages)
    avg_confidence = sum(s["score"] for s in sources[:3]) / min(3, len(sources))

    return {
        "answer": answer,
        "sources": [{"text": s["text"][:200] + "...", "doc_id": s["doc_id"], "score": s["score"]} for s in sources[:3]],
        "confidence": round(avg_confidence, 3),
    }
