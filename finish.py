
import csv
import json
import math
import statistics
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "submission"
OUT.mkdir(exist_ok=True)

FIELDS = [
    "request_id", "scenario", "source", "start_time",
    "first_token_ms", "total_ms", "status", "retries",
    "tokens_in", "tokens_out", "retrieval_setting",
    "answer_grade"
]

GRADES = {
    "correct", "wrong",
    "refused_correctly", "refused_wrongly"
}

SETTINGS = {
    "small": (120, 3),
    "balanced": (220, 4),
    "large": (400, 6)
}


def load(filename):
    path = ROOT / filename
    if not path.exists():
        return []

    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def save(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=fields, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def percent(count, total):
    if total == 0:
        return "not measured"
    return f"{count / total * 100:.1f}%"


def percentile(values, p):
    values = sorted(v for v in values if v is not None)

    if not values:
        return "not measured"

    pos = (len(values) - 1) * p / 100
    low = math.floor(pos)
    high = math.ceil(pos)

    value = values[low] + (
        values[high] - values[low]
    ) * (pos - low)

    return f"{value:.1f}"


def parse_time(value):
    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except (ValueError, AttributeError):
        return None


def normalize(row):
    return {
        field: str(
            row.get(field, "")
            if row.get(field, "") is not None
            else ""
        )
        for field in FIELDS
    }


def prepare_quality_review():
    answers = load("evaluation_answers.csv")

    previous = {
        r["request_id"]: r
        for r in load("submission/quality_review.csv")
    }

    review = []

    for answer in answers:
        request_id = answer.get("request_id", "")
        old = previous.get(request_id, {})

        review.append({
            "request_id": request_id,
            "setting": answer.get("setting", ""),
            "question_id": answer.get("question_id", ""),
            "question": answer.get("question", ""),
            "status": answer.get("status", ""),
            "expected_answerable": answer.get(
                "expected_answerable", ""
            ),
            "model_answer": answer.get("answer", ""),
            "retrieved_references": answer.get(
                "references", ""
            ),
            "manual_grade": old.get("manual_grade", ""),
            "review_note": old.get("review_note", "")
        })

    columns = [
        "request_id", "setting", "question_id",
        "question", "status", "expected_answerable",
        "model_answer", "retrieved_references",
        "manual_grade", "review_note"
    ]

    save(OUT / "quality_review.csv", review, columns)

    return review


def simulated_retry_experiment():
    """
    Controlled synthetic HTTP 429 comparison.
    No actual Groq requests are made.
    """

    rows = []
    traces = []

    start = datetime(
        2026, 11, 14, tzinfo=timezone.utc
    )

    for scenario in ["retry_off", "retry_on"]:
        for i in range(12):
            retries = 1 if scenario == "retry_on" else 0

            first_failure_ms = 120 + i * 4
            backoff_ms = 250 if retries else 0
            second_failure_ms = (
                first_failure_ms if retries else 0
            )

            total_ms = (
                first_failure_ms
                + backoff_ms
                + second_failure_ms
            )

            request_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"relay-retry-{scenario}-{i}"
                )
            )

            rows.append(normalize({
                "request_id": request_id,
                "scenario": scenario,
                "source": "stand-in",
                "start_time": (
                    start + timedelta(milliseconds=100 * i)
                ).isoformat(),
                "first_token_ms": "",
                "total_ms": total_ms,
                "status": "rate_limited",
                "retries": retries,
                "tokens_in": 0,
                "tokens_out": 0,
                "retrieval_setting": "none",
                "answer_grade": ""
            }))

            traces.append({
                "request_id": request_id,
                "scenario": scenario,
                "first_failure_ms": first_failure_ms,
                "backoff_ms": backoff_ms,
                "second_failure_ms": second_failure_ms,
                "total_ms": total_ms,
                "note": "Synthetic HTTP 429 injection"
            })

    save(
        OUT / "retry_trace.csv",
        traces,
        list(traces[0].keys())
    )

    return rows


