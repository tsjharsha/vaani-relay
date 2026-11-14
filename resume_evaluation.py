
import argparse
import csv
import time
from pathlib import Path

from evaluate import (
    ROOT,
    RAW,
    ANSWERS,
    SETTINGS,
    QUESTIONS,
    build_retriever,
    evaluate_one,
    save_csv,
    FIELDS,
)


def read_existing():
    if not ANSWERS.exists():
        return []

    with ANSWERS.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as file:
        return list(csv.DictReader(file))


def completed_questions(setting):
    rows = read_existing()

    completed = set()

    for row in rows:
        if (
            row["setting"] == setting
            and row["status"] == "ok"
            and row["answer"].strip()
        ):
            completed.add(row["question_id"])

    return completed


def run(setting, delay):
    completed = completed_questions(setting)

    pending = [
        (qid, question, answerable)
        for qid, question, answerable in QUESTIONS
        if qid not in completed
    ]

    print("\n" + "=" * 55)
    print("VAANI RELAY — RESUMABLE EVALUATION")
    print("=" * 55)

    print("Setting:", setting)
    print("Already completed:", len(completed))
    print("Remaining:", len(pending))
    print("Delay between requests:", delay, "seconds")

    if not pending:
        print("\nAll questions already completed.")
        return

    print("\nPreparing retriever...")
    retriever = build_retriever(setting)

    for index, (qid, question, answerable) in enumerate(
        pending, start=1
    ):
        print(
            f"\n[{index}/{len(pending)}] "
            f"Testing {qid}: {question}",
            flush=True,
        )

        raw_row, answer_row = evaluate_one(
            qid,
            question,
            answerable,
            setting,
            retriever,
        )

        save_csv(RAW, [raw_row], FIELDS)

        save_csv(
            ANSWERS,
            [answer_row],
            list(answer_row.keys()),
        )

        print("Status:", raw_row["status"])
        print("First token:", raw_row["first_token_ms"], "ms")
        print("Total:", raw_row["total_ms"], "ms")

        if raw_row["status"] == "rate_limited":
            print("\nGroq rate limit detected.")
            print("Stopping to protect your free quota.")
            print("Try again after your quota recovers.")
            break

        if raw_row["status"] != "ok":
            print("Request failed; outcome saved.")
            print("Stopping so we can inspect the error.")
            break

        print("Saved successfully.")

        if index < len(pending):
            time.sleep(delay)

    print("\nProgress saved.")
    print("Raw results:", RAW.name)
    print("Answer records:", ANSWERS.name)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--setting",
        required=True,
        choices=list(SETTINGS),
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=8.0,
    )

    args = parser.parse_args()

    run(args.setting, args.delay)


if __name__ == "__main__":
    main()
