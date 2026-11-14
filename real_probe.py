
import csv
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from relay import groq_stream, MODEL

OUTPUT = Path(__file__).resolve().parent / "groq_probe.csv"

QUESTIONS = [
    "In one sentence, what is self-attention?",
    "What is a Transformer encoder?",
    "What is positional encoding?",
    "Explain multi-head attention briefly.",
    "What is an autoregressive model?",
    "What is streaming text generation?",
    "Explain speech-text modeling briefly.",
    "What does sequence chunking mean?",
    "What is model inference latency?",
    "Why is first-token latency important?"
]


def run():
    rows = []

    print("Model:", MODEL)
    print("Running 10 real Groq requests...\n")

    for i, question in enumerate(QUESTIONS, 1):
        start = time.perf_counter()
        first_token = None
        output = []
        status = "ok"
        error_message = ""
        usage = {}

        def receive(chunk):
            nonlocal first_token
            if first_token is None:
                first_token = (
                    time.perf_counter() - start
                ) * 1000
            output.append(chunk)

        try:
            usage = groq_stream(
                [
                    {
                        "role": "system",
                        "content": (
                            "Answer the question in one short "
                            "factual sentence."
                        )
                    },
                    {
                        "role": "user",
                        "content": question
                    }
                ],
                receive
            )

        except Exception as exc:
            error_message = str(exc)[:500]

            if "429" in error_message:
                status = "rate_limited"
            else:
                status = "error"

        total = (time.perf_counter() - start) * 1000

        row = {
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
            "model": MODEL,
            "question": question,
            "status": status,
            "first_token_ms": (
                round(first_token, 2)
                if first_token is not None else ""
            ),
            "total_ms": round(total, 2),
            "tokens_in": usage.get("prompt_tokens", ""),
            "tokens_out": usage.get("completion_tokens", ""),
            "error": error_message
        }

        rows.append(row)

        print(
            f"{i}/10 | {status} | "
            f"TTFT={row['first_token_ms']} ms | "
            f"Total={row['total_ms']} ms"
        )

        # Gentle spacing to avoid unnecessary quota pressure.
        if i < len(QUESTIONS):
            time.sleep(2)

        if status == "rate_limited":
            print(
                "Rate limit detected. Ending probe "
                "to protect the free quota."
            )
            break

    with OUTPUT.open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file, fieldnames=list(rows[0].keys())
        )
        writer.writeheader()
        writer.writerows(rows)

    successful = [
        r for r in rows
        if r["status"] == "ok"
        and isinstance(r["first_token_ms"], (int, float))
    ]

    if successful:
        first = [r["first_token_ms"] for r in successful]
        total = [r["total_ms"] for r in successful]

        print("\n=== REAL GROQ SUMMARY ===")
        print("Successful requests:", len(successful))
        print(
            "Median TTFT:",
            round(statistics.median(first), 2),
            "ms"
        )
        print(
            "Median total latency:",
            round(statistics.median(total), 2),
            "ms"
        )

    print("\nRaw measurements saved to groq_probe.csv")


if __name__ == "__main__":
    run()
