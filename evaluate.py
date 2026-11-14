
import argparse
import csv
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pymupdf
from sklearn.feature_extraction.text import TfidfVectorizer

from relay import groq_stream, LIBRARY, PAPERS, MODEL

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "retrieval_runs.csv"
ANSWERS = ROOT / "evaluation_answers.csv"

SETTINGS = {
    "small": (120, 25, 3),
    "balanced": (220, 40, 4),
    "large": (400, 60, 6),
}

QUESTIONS = [
    ("Q01", "Why does the Transformer need positional encoding?", True),
    ("Q02", "What is scaled dot-product attention?", True),
    ("Q03", "Why does the Transformer use multiple attention heads?", True),
    ("Q04", "What role does masking play in the Transformer decoder?", True),
    ("Q05", "How does the Transformer handle source and target sequences?", True),
    ("Q06", "What is the purpose of residual connections in the Transformer?", True),
    ("Q07", "How are sine and cosine functions used in positional encoding?", True),
    ("Q08", "What problem is Moshi designed to address?", True),
    ("Q09", "What kinds of information does Moshi model?", True),
    ("Q10", "What is meant by full-duplex dialogue in Moshi?", True),
    ("Q11", "What problem does dynamic chunking address in hierarchical sequence modeling?", True),
    ("Q12", "What is the central idea of dynamic chunking?", True),
    ("Q13", "What is the CEO's private mobile number at the company that built Moshi?", False),
    ("Q14", "What was the exact electricity bill for training the original Transformer?", False),
    ("Q15", "What will the price of NVIDIA stock be on January 1, 2030?", False),
]

FIELDS = [
    "request_id", "scenario", "source", "start_time",
    "first_token_ms", "total_ms", "status", "retries",
    "tokens_in", "tokens_out", "retrieval_setting",
    "answer_grade"
]


def make_passages(chunk_words, overlap):
    result = []

    for paper_id, title in LIBRARY.items():
        path = PAPERS / f"{paper_id}.pdf"

        if not path.exists():
            raise FileNotFoundError(
                f"Missing {path}. Run python relay.py download"
            )

        with pymupdf.open(path) as pdf:
            for page_number, page in enumerate(pdf, 1):
                text = " ".join(page.get_text(sort=True).split())
                words = text.split()
                step = chunk_words - overlap

                for start in range(0, len(words), step):
                    chunk = words[start:start + chunk_words]

                    if len(chunk) < 25:
                        continue

                    result.append({
                        "paper_id": paper_id,
                        "title": title,
                        "page": page_number,
                        "text": " ".join(chunk)
                    })

    return result


def build_retriever(setting):
    size, overlap, top_k = SETTINGS[setting]
    passages = make_passages(size, overlap)

    vectorizer = TfidfVectorizer(
        stop_words="english",
        max_features=30000
    )
    matrix = vectorizer.fit_transform(
        [p["text"] for p in passages]
    )

    return passages, vectorizer, matrix, top_k


def search(question, retriever):
    passages, vectorizer, matrix, top_k = retriever
    query = vectorizer.transform([question])

    # TF-IDF vectors are L2-normalized by default.
    scores = (matrix @ query.T).toarray().ravel()
    indices = np.argsort(scores)[::-1][:top_k]

    return [
        passages[int(i)]
        for i in indices
        if scores[int(i)] > 0
    ]


def save_csv(path, rows, fields):
    if not rows:
        return

    create_header = (
        not path.exists() or path.stat().st_size == 0
    )

    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)

        if create_header:
            writer.writeheader()

        for row in rows:
            writer.writerow({
                key: row.get(key, "")
                for key in fields
            })


