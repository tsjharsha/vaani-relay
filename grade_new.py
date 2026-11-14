
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SUB = ROOT / "submission"

GRADES = {
    "Q04": ("correct", "Correct causal masking explanation."),
    "Q05": ("refused_wrongly", "Answerable in Transformer paper; retrieval missed evidence."),
    "Q06": ("wrong", "Extra gradient-flow claim not established by citation."),
    "Q07": ("correct", "Correct sinusoidal formula; verify full cited chunk."),
}

review_path = SUB / "quality_review.csv"
results_path = SUB / "results.csv"

with review_path.open(encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    review_fields = reader.fieldnames
    reviews = list(reader)

updates = {}

for row in reviews:
    if (
        row["setting"] == "large"
        and row["status"] == "ok"
        and row["question_id"] in GRADES
    ):
        grade, note = GRADES[row["question_id"]]
        row["manual_grade"] = grade
        row["review_note"] = note
        updates[row["request_id"]] = grade

with review_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=review_fields)
    writer.writeheader()
    writer.writerows(reviews)

with results_path.open(encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    result_fields = reader.fieldnames
    results = list(reader)

for row in results:
    if row["request_id"] in updates:
        row["answer_grade"] = updates[row["request_id"]]

with results_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=result_fields)
    writer.writeheader()
    writer.writerows(results)

print("New answers graded:", len(updates))
print("Quality review and results updated.")
