"""
Ingestion pipeline: .txt files + manifest -> chunks -> embeddings -> ChromaDB.

Run from the repo root:
    python -m ingest.ingest                     # add/update every .txt in data/docs
    python -m ingest.ingest --reset             # wipe the collection first, then ingest
    python -m ingest.ingest --file PATH.txt     # ingest one file (live upload demo)
    python -m ingest.ingest --stats             # show what's in the collection; changes nothing
    python -m ingest.ingest --chunker semantic  # use the semantic chunker in ingest/chunking.py

Text files may start with a header (the data prep format):
    TITLE: ...
    SOURCE: <url>
    CATEGORY: ...
    CONTENT:
    <page text>
The header is removed before chunking. Metadata comes from manifest.json first,
then from the header, then from defaults.

Shared settings (the API must use the same DB_PATH, COLLECTION and MODEL_NAME):
    DB_PATH     = chroma_db/
    COLLECTION  = godot_docs
    MODEL_NAME  = sentence-transformers/all-MiniLM-L6-v2

For the Search API's POST /ingest, call:
    ingest_text(text, source_file, title=None, section=None, url=None)
"""

from __future__ import annotations

import argparse
import json
import os
import time
import warnings
from pathlib import Path

# Keep Hugging Face output quiet so demo output shows only our progress lines.
# These must be set before sentence_transformers / transformers are imported.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
warnings.filterwarnings("ignore", module="huggingface_hub")

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

HEADER_FIELDS = {"TITLE": "title", "SOURCE": "url", "CATEGORY": "section"}


# ---------------------------------------------------------------------------
# 1. Load
# ---------------------------------------------------------------------------
def load_manifest(path: Path | None = None) -> dict:
    """Read manifest.json: {"file.txt": {"title": ..., "section": ..., "url": ...}}."""
    path = path or MANIFEST_PATH
    if not path.exists():
        print(f"WARNING: no manifest at {path}; using file headers or defaults.")
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_header(raw: str) -> tuple[dict, str]:
    """Split a data-prep file into (header metadata, page content).
    Files without a CONTENT: line are returned unchanged with empty metadata."""
    if "CONTENT:" not in raw:
        return {}, raw.strip()
    head, content = raw.split("CONTENT:", 1)
    meta = {}
    for line in head.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip().upper() in HEADER_FIELDS:
            meta[HEADER_FIELDS[key.strip().upper()]] = value.strip()
    return meta, content.strip()


def make_document(raw: str, source_file: str, overrides: dict | None = None) -> dict | None:
    """Build a document dict from raw file text.
    Metadata priority: overrides (manifest or API form fields) > file header > defaults."""
    header, text = parse_header(raw)
    if not text:
        print(f"WARNING: {source_file} has no content; skipping.")
        return None
    overrides = {k: v for k, v in (overrides or {}).items() if v}

    def pick(field: str, default: str) -> str:
        return overrides.get(field) or header.get(field) or default

    # Chroma metadata values cannot be None, so every field gets a string.
    return {
        "source_file": source_file,
        "text": text,
        "title": pick("title", Path(source_file).stem.replace("_", " ").title()),
        "section": pick("section", ""),
        "url": pick("url", ""),
    }


def load_document(path: Path, manifest: dict) -> dict | None:
    """Read one .txt file and attach its metadata."""
    raw = path.read_text(encoding="utf-8")
    doc = make_document(raw, path.name, manifest.get(path.name))
    if doc and not doc["url"]:
        print(f"WARNING: {path.name} has no URL (not in manifest.json and no SOURCE: header).")
    return doc


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
        try:
            from transformers.utils import logging as hf_logging
            hf_logging.disable_progress_bar()
        except Exception:
            pass
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


def collection_stats(collection) -> dict[str, int]:
    """Chunk count per source file currently stored in the collection."""
    counts: dict[str, int] = {}
    for meta in collection.get(include=["metadatas"])["metadatas"]:
        name = (meta or {}).get("source_file", "?")
        counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items()))


