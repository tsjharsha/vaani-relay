
import csv
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "groq_probe.csv"
OUTPUT = ROOT / "calibration.json"

with SOURCE.open(encoding="utf-8", newline="") as f:
    rows = list(csv.DictReader(f))

successful = [
    r for r in rows
    if r["status"] == "ok"
    and r["first_token_ms"]
    and r["total_ms"]
]

if len(successful) < 5:
    raise SystemExit("Need at least 5 successful real samples.")

ttft = [float(r["first_token_ms"]) for r in successful]
total = [float(r["total_ms"]) for r in successful]
stream = [max(0, t - f) for t, f in zip(total, ttft)]

calibration = {
    "source": "Real Groq streaming probe",
    "sample_count": len(successful),
    "model": successful[0]["model"],
    "ttft_samples_ms": ttft,
    "stream_samples_ms": stream,
    "median_ttft_ms": statistics.median(ttft),
    "median_total_ms": statistics.median(total),
    "limitations": [
        "Only short sequential prompts were sampled",
        "No concurrent real requests were tested",
        "Queue slowdown and errors are modeled assumptions",
        "This sample does not establish daily or minute limits"
    ]
}

OUTPUT.write_text(
    json.dumps(calibration, indent=2),
    encoding="utf-8"
)

print("CALIBRATION COMPLETE")
print("Real samples:", len(successful))
print("Median TTFT:", round(statistics.median(ttft), 2), "ms")
print("Median total:", round(statistics.median(total), 2), "ms")
print("Created calibration.json")
