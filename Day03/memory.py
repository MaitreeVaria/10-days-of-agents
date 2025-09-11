# Day03/memory.py
import os, time
from typing import List
from dotenv import load_dotenv
load_dotenv()

from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

MEM_INDEX_DIR = os.path.join(os.path.dirname(__file__), "mem_index")
MEM_COLLECTION = "day03_semantic"

class SemanticMemory:
    def __init__(self):
        os.makedirs(MEM_INDEX_DIR, exist_ok=True)
        self.emb = OpenAIEmbeddings()
        self.db = Chroma(
            collection_name=MEM_COLLECTION,
            persist_directory=MEM_INDEX_DIR,
            embedding_function=self.emb,
        )

    def count(self) -> int:
        # quick sanity check helper (optional)
        try:
            return self.db._collection.count()  # works with chroma client used by LC
        except Exception:
            return 0

    def add(self, text: str, tags=None, confidence: float = 0.7):
        text = (text or "").strip()
        if not text:
            return

        # Ensure primitives-only metadata
        if tags is None:
            tags_str = ""
        elif isinstance(tags, (list, tuple)):
            # Option A: comma-separated
            tags_str = ",".join(map(str, tags))
            # Option B (alternative): JSON string
            # tags_str = json.dumps(list(tags))
        else:
            tags_str = str(tags)

        meta = {
            "tags": tags_str,               # <-- primitive string
            "confidence": float(confidence),
            "created_at": int(time.time()),
        }
        self.db.add_texts([text], metadatas=[meta])

    def search(self, query: str, k: int = 3) -> list[str]:
        query = (query or "").strip()
        if not query:
            return []
        docs = self.db.similarity_search(query, k=max(1, int(k)))
        return [d.page_content for d in docs]