def print_stats(collection) -> None:
    counts = collection_stats(collection)
    print(f"{COLLECTION}: {len(counts)} files, {sum(counts.values())} chunks")
    for name, n in counts.items():
        print(f"  {name:<40} {n:>4} chunks")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def ingest_document(doc: dict, collection, chunker_name: str = "length",
                    model=None) -> dict:
    """Chunk, embed and store one loaded document. Returns stats for that file."""
    chunker = get_chunker(chunker_name)
    model = model or get_model()

    t0 = time.perf_counter()
    chunks = chunk_document(doc, chunker, chunker_name)
    t1 = time.perf_counter()
    if not chunks:
        return {"source_file": doc["source_file"], "chunks": 0,
                "chunk_s": t1 - t0, "embed_s": 0.0, "store_s": 0.0}
    vectors = embed([c["text"] for c in chunks], model)
    t2 = time.perf_counter()
    store_document_chunks(collection, doc["source_file"], chunks, vectors)
    t3 = time.perf_counter()

    return {"source_file": doc["source_file"], "chunks": len(chunks),
            "chunk_s": t1 - t0, "embed_s": t2 - t1, "store_s": t3 - t2}


def ingest_documents(docs: list[dict], collection, chunker_name: str = "length",
                     model=None) -> dict:
    """Ingest a list of loaded documents, printing one line per file. Returns totals."""
    model = model or get_model()
    totals = {"files": 0, "chunks": 0, "chunk_s": 0.0, "embed_s": 0.0, "store_s": 0.0}
    for doc in docs:
        s = ingest_document(doc, collection, chunker_name, model)
        took = s["chunk_s"] + s["embed_s"] + s["store_s"]
        if not s["chunks"]:
            print(f"  {doc['source_file']:<40} no chunks; skipped")
            continue
        totals["files"] += 1
        for k in ("chunks", "chunk_s", "embed_s", "store_s"):
            totals[k] += s[k]
        print(f"  {doc['source_file']:<40} {s['chunks']:>4} chunks  ({took:.2f}s)")
    return totals


def ingest_text(text: str, source_file: str, title: str | None = None,
                section: str | None = None, url: str | None = None,
                collection=None, model=None, chunker_name: str = "length") -> dict:
    """Ingest one document from raw text (e.g. an uploaded file).

    `text` may include the TITLE/SOURCE/CATEGORY/CONTENT header; title/section/url
    arguments override the header when given. Re-ingesting the same source_file
    replaces its previous chunks.

    Returns: {"source_file", "title", "chunks", "seconds", "collection_total"}
    """
    start = time.perf_counter()
    doc = make_document(text, source_file,
                        {"title": title, "section": section, "url": url})
    if doc is None:
        raise ValueError(f"{source_file} has no content to ingest.")
    collection = collection or get_collection()
    s = ingest_document(doc, collection, chunker_name, model)
    return {
        "source_file": source_file,
        "title": doc["title"],
        "chunks": s["chunks"],
        "seconds": round(time.perf_counter() - start, 3),
        "collection_total": collection.count(),
    }


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
def load_model_verbose():
    t = time.perf_counter()
    print(f"Loading embedding model {MODEL_NAME} ...")
    model = get_model()
    print(f"Model ready ({time.perf_counter() - t:.1f}s)")
    return model


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Ingest Godot docs into ChromaDB.")
    parser.add_argument("--reset", action="store_true",
                        help="delete the collection before ingesting")
    parser.add_argument("--chunker", choices=["length", "semantic"], default="length")
    parser.add_argument("--docs", type=Path, default=DOCS_DIR,
                        help="folder of .txt files (default: data/docs)")
    parser.add_argument("--file", type=Path,
                        help="ingest a single .txt file instead of the whole folder")
    parser.add_argument("--stats", action="store_true",
                        help="show what's in the collection and exit")
    args = parser.parse_args(argv)

    if args.stats:
        print_stats(get_collection())
        return

    start = time.perf_counter()
    print(f"Collection: {COLLECTION}  |  DB: {DB_PATH}  |  chunker: {args.chunker}")

    if args.file:
        if not args.file.is_file():
            raise SystemExit(f"File not found: {args.file}")
        before = get_collection(reset=args.reset).count()
        model = load_model_verbose()
        raw = args.file.read_text(encoding="utf-8")
        manifest = load_manifest() if MANIFEST_PATH.exists() else {}
        m = manifest.get(args.file.name, {})
        result = ingest_text(raw, args.file.name, m.get("title"), m.get("section"),
                             m.get("url"), model=model, chunker_name=args.chunker)
        print("-" * 60)
        print(f"Uploaded {result['source_file']} ({result['title']}): "
              f"{result['chunks']} chunks in {result['seconds']:.2f}s")
        print(f"Collection '{COLLECTION}': {before} -> {result['collection_total']} chunks")
        return

    docs = load_documents(args.docs)
    print(f"Loaded {len(docs)} documents from {args.docs}")
    if not docs:
        return

    model = load_model_verbose()
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