def combine_results(review):
    events = load("events_calibrated.csv")

    calibrated_ids = {
        row["request_id"]
        for row in events
    }

    grades = {
        row["request_id"]: row["manual_grade"]
        for row in review
        if row["manual_grade"] in GRADES
    }

    rows = []
    excluded = 0

    for row in load("results.csv"):
        if row.get("source") == "stand-in":
            if row.get("request_id") not in calibrated_ids:
                excluded += 1
                continue

        rows.append(normalize(row))

    for row in load("retrieval_runs.csv"):
        rows.append(normalize(row))

    for i, row in enumerate(load("groq_probe.csv")):
        request_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"groq-probe-{row.get('timestamp')}-{i}"
            )
        )

        rows.append(normalize({
            "request_id": request_id,
            "scenario": "real_probe",
            "source": "real",
            "start_time": row.get("timestamp", ""),
            "first_token_ms": row.get(
                "first_token_ms", ""
            ),
            "total_ms": row.get("total_ms", ""),
            "status": row.get("status", "error"),
            "retries": 0,
            "tokens_in": row.get("tokens_in", ""),
            "tokens_out": row.get("tokens_out", ""),
            "retrieval_setting": "none",
            "answer_grade": ""
        }))

    rows.extend(simulated_retry_experiment())

    unique = []
    seen = set()

    for row in rows:
        request_id = row["request_id"]

        if request_id in seen:
            continue

        seen.add(request_id)

        if request_id in grades:
            row["answer_grade"] = grades[request_id]

        unique.append(row)

    unique.sort(
        key=lambda r: (
            r["start_time"], r["request_id"]
        )
    )

    save(
        OUT / "results.csv",
        unique,
        FIELDS
    )

    return unique, events, excluded


def make_latency_table(rows):
    groups = defaultdict(list)

    for row in rows:
        groups[row["scenario"]].append(row)

    order = [
        "steady", "burst", "overload", "halved",
        "daily_exhausted", "real_probe",
        "single_real", "retrieval_small",
        "retrieval_balanced", "retrieval_large",
        "retry_off", "retry_on"
    ]

    lines = [
        "| Scenario | Source | Requests | Duration (s) | "
        "Offered rate/min | First token p50/p95/p99 (ms) | "
        "Total p50/p95/p99 (ms) |",
        "|---|---|---:|---:|---:|---|---|"
    ]

    for scenario in order:
        group = groups.get(scenario, [])

        if not group:
            continue

        successful = [
            r for r in group
            if r["status"] == "ok"
        ]

        first = [
            number(r["first_token_ms"])
            for r in successful
        ]

        total = [
            number(r["total_ms"])
            for r in successful
        ]

        times = sorted(
            t for r in group
            if (t := parse_time(r["start_time"])) is not None
        )

        duration = "not measured"
        offered = "not measured"

        if len(times) >= 2:
            span = (
                times[-1] - times[0]
            ).total_seconds()

            if span > 0:
                offered = f"{(len(times) - 1) * 60 / span:.1f}"

                ends = [
                    parse_time(r["start_time"])
                    + timedelta(
                        milliseconds=number(r["total_ms"]) or 0
                    )
                    for r in group
                    if parse_time(r["start_time"]) is not None
                ]

                duration = (
                    f"{(max(ends) - times[0]).total_seconds():.1f}"
                )

        first_text = " / ".join(
            percentile(first, p)
            for p in [50, 95, 99]
        )

        total_text = " / ".join(
            percentile(total, p)
            for p in [50, 95, 99]
        )

        lines.append(
            f"| {scenario} | {group[0]['source']} | "
            f"{len(group)} | {duration} | {offered} | "
            f"{first_text} | {total_text} |"
        )

    return "\n".join(lines)


