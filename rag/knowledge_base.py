from pathlib import Path
from langchain_chroma import Chroma
try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document

_EMBED_MODEL = "BAAI/bge-small-zh-v1.5"
_DB_DIR      = str(Path(__file__).parent.parent / "data" / "chroma_db")
_COLLECTION  = "mold_knowledge"

_embeddings: HuggingFaceEmbeddings | None = None


def _get_embeddings() -> HuggingFaceEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(
            model_name=_EMBED_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    return _embeddings


def get_vector_store() -> Chroma:
    return Chroma(
        collection_name=_COLLECTION,
        embedding_function=_get_embeddings(),
        persist_directory=_DB_DIR,
    )


def search_knowledge(query: str, k: int = 3) -> list[Document]:
    vs = get_vector_store()
    return vs.max_marginal_relevance_search(query, k=k, fetch_k=k * 3)


def add_documents(docs: list[Document]) -> int:
    vs = get_vector_store()
    vs.add_documents(docs)
    return len(docs)


def get_stats() -> dict:
    vs  = get_vector_store()
    col = vs._collection
    return {
        "total":      col.count(),
        "db_path":    _DB_DIR,
        "embed_model": _EMBED_MODEL,
    }
