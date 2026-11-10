# Compare Chunking setting on the eval question 
import json 
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from ingest.chunking import chunk
from ingest.ingest import MODEL_NAME, embed, load_documents

QUESTIONS = Path(__file__).resolve().parent / "questions.json"


#=========Load pages, questions, model================
def load_inputs():
    """Load the 3 things every test needs: pages, questions, model."""
    docs = load_documents()
    questions = json.loads(QUESTIONS.read_text())
    model = SentenceTransformer(MODEL_NAME,device="cpu")
    return docs,questions,model

#=========Cut pages into chunks and turn them into numbers============

def build_index(docs,model,strategy,size):
    """Cut all pages one setting, then embed every chunk.
    Returns (chunks,vectors): chunk i has vector i
    """
    chunks = []
    for doc in docs:
        meta = {k: doc[k] for k in ("title","section","url","source_file")}
        chunks += chunk(doc["text"],meta,strategy,
                        chunk_size=size,chunk_overlap=size//8)
    texts = [c.page_content for c in chunks]
    vectors = np.array(embed(texts,model))
    return chunks, vectors

#=============Search: find the 5 closest chunks for each question==============
def search(questions,chunks,vectors,model,k=5):
    """For every Question, return the k closet chunks(best first)."""
    q_texts = [q["question"] for q in questions]
    q_vectors = np.array(embed(q_texts,model))
    #to calculate the similarity between a set of query vectors and a set of reference vectors.
    scores = q_vectors @ vectors.T 
    top_k = np.argsort(-scores,axis=1)[:,:k]

    return [[chunks[i] for i in row] for row in top_k]

#========= Score the results==============
def score_one(question,found_chunks):
    files = [c.metadata["source_file"] for c in found_chunks]
    headings = [c.metadata.get("heading","") for c in found_chunks]

    expected_file = question["expected_source_file"]
    rank = files.index(expected_file) + 1 if expected_file in files else 0
    section_found = any(h.endswith(question["expected_heading"]) for h in headings)
    return rank,section_found

def score_all(questions,results):
    ranks, sections = [], []
    for q, found in zip(questions,results):
        rank,section_found = score_one(q,found)
        ranks.append(rank)
        sections.append(section_found)
    n = len(questions)
    return{
        "hit1": 100 * sum(r == 1 for r in ranks) / n,
        "hit5": 100 * sum(r > 0 for r in ranks) / n,
        "mrr": sum(1 / r for r in ranks if r > 0) / n,
        "section": 100 * sum(sections) / n,
        "ranks": ranks,
    }

#======Scoreboard========
STRATEGIES = ["length", "semantic"]
SIZES = [300, 500, 800,1000, 1200]


def main():
    docs, questions, model = load_inputs()
    print(f"{len(questions)} questions, {len(docs)} pages\n")
    print(f"{'strategy':<9}{'size':>5}{'chunks':>6} | {'hit@1':>6} {'hit@5':>6} {'MRR':>5} | {'section':>7}")
    print("-" * 58)

    all_scores = {}
    for strategy in STRATEGIES:
        for size in SIZES:
            chunks, vectors = build_index(docs,model,strategy, size)
            results = search(questions,chunks,vectors,model,k=5)
            s = score_all(questions,results)
            all_scores[(strategy,size)] = s
            print(f"{strategy:<9} {size:>5} {len(chunks):>6} | "
                  f"{s['hit1']:5.0f}% {s['hit5']:5.0f}% {s['mrr']:5.2f} | {s['section']:6.0f}%")


    best = max(all_scores,key=lambda key: all_scores[key]["mrr"])
    print(f"\nBest by MRR:{best[0]} @ {best[1]} chars")

    misses = [q["id"] for q,r in zip(questions,all_scores[best]["ranks"]) if r != 1]
    print("Not ranked first in the best setting:",misses or "none")

if __name__ == "__main__":
    main()

