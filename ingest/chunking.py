import  re
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

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



    