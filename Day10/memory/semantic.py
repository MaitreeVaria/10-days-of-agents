import os, time
from typing import List
from dotenv import load_dotenv
load_dotenv()

from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma


MEM_INDEX_DIR = os.path.join(os.path.dirname(__file__), "index")
MEM_COLLECTION = "day10_semantic"


class SemanticMemory:
    def __init__(self):
        os.makedirs(MEM_INDEX_DIR, exist_ok=True)
        self.emb = OpenAIEmbeddings()
        self.db = Chroma(
            collection_name=MEM_COLLECTION,
            persist_directory=MEM_INDEX_DIR,
            embedding_function=self.emb,
        )

    def add(self, text: str, tags=None, confidence: float = 0.7):
        text = (text or "").strip()
        if not text:
            return

        if tags is None:
            tags_str = ""
        elif isinstance(tags, (list, tuple)):
            tags_str = ",".join(map(str, tags))
        else:
            tags_str = str(tags)

        meta = {
            "tags": tags_str,
            "confidence": float(confidence),
            "created_at": int(time.time()),
        }
        self.db.add_texts([text], metadatas=[meta])

    def search(self, query: str, k: int = 3) -> List[str]:
        query = (query or "").strip()
        if not query:
            return []
        docs = self.db.similarity_search(query, k=max(1, int(k)))
        return [d.page_content for d in docs]

    def clear_all(self) -> None:
        try:
            # delete all items from the underlying collection
            self.db._collection.delete(where={})
        except Exception:
            pass

    def count(self) -> int:
        try:
            return int(self.db._collection.count())
        except Exception:
            return 0

    def list_texts(self, limit: int = 100) -> List[str]:
        try:
            data = self.db._collection.get(include=["documents"]) or {}
            docs = data.get("documents") or []
            return list(docs)[: max(0, int(limit))]
        except Exception:
            return []


def clear_all_memory() -> None:
    try:
        SemanticMemory().clear_all()
    except Exception:
        pass


