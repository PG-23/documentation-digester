"""
Ingestion pipeline: .txt files + manifest -> chunks -> embeddings -> ChromaDB.

Run from the repo root:
    python -m ingest.ingest                    # add/update every .txt in data/docs
    python -m ingest.ingest --reset            # wipe the collection first, then ingest
    python -m ingest.ingest --chunker semantic # use the semantic chunker in ingest/chunking.py

Shared settings (the API must use the same DB_PATH, COLLECTION and MODEL_NAME):
    DB_PATH     = chroma_db/
    COLLECTION  = godot_docs
    MODEL_NAME  = sentence-transformers/all-MiniLM-L6-v2
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "data" / "docs"
MANIFEST_PATH = ROOT / "data" / "manifest.json"
DB_PATH = ROOT / "chroma_db"
COLLECTION = "godot_docs"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

CHUNK_SIZE = 800      # characters
CHUNK_OVERLAP = 100   # characters


# ---------------------------------------------------------------------------
# 1. Load
# ---------------------------------------------------------------------------
def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    """Read manifest.json: {"file.txt": {"title": ..., "section": ..., "url": ...}}."""
    if not path.exists():
        print(f"WARNING: no manifest at {path}; titles will come from file names.")
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_document(path: Path, manifest: dict) -> dict | None:
    """Read one .txt file and attach its manifest metadata."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        print(f"WARNING: {path.name} is empty; skipping.")
        return None

    meta = manifest.get(path.name)
    if meta is None:
        print(f"WARNING: {path.name} is not in manifest.json; using defaults.")
        meta = {}

    # Chroma metadata values cannot be None, so every field gets a string.
    return {
        "source_file": path.name,
        "text": text,
        "title": meta.get("title") or path.stem.replace("_", " ").title(),
        "section": meta.get("section") or "",
        "url": meta.get("url") or "",
    }


def load_documents(docs_dir: Path = DOCS_DIR, manifest: dict | None = None) -> list[dict]:
    """Load every .txt file in docs_dir."""
    if manifest is None:
        manifest = load_manifest()
    docs = []
    for path in sorted(docs_dir.glob("*.txt")):
        doc = load_document(path, manifest)
        if doc:
            docs.append(doc)
    return docs


# ---------------------------------------------------------------------------
# 2. Chunk
# ---------------------------------------------------------------------------
# A chunker is any function: text (str) -> list of chunk strings.
# The semantic chunker in ingest/chunking.py must follow the same signature.

def length_chunker(text: str) -> list[str]:
    """Split by length, preferring paragraph and sentence boundaries."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    return splitter.split_text(text)


def get_chunker(name: str):
    if name == "length":
        return length_chunker
    if name == "semantic":
        try:
            from ingest.chunking import semantic_chunker  # provided by the Chunking role
        except ImportError:
            raise SystemExit(
                "Semantic chunking isn't available yet: ingest/chunking.py must define "
                "semantic_chunker(text: str) -> list[str]. Use --chunker length for now."
            )
        return semantic_chunker
    raise ValueError(f"Unknown chunker: {name!r} (use 'length' or 'semantic')")


def chunk_document(doc: dict, chunker, chunker_name: str) -> list[dict]:
    """Split one document and give every chunk a stable ID and full metadata."""
    chunks = []
    for i, piece in enumerate(chunker(doc["text"])):
        piece = piece.strip()
        if not piece:
            continue
        chunks.append({
            "id": f"{doc['source_file']}::{i}",   # stable: same file + index -> same ID
            "text": piece,
            "metadata": {
                "title": doc["title"],
                "section": doc["section"],
                "url": doc["url"],
                "source_file": doc["source_file"],
                "chunk_index": i,
                "chunker": chunker_name,
            },
        })
    return chunks


# ---------------------------------------------------------------------------
# 3. Embed
# ---------------------------------------------------------------------------
_model = None


def get_model():
    """Load the embedding model once and reuse it."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed(texts: list[str], model=None) -> list[list[float]]:
    model = model or get_model()
    vectors = model.encode(
        texts, batch_size=32, show_progress_bar=len(texts) > 32,
        normalize_embeddings=True,
    )
    return vectors.tolist()


