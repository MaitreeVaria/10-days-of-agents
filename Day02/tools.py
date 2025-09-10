from langchain_tavily import TavilySearch

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

import os
from dotenv import load_dotenv
load_dotenv()

def web_search(searchString: str) -> dict:
    """Search the web using Tavily and return top results (title + URL)."""
    try:
        tavily = TavilySearch(
            max_results=2,
            topic="general",
            include_raw_content=False,
            search_depth="basic",
        )
        values = tavily.invoke(searchString)
        # Case: Tavily gave a dict with structured results
        if isinstance(values, dict) and "results" in values:
            clean = [
                {"title": r.get("title"), "url": r.get("url")}
                for r in values["results"]
                if isinstance(r, dict)
            ]
            return {"ok": True, "results": clean}

        # Case: Tavily just gave a string or something else
        return {"ok": True, "text": str(values)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
INDEX_DIR = os.path.join(os.path.dirname(__file__), "index")
COLLECTION_NAME = "day02_docs"

# ---- Helpers ----------------------------------------------------------------
def _load_documents() -> list:
    """Load PDFs and Markdown files from DATA_DIR into LangChain Document objects.
    Keeps metadata: source (filename), and page for PDFs.
    """
    docs = []

    # 1) PDFs
    for name in os.listdir(DATA_DIR):
        if name.lower().endswith(".pdf"):
            pdf_path = os.path.join(DATA_DIR, name)
            try:
                loader = PyPDFLoader(pdf_path)
                pdf_docs = loader.load()  # one Document per page with metadata["page"]
                # Normalize 'source' to filename only (nicer citations)
                for d in pdf_docs:
                    d.metadata["source"] = name
                    raw_page = d.metadata.get("page", 0)  # may be 0-based
                    try:
                        d.metadata["page"] = int(raw_page) + 1
                    except Exception:
                        d.metadata["page"] = None
            except Exception as e:
                print(f"[warn] failed to load PDF {name}: {e}")

    # 2) Markdown / text
    for name in os.listdir(DATA_DIR):
        if name.lower().endswith((".md", ".txt")):
            md_path = os.path.join(DATA_DIR, name)
            try:
                loader = TextLoader(md_path, encoding="utf-8")
                md_docs = loader.load()  # one Document for the whole file
                for d in md_docs:
                    d.metadata["source"] = name
                    d.metadata["page"] = None
                docs.extend(md_docs)
            except Exception as e:
                print(f"[warn] failed to load text {name}: {e}")

    return docs

def _split_documents(docs: list):
    """Split documents into overlapping chunks for better retrieval."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,      # ~800 characters per chunk
        chunk_overlap=120,   # ~120 characters overlap (keeps context)
        length_function=len, # simple char length
    )
    return splitter.split_documents(docs)

def _get_embeddings():
    """Embedding function that turns text into vectors."""
    return OpenAIEmbeddings()  # uses OPENAI_API_KEY from env

def _get_vectorstore(embeddings):
    """Open (or create) a persistent Chroma collection."""
    os.makedirs(INDEX_DIR, exist_ok=True)
    vs = Chroma(
        collection_name=COLLECTION_NAME,
        persist_directory=INDEX_DIR,
        embedding_function=embeddings,
    )
    return vs

def doc_ingest() -> dict:
    """Load files from data/, chunk, embed, and persist to Chroma.
    Returns simple stats so you can see what happened.
    """
    try:
        # 1) Load
        docs = _load_documents()
        files_seen = sorted({d.metadata.get("source") for d in docs})
        # 2) Chunk
        chunks = _split_documents(docs)
        # 3) Embed + Upsert
        embeddings = _get_embeddings()
        vectordb = _get_vectorstore(embeddings)

        # NOTE: add_texts expects parallel arrays of texts and metadatas
        texts = [d.page_content for d in chunks]
        metadatas = [d.metadata for d in chunks]
        if texts:
            vectordb.add_texts(texts=texts, metadatas=metadatas)
            # vectordb.persist()

        return {
            "ok": True,
            "files_indexed": len(files_seen),
            "chunks_added": len(texts),
            "files": files_seen,
            "index_dir": INDEX_DIR,
            "collection": COLLECTION_NAME,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

# --- QUERY PIPELINE -----------------------------------------------------------
from typing import Dict, Any, List

def _open_vectorstore():
    """Reopen the same Chroma collection we wrote during ingest."""
    embeddings = _get_embeddings()
    return _get_vectorstore(embeddings)

def _short(text: str, n: int = 240) -> str:
    return (text or "").replace("\n", " ").strip()[:n]

def doc_query(question: str, top_k: int = 4) -> Dict[str, Any]:
    """Retrieve top-k chunks relevant to the question with citations."""
    try:
        if not isinstance(question, str) or not question.strip():
            return {"ok": False, "error": "Empty question"}

        vectordb = _open_vectorstore()
        # similarity_search_with_score returns (Document, score)
        hits: List = vectordb.similarity_search_with_score(question, k=max(1, int(top_k)))

        results = []
        for doc, score in hits:
            md = doc.metadata or {}
            results.append({
                "source": md.get("source"),
                "page": md.get("page"),
                "snippet": _short(doc.page_content),
                "score": float(score) if score is not None else None,
            })

        return {"ok": True, "results": results}
    except Exception as e:
        return {"ok": False, "error": str(e)}