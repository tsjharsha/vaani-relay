
import argparse
import csv
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pymupdf
import requests
from dotenv import load_dotenv
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parent

load_dotenv(ROOT / ".env")

PAPERS = ROOT / "papers"
INDEX = ROOT / "passages.json"
RESULTS = ROOT / "results.csv"

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

LIBRARY = {
    "1706.03762v7": "Attention Is All You Need",
    "2410.00037v1": (
        "Moshi: a speech-text foundation model for real-time dialogue"
    ),
    "2507.07955v2": (
        "Dynamic Chunking for End-to-End Hierarchical Sequence Modeling"
    ),
}

COLUMNS = [
    "request_id",
    "scenario",
    "source",
    "start_time",
    "first_token_ms",
    "total_ms",
    "status",
    "retries",
    "tokens_in",
    "tokens_out",
    "retrieval_setting",
    "answer_grade",
]


def download():
    PAPERS.mkdir(exist_ok=True)

    for paper_id, title in LIBRARY.items():
        target = PAPERS / f"{paper_id}.pdf"

        if target.exists() and target.read_bytes()[:4] == b"%PDF":
            print("Already downloaded:", paper_id)
            continue

        url = f"https://arxiv.org/pdf/{paper_id}"

        print("Downloading:", title, flush=True)

        response = requests.get(
            url,
            timeout=90,
            headers={"User-Agent": "RelayAssignment/1.0"},
        )

        response.raise_for_status()

        if not response.content.startswith(b"%PDF"):
            raise ValueError(
                f"{paper_id}: arXiv did not return a valid PDF"
            )

        target.write_bytes(response.content)

        print("Saved:", target)

        time.sleep(3)


def build_index(chunk_words=220, overlap_words=40):
    if chunk_words <= overlap_words:
        raise ValueError(
            "Chunk size must be larger than overlap."
        )

    passages = []

    for paper_id, title in LIBRARY.items():
        path = PAPERS / f"{paper_id}.pdf"

        if not path.exists():
            raise FileNotFoundError(
                f"{path} missing. Run python relay.py download"
            )

        with pymupdf.open(path) as pdf:
            for page_no, page in enumerate(pdf, start=1):
                text = " ".join(
                    page.get_text(sort=True).split()
                )

                words = text.split()
                step = chunk_words - overlap_words

                for start in range(0, len(words), step):
                    part = words[start:start + chunk_words]

                    if len(part) < 25:
                        continue

                    passages.append({
                        "paper_id": paper_id,
                        "title": title,
                        "page": page_no,
                        "text": " ".join(part),
                    })

    INDEX.write_text(
        json.dumps(passages, ensure_ascii=False),
        encoding="utf-8",
    )

    print(
        f"Indexed {len(passages)} passages "
        f"into {INDEX.name}"
    )


def retrieve(question, top_k=4):
    if not INDEX.exists():
        raise FileNotFoundError(
            "No index found. Run python relay.py index"
        )

    passages = json.loads(
        INDEX.read_text(encoding="utf-8")
    )

    if not passages:
        return []

    vectorizer = TfidfVectorizer(
        stop_words="english",
        max_features=30000,
    )

    matrix = vectorizer.fit_transform(
        [p["text"] for p in passages]
    )

    query = vectorizer.transform([question])

    scores = cosine_similarity(
        query, matrix
    ).ravel()

    best = np.argsort(scores)[::-1][:top_k]

    return [
        (passages[int(i)], float(scores[i]))
        for i in best
        if scores[int(i)] > 0
    ]


def save_result(row):
    create_header = (
        not RESULTS.exists()
        or RESULTS.stat().st_size == 0
    )

    with RESULTS.open(
        "a",
        newline="",
        encoding="utf-8",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=COLUMNS,
        )

        if create_header:
            writer.writeheader()

        writer.writerow({
            key: row.get(key, "")
            for key in COLUMNS
        })


def groq_stream(messages, on_text):
    key = os.getenv(
        "GROQ_API_KEY", ""
    ).strip()

    if not key or key == "put_your_key_here":
        raise RuntimeError(
            "Missing Groq API key. Check your .env file."
        )

    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": True,
        "stream_options": {
            "include_usage": True
        },
        "temperature": 0.1,
        "max_completion_tokens": 450,
    }

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    usage = {}

    with requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        json=payload,
        headers=headers,
        stream=True,
        timeout=(15, 90),
    ) as response:

        if response.status_code != 200:
            raise requests.HTTPError(
                f"Groq HTTP {response.status_code}: "
                f"{response.text[:500]}",
                response=response,
            )

        # Correct UTF-8 decoding and indentation.
        for raw_bytes in response.iter_lines():

            if not raw_bytes:
                continue

            raw = raw_bytes.decode(
                "utf-8",
                errors="replace",
            )

            if not raw.startswith("data: "):
                continue

            data = raw[6:].strip()

            if data == "[DONE]":
                break

            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue

            if event.get("usage"):
                usage = event["usage"]

            for choice in event.get("choices", []):
                delta = choice.get("delta") or {}
                content = delta.get("content")

                if content:
                    on_text(content)

    return usage


