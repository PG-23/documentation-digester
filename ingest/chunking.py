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
def _split_sections(text:str,page_title:str = "") -> list[tuple[str,str]]:
    """Cut a page at its headings.

    Returns a list of (heading_path, body), e.g.
    ("Using signals > Connecting a signal in code", "You can also connect ...").
    Text before the first heading gets heading_path "".
    """
    header_title, text = _strip_header(text)
    page_title = page_title or header_title
    lines = text.splitlines()
    sections:list[tuple[str,str]] = []
    root: list[str] = [page_title] if page_title else []   # page title, start of every path
    path: list[str] = list(root)
    seen_text = False                                      # any body text yet?

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
            if not root and not seen_text:
                root = [title]          # page starts with a heading: it's the page title
                path = list(root)
            elif root and title == root[-1]:
                path = list(root)       # page title repeated in the text: don't nest it
            else:
                path = root + [title]   # every other heading sits under the page title
            i += 1
            continue
        if lines[i].strip():
            seen_text = True
        body.append(lines[i])

        i += 1
    flush()
    return sections

#=========== Meaning-based Split(for the "hybrid strategy") ===========
SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")
MIN_PIECE = 150 

def _sentences(text:str) -> list[tuple[str,str]]:
    """Split text into sentences. Returns (sentence, separator_before) paris.
     separator_before is "\n" if the sentence starts a new line, else " ",
    so we can rebuild the text with its line breaks (bullet lists) intact.
     """
    units = []
    for line in text.splitlines():
        if not line.strip():
            continue
        for j, sent in enumerate(SENTENCE_END_RE.split(line.strip())):
            if sent:
                units.append((sent," " if j > 0 else "\n"))
    return units

def _join(units: list[tuple[str,str]]) -> str:
    """Rebuild text from (sentence,separator_before) paris"""
    return "".join(sep + sent for sent,sep in units).strip()

def semantic_split(text:str,max_len:int) -> list[str]:
    """Split long text where the meaning changes the most
    1. Split into sentences and embed them.
    2. Score each gap by how similar the sentences on both sides are
    3. Cut at the least similar gap, then repeat on each half
    until every piece is <= max_len."""

    from ingest.ingest import get_model
    units = _sentences(text)
    if len(units) < 2:
        return RecursiveCharacterTextSplitter(chunk_size=max_len,chunk_overlap = 0).split_text(text)
    vectors = get_model().encode([s for s, _ in units],normalize_embeddings=True)
    gap_sims = [float(vectors[i] @ vectors[i+1]) for i in range(len(units)-1)]

    def split(start:int,end:int) -> list[str]:
        piece = _join(units[start:end])
        if len(piece) <= max_len:
            return [piece]
        if end - start == 1:
            return RecursiveCharacterTextSplitter(chunk_size=max_len,chunk_overlap=0).split_text(piece)
        gaps = range(start,end - 1)
        good = [g for g in gaps
                if len(_join(units[start:g + 1])) >= MIN_PIECE
                and len(_join(units[g + 1:end])) >= MIN_PIECE]
        cut = min(good or gaps,key=lambda g: gap_sims[g]) 
        return split(start,cut + 1) + split(cut + 1,end)
    return split(0,len(units)) 
# =========== Semantic chunking ========  
MIN_BODY_ROOM = 200
def _semantic_pieces(
    text: str,
    chunk_size:int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    page_title: str = "",
    long_split:str = "length",

) -> list[tuple[str,str]]:
    """Return (heading_path, chunk_text) for every chunk on the page.

    chunk_text already starts with the heading path.
    """
    pieces: list[tuple[str,str]] = []
    for heading, body in _split_sections(text,page_title):
        prefix = f"{heading}\n\n" if heading else ""
        room = max(chunk_size - len(prefix),MIN_BODY_ROOM)

        if len(body) <= room:
            parts = [body]
        elif long_split == "meaning":
            parts = semantic_split(body,room)
        else:
            splitter = RecursiveCharacterTextSplitter(
                  chunk_size=room,
                  chunk_overlap = min(chunk_overlap,room // 4),
                )
            parts = splitter.split_text(body)
        for part in parts:
            pieces.append((heading,prefix + part))
    return pieces

def semantic_chunker(text:str,page_title:str="") -> list[str]:
    """Split by headings first, then by length inside long sections.

    Same signature as length_chunker in ingest/ingest.py: text -> list of chunk strings.
    """
    return [chunk for _, chunk in _semantic_pieces(text,page_title=page_title)]
             
            
         
          
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
             _semantic_pieces(text, chunk_size, chunk_overlap, metadata.get("title",""))
        )
    ]

def chunk_page_hybrid(
        text:str,
        metadata:dict,
        chunk_size:int = CHUNK_SIZE,
        chunk_overlap:int = CHUNK_OVERLAP,
) -> list[Document]:
    """Heading first (like semantic), then split long sections by meaning"""
    return [
        Document(
            page_content=chunk_text,
            metadata={**metadata,"heading":heading,"chunk_index":i},

        )
        for i, (heading,chunk_text) in enumerate(
            _semantic_pieces(text, chunk_size,chunk_overlap,
                            metadata.get("title",""),long_split = "meaning")
        )
    ]

# =========== One entry point for ingest ========
CHUNKERS = {
    "length" : chunk_page,
    "semantic": chunk_page_semantic,
    "hybrid": chunk_page_hybrid
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
        


     
     
     


    