def make_outcome_table(rows):
    groups = defaultdict(list)

    for row in rows:
        groups[row["scenario"]].append(row)

    lines = [
        "| Scenario | Succeeded | Rate-limited | "
        "Timed out/given up | Retries/request | "
        "Peak queue | Tokens/answer | Cost/1,000 answers |",
        "|---|---:|---:|---:|---:|---|---|---|"
    ]

    queue_peaks = {
        "steady": 1,
        "burst": 28,
        "overload": 30,
        "halved": 6,
        "daily_exhausted": 1
    }

    for scenario, group in groups.items():
        total = len(group)
        ok = sum(r["status"] == "ok" for r in group)
        limited = sum(
            r["status"] == "rate_limited"
            for r in group
        )
        failed = sum(
            r["status"] in ["timeout", "error"]
            for r in group
        )

        retries = sum(
            number(r["retries"]) or 0
            for r in group
        ) / total

        token_pairs = [
            (number(r["tokens_in"]), number(r["tokens_out"]))
            for r in group
            if r["status"] == "ok"
        ]

        measured = [
            (a, b)
            for a, b in token_pairs
            if a is not None and b is not None
        ]

        if measured:
            avg_tokens = statistics.mean(
                a + b for a, b in measured
            )

            cost = statistics.mean(
                a * 0.075 / 1_000_000
                + b * 0.30 / 1_000_000
                for a, b in measured
            ) * 1000

            tokens_text = f"{avg_tokens:.0f}"
            cost_text = f"${cost:.3f}"

            if group[0]["source"] == "stand-in":
                tokens_text += " (assumed)"
                cost_text += " (modeled)"
            else:
                cost_text += " (list price)"
        else:
            tokens_text = "not measured"
            cost_text = "not measured"

        peak = queue_peaks.get(
            scenario, "not measured"
        )

        lines.append(
            f"| {scenario} | {percent(ok, total)} | "
            f"{percent(limited, total)} | "
            f"{percent(failed, total)} | "
            f"{retries:.2f} | {peak} | "
            f"{tokens_text} | {cost_text} |"
        )

    return "\n".join(lines)


def make_retrieval_table(rows, review):
    indexed = {
        r["request_id"]: r
        for r in rows
    }

    lines = [
        "| Setting | Questions asked | Correct and cited | "
        "Wrong | Correctly refused | Tokens/answer | "
        "First token p50/p95 (ms) | Total p50/p95 (ms) |",
        "|---|---:|---:|---:|---:|---:|---|---|"
    ]

    for setting, (size, top_k) in SETTINGS.items():
        records = {
            r["question_id"]: r
            for r in review
            if r["setting"] == setting
            and r["status"] == "ok"
            and r["model_answer"].strip()
        }

        matched = [
            indexed[r["request_id"]]
            for r in records.values()
            if r["request_id"] in indexed
        ]

        count = len(records)

        grades = [
            r["answer_grade"]
            for r in matched
            if r["answer_grade"] in GRADES
        ]

        if count == 15 and len(grades) == 15:
            correct = percent(
                grades.count("correct"), count
            )
            wrong = percent(
                grades.count("wrong")
                + grades.count("refused_wrongly"),
                count
            )
            refused = percent(
                grades.count("refused_correctly"),
                count
            )
        else:
            correct = wrong = refused = (
                f"not measured ({len(grades)}/{count} graded)"
            )

        tokens = [
            number(r["tokens_in"])
            + number(r["tokens_out"])
            for r in matched
            if number(r["tokens_in"]) is not None
            and number(r["tokens_out"]) is not None
        ]

        tokens_text = (
            f"{statistics.mean(tokens):.0f}"
            if tokens else "not measured"
        )

        first = [
            number(r["first_token_ms"])
            for r in matched
        ]

        total = [
            number(r["total_ms"])
            for r in matched
        ]

        first_text = " / ".join(
            percentile(first, p)
            for p in [50, 95]
        )

        total_text = " / ".join(
            percentile(total, p)
            for p in [50, 95]
        )

        lines.append(
            f"| {setting} ({size}w, top{top_k}, no rerank) | "
            f"{count}/15 | {correct} | {wrong} | "
            f"{refused} | {tokens_text} | "
            f"{first_text} | {total_text} |"
        )

    return "\n".join(lines)