# ---------------------------------------------------------------------------
# 4. Store
# ---------------------------------------------------------------------------
def get_collection(reset: bool = False):
    import chromadb

    client = chromadb.PersistentClient(path=str(DB_PATH))
    if reset:
        try:
            client.delete_collection(COLLECTION)
            print(f"Reset: deleted collection '{COLLECTION}'.")
        except Exception:
            pass  # collection did not exist yet
    return client.get_or_create_collection(
        COLLECTION, metadata={"hnsw:space": "cosine"}
    )


def store_document_chunks(collection, source_file: str, chunks: list[dict],
                          embeddings: list[list[float]]) -> None:
    """Replace all chunks for one file. Deleting first removes leftover chunks
    if the file now produces fewer chunks than before (e.g. after a chunker change)."""
    collection.delete(where={"source_file": source_file})
    collection.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        embeddings=embeddings,
        metadatas=[c["metadata"] for c in chunks],
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def ingest_documents(docs: list[dict], collection, chunker_name: str = "length",
                     model=None) -> dict:
    """Chunk, embed and store a list of loaded documents. Returns stats.
    The /ingest API endpoint can call this with a single document."""
    chunker = get_chunker(chunker_name)
    model = model or get_model()
    stats = {"files": 0, "chunks": 0, "chunk_s": 0.0, "embed_s": 0.0, "store_s": 0.0}

    for doc in docs:
        t0 = time.perf_counter()
        chunks = chunk_document(doc, chunker, chunker_name)
        t1 = time.perf_counter()
        if not chunks:
            print(f"  {doc['source_file']:<32} no chunks; skipped")
            continue
        vectors = embed([c["text"] for c in chunks], model)
        t2 = time.perf_counter()
        store_document_chunks(collection, doc["source_file"], chunks, vectors)
        t3 = time.perf_counter()

        stats["files"] += 1
        stats["chunks"] += len(chunks)
        stats["chunk_s"] += t1 - t0
        stats["embed_s"] += t2 - t1
        stats["store_s"] += t3 - t2
        print(f"  {doc['source_file']:<32} {len(chunks):>4} chunks  ({t3 - t0:.2f}s)")

    return stats


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Ingest Godot docs into ChromaDB.")
    parser.add_argument("--reset", action="store_true",
                        help="delete the collection before ingesting")
    parser.add_argument("--chunker", choices=["length", "semantic"], default="length")
    parser.add_argument("--docs", type=Path, default=DOCS_DIR,
                        help="folder of .txt files (default: data/docs)")
    args = parser.parse_args(argv)

    start = time.perf_counter()
    print(f"Collection: {COLLECTION}  |  DB: {DB_PATH}  |  chunker: {args.chunker}")

    docs = load_documents(args.docs)
    print(f"Loaded {len(docs)} documents from {args.docs}")
    if not docs:
        return

    t = time.perf_counter()
    print(f"Loading embedding model {MODEL_NAME} ...")
    model = get_model()
    print(f"Model ready ({time.perf_counter() - t:.1f}s)")

    collection = get_collection(reset=args.reset)
    stats = ingest_documents(docs, collection, args.chunker, model)

    total = time.perf_counter() - start
    print("-" * 60)
    print(f"Ingested {stats['files']} files -> {stats['chunks']} chunks")
    print(f"Time: chunk {stats['chunk_s']:.2f}s | embed {stats['embed_s']:.2f}s | "
          f"store {stats['store_s']:.2f}s | total {total:.2f}s")
    print(f"Collection '{COLLECTION}' now holds {collection.count()} chunks.")


if __name__ == "__main__":
    main()