def has_valid_citation_format(answer, passage_count):
    labels = re.findall(
        r"\bP(\d+)\b",
        answer,
    )

    if not labels:
        return False

    return all(
        1 <= int(label) <= passage_count
        for label in labels
    )


def ask(question):
    request_id = str(uuid.uuid4())

    start_utc = datetime.now(
        timezone.utc
    ).isoformat()

    start = time.perf_counter()

    first_token_ms = None
    answer = []

    status = "ok"
    tokens_in = ""
    tokens_out = ""
    top_k = 4

    print(
        "\nSearching the papers...",
        flush=True,
    )

    try:
        passages = retrieve(
            question,
            top_k=top_k,
        )

        if not passages:
            print(
                "The supplied papers do not "
                "establish that."
            )
            return

        context = "\n\n".join(
            f"[P{i}] {p['title']} "
            f"(arXiv:{p['paper_id']}, "
            f"PDF page {p['page']}): "
            f"{p['text']}"
            for i, (p, score) in enumerate(
                passages, 1
            )
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a research assistant. "
                    "Answer ONLY from the supplied excerpts. "
                    "Cite supporting passages using labels "
                    "such as [P1] or [P1, P2]. "
                    "If the excerpts do not support the answer, "
                    "say exactly: "
                    "'The supplied papers do not establish that.' "
                    "Do not invent facts or citations. "
                    "Give a complete, concise answer."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"QUESTION:\n{question}\n\n"
                    f"EXCERPTS:\n{context}"
                ),
            },
        ]

        print(
            "\nAnswer:\n",
            end="",
            flush=True,
        )

        def handle_piece(piece):
            nonlocal first_token_ms

            if first_token_ms is None:
                first_token_ms = (
                    time.perf_counter() - start
                ) * 1000

            print(
                piece,
                end="",
                flush=True,
            )

            answer.append(piece)

        usage = groq_stream(
            messages,
            handle_piece,
        )

        tokens_in = usage.get(
            "prompt_tokens", ""
        )

        tokens_out = usage.get(
            "completion_tokens", ""
        )

        final_answer = "".join(answer)

        print("\n\nSource labels:")

        for i, (p, score) in enumerate(
            passages, 1
        ):
            print(
                f"[P{i}] arXiv:{p['paper_id']}, "
                f"PDF page {p['page']} | "
                f"relevance={score:.3f}"
            )

        refusal = (
            "the supplied papers do not establish that"
            in final_answer.lower()
        )

        if not refusal:
            if not has_valid_citation_format(
                final_answer,
                len(passages),
            ):
                print(
                    "\nWARNING: Missing or invalid "
                    "citation labels. Review the answer."
                )

    except requests.Timeout as exc:
        status = "timeout"
        print("\nTimed out:", exc)

    except requests.HTTPError as exc:
        if (
            exc.response is not None
            and exc.response.status_code == 429
        ):
            status = "rate_limited"
        else:
            status = "error"

        print("\nAPI error:", exc)

    except Exception as exc:
        status = "error"
        print("\nError:", exc)

    finally:
        total_ms = round(
            (
                time.perf_counter() - start
            ) * 1000,
            2,
        )

        save_result({
            "request_id": request_id,
            "scenario": "single_real",
            "source": "real",
            "start_time": start_utc,
            "first_token_ms": (
                ""
                if first_token_ms is None
                else round(first_token_ms, 2)
            ),
            "total_ms": total_ms,
            "status": status,
            "retries": 0,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "retrieval_setting": (
                f"220w_40overlap_top{top_k}_tfidf"
            ),
            "answer_grade": "",
        })

        print(
            f"\nStatus: {status} | "
            f"total={total_ms:.0f} ms | "
            f"first token={first_token_ms}"
        )

        print(
            f"Logged in {RESULTS.name}"
        )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Vaani RELAY research-paper assistant"
        )
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    commands.add_parser("download")
    commands.add_parser("index")

    ask_parser = commands.add_parser("ask")

    ask_parser.add_argument(
        "question"
    )

    ask_parser.add_argument(
        "--source",
        default="real",
        choices=["real"],
    )

    args = parser.parse_args()

    if args.command == "download":
        download()

    elif args.command == "index":
        build_index()

    elif args.command == "ask":
        ask(args.question)


if __name__ == "__main__":
    main()
