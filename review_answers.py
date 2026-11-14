
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "evaluation_answers.csv"

if not SOURCE.exists():
    raise SystemExit("evaluation_answers.csv not found")

with SOURCE.open(
    newline="", encoding="utf-8"
) as f:
    rows = list(csv.DictReader(f))

small = [
    row for row in rows
    if row["setting"] == "small"
]

print("=" * 65)
print("VAANI RELAY — ANSWER QUALITY REVIEW")
print("=" * 65)
print("Small-setting records:", len(small))

for row in small:
    print("\n" + "=" * 65)
    print("QUESTION:", row["question_id"])
    print(row["question"])
    print("EXPECTED ANSWERABLE:", row["expected_answerable"])
    print("STATUS:", row["status"])

    print("\nMODEL ANSWER:")
    print(row["answer"] or "(No answer)")

    print("\nRETRIEVED SOURCES:")
    try:
        references = json.loads(row["references"])

        for ref in references:
            print(
                f"\n[{ref['label']}] "
                f"arXiv:{ref['paper']}, page {ref['page']}"
            )
            print(ref["excerpt"])
    except (ValueError, KeyError):
        print("References unavailable")

    print("\n")

print("=" * 65)
print("Review complete.")
print("No additional Groq requests were made.")
