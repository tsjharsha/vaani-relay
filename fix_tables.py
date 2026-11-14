
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SUB = ROOT / "submission"

REVIEW = SUB / "quality_review.csv"
TABLES = SUB / "RESULTS_TABLES.md"

with REVIEW.open(
    encoding="utf-8-sig", newline=""
) as f:
    reviews = list(csv.DictReader(f))

text = TABLES.read_text(encoding="utf-8")

settings = ["small", "balanced", "large"]

lines = text.splitlines()
updated = []

for line in lines:
    matched = None

    for setting in settings:
        if line.startswith(f"| {setting} ("):
            matched = setting
            break

    if matched is None:
        updated.append(line)
        continue

    rows = [
        r for r in reviews
        if r["setting"] == matched
        and r["status"] == "ok"
        and r["model_answer"].strip()
    ]

    # Use the latest successful response per question.
    unique = {
        r["question_id"]: r
        for r in rows
    }

    rows = list(unique.values())
    total = len(rows)

    correct = sum(
        r["manual_grade"] == "correct"
        for r in rows
    )

    refused = sum(
        r["manual_grade"] == "refused_correctly"
        for r in rows
    )

    wrong = sum(
        r["manual_grade"] in [
            "wrong", "refused_wrongly"
        ]
        for r in rows
    )

    graded = correct + refused + wrong

    def pct(n):
        return f"{n / total * 100:.1f}%" if total else "not measured"

    cells = [c.strip() for c in line.strip().split("|")][1:-1]

    if total and graded == total:
        cells[2] = pct(correct)
        cells[3] = pct(wrong)
        cells[4] = pct(refused)
    else:
        cells[2] = "not measured"
        cells[3] = "not measured"
        cells[4] = "not measured"

    updated.append("| " + " | ".join(cells) + " |")

    print(
        f"{matched}: {total}/15 completed, "
        f"{graded} graded, "
        f"{correct} correct, "
        f"{wrong} wrong, "
        f"{refused} correct refusals"
    )

TABLES.write_text(
    "\n".join(updated) + "\n",
    encoding="utf-8"
)

print("RESULTS_TABLES.md updated successfully.")
