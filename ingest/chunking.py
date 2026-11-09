import  re
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
MAX_HEADING_LEN = 80 # heading are short lines
MAX_HEADING_WORDS = 10

# Style 1 (Sphinx/RST): title line followed by one character repeated, e.g. "=====".
# "No spaces" means table borders like "=====  =====" are not matched.

UNDERLINE_RE = re.compile(r'^([=\-~*^"+#`])\1{2,}\s*$')

# Lines ending like a sentence or a code line are not headings.

NOT_HEADING_ENDING = (".",",",";",":","!")
CODE_CHARS = set("(){}=;<>[]")
BULLETS = ("_ ","* ",". ")

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



    