def slow_request_analysis(events):
    groups = defaultdict(dict)

    for event in events:
        try:
            groups[event["request_id"]][event["event"]] = (
                float(event["elapsed_ms"])
            )
        except (KeyError, ValueError):
            continue

    candidates = []

    needed = [
        "arrived",
        "processing_started",
        "first_token",
        "completed"
    ]

    for request_id, event_times in groups.items():
        if all(k in event_times for k in needed):
            duration = (
                event_times["completed"]
                - event_times["arrived"]
            )

            candidates.append(
                (duration, request_id, event_times)
            )

    if not candidates:
        return "No complete event trace available."

    duration, request_id, e = max(candidates)

    waiting = (
        e["processing_started"] - e["arrived"]
    )

    before_token = (
        e["first_token"] - e["processing_started"]
    )

    after_token = (
        e["completed"] - e["first_token"]
    )

    return (
        f"Request {request_id}: {duration:.1f} ms total. "
        f"Queue waiting: {waiting:.1f} ms. "
        f"Processing before first token: "
        f"{before_token:.1f} ms. "
        f"Streaming after first token: "
        f"{after_token:.1f} ms. "
        "Retries: 0. This is a calibrated stand-in trace, "
        "not an internal Groq trace."
    )


def generate_tables(rows, review, events):
    table1 = """| Limit | Value | How found | Confidence |
|---|---|---|---|
| Requests/min | Published 30; account not verified | Groq documentation | Low |
| Tokens/min | Published 8,000; account not verified | Groq documentation | Low |
| Requests/day | Published 1,000; account not verified | Groq documentation | Low |
| Tokens/day | Published 200,000; account not verified | Groq documentation | Low |
| Concurrent requests | Not measured | No real concurrency probe | Low |
| Limit response | HTTP 429 observed | Retrieval experiments | High |
| Recovery time | Not measured | No verified recovery interval | Low |"""

    content = (
        "# Table 1 — Real Groq limits\n\n"
        + table1
        + "\n\n# Table 2a — Latency\n\n"
        + make_latency_table(rows)
        + "\n\n# Table 2b — Outcomes\n\n"
        + make_outcome_table(rows)
        + "\n\n# Table 3 — Retrieval configurations\n\n"
        + make_retrieval_table(rows, review)
        + "\n\n"
        + "Latency percentiles are calculated over successful "
        + "requests only. Simulated tokens and modeled costs "
        + "are assumptions, not measured Groq usage. "
        + "Offered rate uses the observed arrival interval. "
        + "Account limits require console verification."
    )

    (OUT / "RESULTS_TABLES.md").write_text(
        content, encoding="utf-8"
    )

    (OUT / "SLOW_TRACE.md").write_text(
        slow_request_analysis(events),
        encoding="utf-8"
    )


