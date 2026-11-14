
import csv
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SUB = ROOT / "submission"

GRADES = {
    "small": {
        "Q01": "correct",
        "Q02": "correct",
        "Q03": "correct",
        "Q04": "correct",
        "Q05": "wrong",
        "Q06": "refused_wrongly",
        "Q07": "correct",
        "Q08": "wrong",
        "Q09": "correct",
        "Q10": "wrong",
        "Q11": "correct",
        "Q12": "correct",
        "Q13": "refused_correctly",
        "Q14": "refused_correctly",
        "Q15": "refused_correctly",
    },
    "balanced": {
        "Q01": "correct",
        "Q02": "correct",
        "Q03": "correct",
        "Q04": "correct",
        "Q05": "refused_wrongly",
        "Q06": "refused_wrongly",
        "Q07": "correct",
        "Q08": "wrong",
        "Q09": "correct",
        "Q10": "correct",
        "Q11": "correct",
        "Q12": "correct",
        "Q13": "refused_correctly",
        "Q14": "refused_correctly",
        "Q15": "refused_correctly",
    },
    "large": {
        "Q01": "correct",
        "Q02": "correct",
        "Q03": "correct",
    },
}


def update_csv(path, grade_by_id, column):
    with path.open(
        encoding="utf-8-sig", newline=""
    ) as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)

    if column not in fields:
        fields.append(column)

    count = 0

    for row in rows:
        request_id = row["request_id"]

        if request_id in grade_by_id:
            row[column] = grade_by_id[request_id]
            count += 1

    backup = path.with_name(
        path.stem + "_before_grading.csv"
    )
    shutil.copy2(path, backup)

    with path.open(
        "w", encoding="utf-8", newline=""
    ) as f:
        writer = csv.DictWriter(
            f, fieldnames=fields
        )
        writer.writeheader()
        writer.writerows(rows)

    print(path.name, "updated:", count)


def main():
    review_path = SUB / "quality_review.csv"

    with review_path.open(
        encoding="utf-8-sig", newline=""
    ) as f:
        reviews = list(csv.DictReader(f))

    grade_by_id = {}

    for row in reviews:
        setting = row["setting"]
        question = row["question_id"]

        if row["status"] != "ok":
            continue

        grade = GRADES.get(
            setting, {}
        ).get(question)

        if grade:
            grade_by_id[
                row["request_id"]
            ] = grade

    print("Review grades:", len(grade_by_id))

    update_csv(
        review_path,
        grade_by_id,
        "manual_grade"
    )

    update_csv(
        SUB / "results.csv",
        grade_by_id,
        "answer_grade"
    )

    print("Grading complete.")
    print("Backups created automatically.")


if __name__ == "__main__":
    main()
