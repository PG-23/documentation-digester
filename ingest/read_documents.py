from pathlib import Path
import json

# Find the main project directory
PROJECT_DIR = Path(__file__).resolve().parent.parent

# Locate the documentation and manifest files
DOCS_DIR = PROJECT_DIR / "data" / "docs"
MANIFEST_FILE = PROJECT_DIR / "data" / "manifest.json"


def read_documents():
    documents = []

    # Find all text files in the documentation folder
    for file_path in sorted(DOCS_DIR.glob("*.txt")):

        # Read the file contents
        text = file_path.read_text(encoding="utf-8")

        # Separate metadata from documentation content
        sections = text.split("CONTENT:", 1)

        metadata = sections[0]
        content = sections[1].strip() if len(sections) > 1 else ""

        title = ""
        source = ""
        category = ""

        # Extract metadata
        for line in metadata.splitlines():
            if line.startswith("TITLE:"):
                title = line.replace("TITLE:", "").strip()

            elif line.startswith("SOURCE:"):
                source = line.replace("SOURCE:", "").strip()

            elif line.startswith("CATEGORY:"):
                category = line.replace("CATEGORY:", "").strip()

        # Store document information
        documents.append(
            {
                "title": title,
                "source": source,
                "category": category,
                "content": content,
                "file": str(file_path.relative_to(PROJECT_DIR)),
            }
        )

    return documents


def create_manifest(documents):

    # Keep metadata without duplicating the full document content
    manifest = {
        "documents": [
            {
                "title": doc["title"],
                "source": doc["source"],
                "category": doc["category"],
                "file": doc["file"],
            }
            for doc in documents
        ]
    }

    # Save the manifest as JSON
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=4), encoding="utf-8")

    print("Manifest successfully created!")


if __name__ == "__main__":

    docs = read_documents()

    print(f"Found {len(docs)} documents.\n")

    for doc in docs:
        print("TITLE:", doc["title"])
        print("SOURCE:", doc["source"])
        print("CATEGORY:", doc["category"])
        print("CONTENT LENGTH:", len(doc["content"]), "characters")
        print("-" * 40)

    create_manifest(docs)