def generate_report():
    report = """# The Relay — Engineering Report
DRAFT: Keep the final report within two pages and include all required tables.

## 1. What I built and why
A Python RAG system using the three required versioned arXiv papers,
TF-IDF retrieval, Groq streaming, citations, and request-level metrics.
The most important design choice was grounding answers in paper evidence
rather than returning unsupported claims.

## 2. The real service and my stand-in
Ten real Groq probes gave 954.34 ms median TTFT and 996.28 ms median
total latency. The stand-in samples observed latency values, adds an
assumed 90 ms concurrency penalty above four active requests, injects
3% errors, and models rate limits. These concurrency assumptions were
not measured against the real service.

## 3. Results
See RESULTS_TABLES.md for all three required tables.
The calibrated steady test completed 20/20 requests with 1004 ms
median TTFT. The burst completed 50/50 with 3812 ms median TTFT.
Overload completed 25/80; 45 were rate-limited and 10 timed out.
These are simulated measurements, not actual Groq burst measurements.
The small-retrieval Q02 real request took 8012 ms.
Answer quality must be manually graded before final percentages
can be reported.

## 4. Where the time goes
See SLOW_TRACE.md for event-derived queue waiting, model work before
the first token, streaming after the first token, and retry count.
The real 8012 ms outlier was observed, but the internal causes
were not independently instrumented.

## 5. When a limit is hit
Per-minute exhaustion should delay requests only if retry-after
fits the deadline. Otherwise the system should reject transparently.
Daily exhaustion should stop generation instead of inventing answers.
The current pipeline reports 429 but does not yet implement a
predictive global admission controller.

## Retrieval: quality versus cost
We tested 120 words/top3, 220 words/top4, and 400 words/top6,
all using TF-IDF without reranking. Rate limits interrupted the
latter two configurations. Quality percentages require reviewed
answers. Near limits, reduce unnecessary context or refuse.

## How this library will mislead a naive retriever
Q05 retrieved training-data batching instead of encoder-decoder
processing. Q08 retrieved unrelated H-Net passages and produced
an incomplete Moshi answer. Q06 retrieved residual-connection
architecture details but produced an arguably unnecessary refusal.

## 6. Retries
Policy: at most one transient-error retry, respecting retry-after
and the request deadline. Synthetic injected 429 experiments show
that retrying without recovery increases latency without improving
success. This policy is demonstrated in the stand-in, not yet
implemented as automatic retries in the real pipeline.

## 7. What the person sees
"I can't answer from the papers right now because today's model
allowance is exhausted. I won't guess or invent citations. Please
try after the quota resets."

## 8. What I'm unsure about, what I left out, what I learned
The uncertain assumption is the stand-in's concurrency slowdown.
If wrong, its tail-latency predictions are unreliable. I left out
a neural reranker and hosted deployment. I learned that fast average
inference can still hide unacceptable long-tail latency.

## Your feedback on Vaani
The emphasis on low-latency conversation, turn-taking, and context
retention stood out. I found interruption-stop time and total
response-turn latency easy to confuse. I would show both definitions
alongside latency benchmarks.
Review and personalize this feedback before submission.

## How I worked with the assistant
Attach the genuine unedited conversation history or prompts.
Describe three actual prompts that mattered, the streaming
indentation/UTF-8 error you caught, one decision you overruled,
and which experiments and engineering decisions are yours.
"""

    (OUT / "REPORT_DRAFT.md").write_text(
        report, encoding="utf-8"
    )


def audit(rows, review, excluded):
    lines = [
        "# Submission Audit",
        "",
        f"Consolidated requests: {len(rows)}",
        f"Old uncalibrated rows excluded: {excluded}",
        ""
    ]

    counts = Counter(
        (r["scenario"], r["source"])
        for r in rows
    )

    for (scenario, source), count in sorted(counts.items()):
        lines.append(
            f"- {scenario} ({source}): {count}"
        )

    lines.append("\n## Remaining requirements")

    for setting in SETTINGS:
        completed = {
            r["question_id"]
            for r in review
            if r["setting"] == setting
            and r["status"] == "ok"
            and r["model_answer"].strip()
        }

        lines.append(
            f"- {setting}: {len(completed)}/15 "
            "questions completed"
        )

    ungraded = sum(
        r["status"] == "ok"
        and r["manual_grade"] not in GRADES
        for r in review
    )

    lines.extend([
        f"- Successful answers awaiting manual grade: {ungraded}",
        "- Verify actual account limits and 429 headers",
        "- Final report must fit two pages",
        "- Include complete AI conversation history",
        "- Include README and source code",
        "- Exclude .env and all private API keys",
        "- Verify final table values against results.csv"
    ])

    text = "\n".join(lines)

    (OUT / "AUDIT.md").write_text(
        text, encoding="utf-8"
    )

    print(text)


def main():
    review = prepare_quality_review()

    rows, events, excluded = combine_results(review)

    generate_tables(rows, review, events)
    generate_report()
    audit(rows, review, excluded)

    print("\nFINALIZATION FILES CREATED")
    print("Location:", OUT)
    print("1. results.csv")
    print("2. RESULTS_TABLES.md")
    print("3. REPORT_DRAFT.md")
    print("4. quality_review.csv")
    print("5. retry_trace.csv")
    print("6. SLOW_TRACE.md")
    print("7. AUDIT.md")


if __name__ == "__main__":
    main()