def evaluate_one(question_id, question, answerable,
                 setting, retriever):
    request_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    start = time.perf_counter()

    retrieved = search(question, retriever)
    retrieval_ms = (
        time.perf_counter() - start
    ) * 1000

    context = "\n\n".join(
        f"[P{i}] {p['title']}, "
        f"arXiv:{p['paper_id']}, PDF page {p['page']}\n"
        f"{p['text']}"
        for i, p in enumerate(retrieved, 1)
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a research assistant answering ONLY "
                "from the provided paper passages. "
                "Cite supporting passage labels such as [P1]. "
                "If the passages do not establish the answer, "
                "say exactly: "
                "'The supplied papers do not establish that.' "
                "Do not guess or use outside information. "
                "Keep answers concise."
            )
        },
        {
            "role": "user",
            "content": (
                f"Question: {question}\n\n"
                f"Paper passages:\n{context}"
            )
        }
    ]

    chunks = []
    first_token = None
    usage = {}
    status = "ok"
    error = ""

    def receive(piece):
        nonlocal first_token

        if first_token is None:
            first_token = (
                time.perf_counter() - start
            ) * 1000

        chunks.append(piece)

    try:
        if not retrieved:
            status = "error"
            error = "No passages retrieved"
        else:
            usage = groq_stream(messages, receive)

    except Exception as exc:
        error = str(exc)[:400]

        if "429" in error:
            status = "rate_limited"
        elif "timed out" in error.lower():
            status = "timeout"
        else:
            status = "error"

    total_ms = (
        time.perf_counter() - start
    ) * 1000

    answer = "".join(chunks)

    references = [
        {
            "label": f"P{i}",
            "paper": p["paper_id"],
            "page": p["page"],
            "excerpt": p["text"][:400]
        }
        for i, p in enumerate(retrieved, 1)
    ]

    raw_row = {
        "request_id": request_id,
        "scenario": f"retrieval_{setting}",
        "source": "real",
        "start_time": timestamp,
        "first_token_ms": (
            round(first_token, 2)
            if first_token is not None else ""
        ),
        "total_ms": round(total_ms, 2),
        "status": status,
        "retries": 0,
        "tokens_in": usage.get("prompt_tokens", ""),
        "tokens_out": usage.get("completion_tokens", ""),
        "retrieval_setting": setting,
        "answer_grade": ""
    }

    answer_row = {
        "request_id": request_id,
        "question_id": question_id,
        "setting": setting,
        "question": question,
        "expected_answerable": answerable,
        "answer": answer,
        "references": json.dumps(references),
        "retrieval_ms": round(retrieval_ms, 2),
        "status": status,
        "error": error,
        "manual_grade": ""
    }

    return raw_row, answer_row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--setting",
        choices=list(SETTINGS),
        required=True
    )
    args = parser.parse_args()

    setting = args.setting

    print("Preparing retrieval:", setting, flush=True)
    retriever = build_retriever(setting)

    print("Model:", MODEL)
    print("Questions:", len(QUESTIONS))
    print("Expected real requests: 15\n")

    for index, (qid, question, answerable) in enumerate(
        QUESTIONS, 1
    ):
        raw_row, answer_row = evaluate_one(
            qid, question, answerable, setting, retriever
        )

        # Save after EVERY request so interruptions
        # do not destroy previous measurements.
        save_csv(RAW, [raw_row], FIELDS)
        save_csv(
            ANSWERS,
            [answer_row],
            list(answer_row.keys())
        )

        print(
            f"{index}/15 | {qid} | "
            f"{raw_row['status']} | "
            f"TTFT={raw_row['first_token_ms']} ms | "
            f"total={raw_row['total_ms']} ms",
            flush=True
        )

        if raw_row["status"] == "rate_limited":
            print(
                "Rate limit reached. Stopping this run."
            )
            break

        if index < len(QUESTIONS):
            time.sleep(2)

    print("\nEvaluation run complete.")
    print("Raw measurements:", RAW.name)
    print("Answers for manual review:", ANSWERS.name)
    print(
        "Important: grades remain blank until "
        "answers and citations are checked."
    )


if __name__ == "__main__":
    main()
