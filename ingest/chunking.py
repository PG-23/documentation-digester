import  re
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
MAX_HEADING_LEN = 80 # heading are short lines
MAX_HEADING_WORDS = 10

# =========== Heading detector========
# Style 1 (Sphinx/RST): title line followed by one character repeated, e.g. "=====".
# "No spaces" means table borders like "=====  =====" are not matched.

UNDERLINE_RE = re.compile(r'^([=\-~*^"+#`])\1{2,}\s*$')

# Lines ending like a sentence or a code line are not headings.

NOT_HEADING_ENDING = (".",",",";",":","!")
CODE_CHARS = set("(){}=;<>[]")
BULLETS = ("- ", "* ", "• ")# Files may start with:  TITLE: ... / SOURCE: ... / CATEGORY: ... / CONTENT:
HEADER_KEYS = ("TITLE:", "SOURCE:", "CATEGORY:")

def _strip_header(text:str) -> tuple[str,str]:
    """Remove the TITLE/SOURCE/CATEGORY/CONTENT: header if the page has one.

    Returns (page_title, content). Pages without a header come back unchanged
    with page_title"""
    if not text.lstrip().startswith("TITLE:"):
        return "", text
    lines = text.splitlines()
    title = ""
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("TITLE:"):
            title = s[len("TITLE:"):].strip()
        elif s == "CONTENT:":
            return title, "\n".join(lines[i+1:])
        elif s and not s.startswith(HEADER_KEYS):
            break
    content = [l for l in lines if not l.strip().startswith(HEADER_KEYS)]
    return title, "\n".join(content)

def _clean_heading(line:str) -> str:
    s = line.strip().lstrip("#").strip()
    s = s.strip("*").strip()
    return s.rstrip(":").strip()
             
            
def _is_blank(lines: list[str],i:int) -> bool:
    """True if index i is outside the list or the line is empty."""
    return i < 0 or i >= len(lines) or not lines[i].strip()

def _is_underline(line:str) -> bool:
    return bool(UNDERLINE_RE.match(line))

def _looks_like_title(line:str) -> bool:
    """Checks shared by both heading styles"""
    s = line.strip()
    if not s or line[0].isspace():
            return False
    if len(s) > MAX_HEADING_LEN or len(s.split()) > MAX_HEADING_WORDS:
            return False
    if _is_underline(s):
            return False
    return True
def _is_underline_heading(lines:list[str],i:int) -> bool:
    """Style 1: lines[i] is a title and lines[i+1] is its underline."""
    if i + 1 >= len(lines) or not _looks_like_title(lines[i]):
            return False
    underline = lines[i+1].strip()
    if not _is_underline(underline):
            return False
    return len(underline) >= len(lines[i].strip()) * 0.8

def _is_plain_heading(lines: list[str],i:int) -> bool:
    """Style 2 (our data): a short line with a blank line above and below"""
    if not _looks_like_title(lines[i]):
        return False
    s = lines[i].strip()
    if not(_is_blank(lines,i-1) and _is_blank(lines,i+1)):
        return False
    if s.endswith(NOT_HEADING_ENDING):
        return False
    if s.startswith(BULLETS) or any(c in CODE_CHARS for c in s):
          return False
    return True
    
# =========== Split a page into sections ======== 
def _split_sections(text:str) -> list[tuple[str,str]]:
    """Cut a page at its headings.

    Returns a list of (heading_path, body), e.g.
    ("Using signals > Connecting a signal in code", "You can also connect ...").
    Text before the first heading gets heading_path "".
    """
    page_title, text = _strip_header(text)
    lines = text.splitlines()
    sections:list[tuple[str,str]] = []
    path: list[str] = [page_title] if page_title else []
    underline_levels: list[str] = []
    body: list[str] = []

    def flush():
        """Save the body collected so far under the current path."""
        content = "\n".join(body).strip()
        if content:
            sections.append((" > ".join(path),content))
        body.clear()

    i = 0
    while i < len(lines):
        if _is_underline_heading(lines, i):
            flush()
            title = _clean_heading(lines[i])
            char = lines[i+1].strip()[0]
            if char not in underline_levels:
                underline_levels.append(char)
            level = underline_levels.index(char)
            path = path[:level] + [title]
            i += 2
            continue
        if _is_plain_heading(lines, i):
            flush()
            title = _clean_heading(lines[i])
            # First heading = page title (level 0); every later one is level 1
            path = [title] if not path else path[:1] + [title]
            i += 1
            continue
        body.append(lines[i])
        i += 1
    flush()
    return sections
         
# =========== Semantic chunking ========  
MIN_BODY_ROOM = 200
def _semantic_pieces(
    text: str,
    chunk_size:int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,    
) -> list[tuple[str,str]]:
    """Return (heading_path, chunk_text) for every chunk on the page.

    chunk_text already starts with the heading path.
    """
    pieces: list[tuple[str,str]] = []
    for heading, body in _split_sections(text):
        prefix = f"{heading}\n\n" if heading else ""
        room = max(chunk_size - len(prefix),MIN_BODY_ROOM)

        if len(body) <= room:
            parts = [body]
        else:
            splitter = RecursiveCharacterTextSplitter(
                  chunk_size=room,
                  chunk_overlap = min(chunk_overlap,room // 4),
                )
            parts = splitter.split_text(body)
        for part in parts:
            pieces.append((heading,prefix + part))
    return pieces

def semantic_chunker(text:str) -> list[str]:
    """Split by headings first, then by length inside long sections.

    Same signature as length_chunker in ingest/ingest.py: text -> list of chunk strings.
    """
    return [chunk for _, chunk in _semantic_pieces(text)]
             
            
         
       

          
def chunk_page(
        text:str,
        metadata: dict,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap:int = CHUNK_OVERLAP
) -> list[Document]:
        splitter = RecursiveCharacterTextSplitter(
              chunk_size=chunk_size,
              chunk_overlap = chunk_overlap,
        )
        pieces = splitter.split_text(text)
        return[
                Document(
                        page_content = piece,
                        metadata = {**metadata,"chunk_index":i},
                )
                for i,piece in enumerate(pieces)
        ]

def chunk_page_semantic(
        text:str,
        metadata: dict,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = CHUNK_OVERLAP,
) -> list[Document]:
    """Like chunk_page, but split by headings and record the heading in metadata."""
    return [
         Document(
            page_content=chunk_text,
            metadata = {**metadata,"heading":heading,"chunk_index":i},
        )
        for i, (heading, chunk_text) in enumerate(
             _semantic_pieces(text, chunk_size, chunk_overlap)
        )
    ]

# =========== One entry point for ingest ========
CHUNKERS = {
    "length" : chunk_page,
    "semantic": chunk_page_semantic,
}

def chunk(
    text: str,
    metadata: dict,
    strategy: str = "semantic",
    **kwargs,

) -> list[Document]:
     
    """Chunk one page with the chosen strategy ("length" or "semantic").

    Extra kwargs (chunk_size, chunk_overlap) are passed through,
    so K-2 can try different sizes: chunk(text, meta, "semantic", chunk_size=500)
    """
    if strategy not in CHUNKERS:
        raise ValueError(f"Unknown strategy {strategy!r}, use one of {list(CHUNKERS)}")

    docs = CHUNKERS[strategy] (text,metadata, **kwargs)
    for d in docs:
        d.metadata["chunker"] = strategy
    return docs
        


     
     
     


    