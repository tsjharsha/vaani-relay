
import argparse
import asyncio
import csv
import json
import random
import statistics
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results.csv"
EVENTS = ROOT / "events.csv"
CALIBRATION = ROOT / "calibration.json"

FIELDS = [
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

SCENARIOS = {
    "steady": {
        "count": 20,
        "rate": 60,
        "rpm": 120,
        "daily": 1000,
        "workers": 8,
    },
    "burst": {
        "count": 50,
        "rate": 1200,
        "rpm": 120,
        "daily": 1000,
        "workers": 8,
    },
    "overload": {
        "count": 80,
        "rate": 1200,
        "rpm": 25,
        "daily": 1000,
        "workers": 8,
    },
    "halved": {
        "count": 40,
        "rate": 600,
        "rpm": 15,
        "daily": 1000,
        "workers": 8,
    },
    "daily_exhausted": {
        "count": 20,
        "rate": 300,
        "rpm": 120,
        "daily": 0,
        "workers": 8,
    },
}


class Simulator:
    def __init__(self, scenario, seed=42):
        self.scenario = scenario
        self.cfg = SCENARIOS[scenario]
        self.rng = random.Random(seed)

        if not CALIBRATION.exists():
            raise FileNotFoundError(
                "calibration.json not found. "
                "Run python calibrate.py first."
            )

        with CALIBRATION.open(encoding="utf-8") as f:
            self.calibration = json.load(f)

        self.ttft_samples = self.calibration[
            "ttft_samples_ms"
        ]
        self.stream_samples = self.calibration[
            "stream_samples_ms"
        ]

        if (
            not self.ttft_samples
            or len(self.ttft_samples)
            != len(self.stream_samples)
        ):
            raise ValueError(
                "Invalid calibration samples."
            )

        self.queue = asyncio.Queue(maxsize=30)
        self.rows = []
        self.events = []

        self.peak_queue = 0
        self.used_today = 0
        self.recent = []
        self.active = 0

        self.request_timeout = 8.0

    def log(self, request_id, event):
        self.events.append({
            "request_id": request_id,
            "scenario": self.scenario,
            "event": event,
            "elapsed_ms": round(
                (time.perf_counter() - self.begin)
                * 1000,
                2,
            ),
        })

    def finish(self, row):
        row["total_ms"] = round(
            (time.perf_counter() - row["_start"])
            * 1000,
            2,
        )

    def check_limit(self):
        now = time.monotonic()

        self.recent = [
            timestamp
            for timestamp in self.recent
            if now - timestamp < 60
        ]

        if self.used_today >= self.cfg["daily"]:
            return "daily_limit"

        if len(self.recent) >= self.cfg["rpm"]:
            return "minute_limit"

        self.recent.append(now)
        self.used_today += 1

        return None

    async def execute(self, row):
        request_id = row["request_id"]

        self.log(request_id, "processing_started")

        limit = self.check_limit()

        if limit is not None:
            row["status"] = "rate_limited"
            self.log(request_id, limit)
            return

        self.active += 1

        try:
            sample_index = self.rng.randrange(
                len(self.ttft_samples)
            )

            real_ttft_ms = float(
                self.ttft_samples[sample_index]
            )

            real_stream_ms = float(
                self.stream_samples[sample_index]
            )

            # The baseline first-token latency comes
            # from the real Groq probe.
            #
            # The concurrency penalty is an explicit
            # simulation assumption, NOT a measured
            # Groq performance characteristic.

            pressure = max(0, self.active - 4)
            extra_delay_ms = pressure * 90

            simulated_ttft = (
                real_ttft_ms + extra_delay_ms
            ) / 1000

            self.log(request_id, "model_started")

            await asyncio.sleep(simulated_ttft)

            # Synthetic failure injection.
            # The 3% probability is an assumption.
            if self.rng.random() < 0.03:
                row["status"] = "error"
                self.log(
                    request_id,
                    "simulated_provider_error",
                )
                return

            row["first_token_ms"] = round(
                (time.perf_counter() - row["_start"])
                * 1000,
                2,
            )

            self.log(request_id, "first_token")

            # Simulate a streamed answer delivered
            # in six pieces.
            stream_piece_delay = (
                real_stream_ms / 6
            ) / 1000

            for piece in range(6):
                await asyncio.sleep(
                    stream_piece_delay
                )

                self.log(
                    request_id,
                    f"stream_chunk_{piece + 1}",
                )

            # Illustrative fixed token counts.
            # These are NOT measured Groq usage.
            row["tokens_in"] = 650
            row["tokens_out"] = 120

            row["status"] = "ok"

            self.log(request_id, "completed")

        finally:
            self.active -= 1

    async def worker(self):
        while True:
            row = await self.queue.get()

            if row is None:
                self.queue.task_done()
                return

            try:
                await asyncio.wait_for(
                    self.execute(row),
                    timeout=self.request_timeout,
                )

            except asyncio.TimeoutError:
                row["status"] = "timeout"
                self.log(
                    row["request_id"],
                    "processing_timeout",
                )

            except Exception as exc:
                row["status"] = "error"
                self.log(
                    row["request_id"],
                    "unexpected_error",
                )

                print(
                    "Worker error:",
                    type(exc).__name__,
                    str(exc),
                )

            finally:
                self.finish(row)
                self.queue.task_done()

    async def run(self):
        self.begin = time.perf_counter()

        workers = [
            asyncio.create_task(self.worker())
            for _ in range(
                self.cfg["workers"]
            )
        ]

        interval = 60 / self.cfg["rate"]

        for i in range(self.cfg["count"]):
            request_id = str(uuid.uuid4())

            row = {
                "request_id": request_id,
                "scenario": self.scenario,
                "source": "stand-in",
                "start_time": datetime.now(
                    timezone.utc
                ).isoformat(),
                "first_token_ms": "",
                "total_ms": "",
                "status": "timeout",
                "retries": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "retrieval_setting": (
                    "220w_40overlap_top4_tfidf"
                ),
                "answer_grade": "",
                "_start": time.perf_counter(),
            }

            self.rows.append(row)

            self.log(request_id, "arrived")

            try:
                self.queue.put_nowait(row)

                self.log(request_id, "queued")

                self.peak_queue = max(
                    self.peak_queue,
                    self.queue.qsize(),
                )

            except asyncio.QueueFull:
                # The assignment allows only:
                # ok, rate_limited, timeout, error.
                #
                # Queue abandonment is stored as
                # timeout, but the event log records
                # the real reason separately.
                row["status"] = "timeout"

                self.finish(row)

                self.log(
                    request_id,
                    "queue_rejected",
                )

            await asyncio.sleep(interval)

        await self.queue.join()

        for _ in workers:
            await self.queue.put(None)

        await asyncio.gather(*workers)

        self.duration = (
            time.perf_counter() - self.begin
        )

    def save(self):
        new_results = (
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
                fieldnames=FIELDS,
            )

            if new_results:
                writer.writeheader()

            for row in self.rows:
                writer.writerow({
                    key: row.get(key, "")
                    for key in FIELDS
                })

        event_columns = [
            "request_id",
            "scenario",
            "event",
            "elapsed_ms",
        ]

        # Use a separate event file for the
        # calibrated experiments. This avoids
        # mixing it with earlier event schemas.
        event_path = ROOT / "events_calibrated.csv"

        new_events = (
            not event_path.exists()
            or event_path.stat().st_size == 0
        )

        with event_path.open(
            "a",
            newline="",
            encoding="utf-8",
        ) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=event_columns,
            )

            if new_events:
                writer.writeheader()

            writer.writerows(self.events)

    def summary(self):
        total_requests = len(self.rows)

        successful = [
            row
            for row in self.rows
            if row["status"] == "ok"
        ]

        first_token_times = [
            row["first_token_ms"]
            for row in successful
            if isinstance(
                row["first_token_ms"],
                (int, float),
            )
        ]

        total_times = [
            row["total_ms"]
            for row in successful
        ]

        def percentile(values, percentage):
            if not values:
                return None

            sorted_values = sorted(values)

            position = (
                (len(sorted_values) - 1)
                * percentage / 100
            )

            lower = int(position)
            upper = min(
                lower + 1,
                len(sorted_values) - 1,
            )

            weight = position - lower

            return (
                sorted_values[lower]
                * (1 - weight)
                + sorted_values[upper]
                * weight
            )

        def report_latency(label, values):
            if not values:
                print(label, ": not measured")
                return

            print(
                f"{label}: "
                f"p50={percentile(values, 50):.2f} ms | "
                f"p95={percentile(values, 95):.2f} ms | "
                f"p99={percentile(values, 99):.2f} ms"
            )

        print("\n" + "=" * 55)
        print("RELAY — CALIBRATED LOAD TEST")
        print("=" * 55)

        print("Scenario:", self.scenario)
        print(
            "Model calibration:",
            self.calibration.get("model", "unknown"),
        )
        print(
            "Real calibration samples:",
            len(self.ttft_samples),
        )

        print("Requests:", total_requests)

        print(
            "Duration:",
            round(self.duration, 2),
            "seconds",
        )

        print(
            "Offered rate:",
            round(
                total_requests
                / self.duration * 60,
                2,
            ),
            "requests/min",
        )

        print("Peak queue:", self.peak_queue)

        print("\nOUTCOMES")

        for status in [
            "ok",
            "rate_limited",
            "timeout",
            "error",
        ]:
            count = sum(
                row["status"] == status
                for row in self.rows
            )

            percentage = (
                count / total_requests * 100
            )

            print(
                f"{status}: "
                f"{count} ({percentage:.1f}%)"
            )

        print("\nLATENCY — SUCCESSFUL REQUESTS ONLY")

        report_latency(
            "First token",
            first_token_times,
        )

        report_latency(
            "Total time",
            total_times,
        )

        print("\nMODEL ASSUMPTIONS")
        print(
            "- Baseline latency sampled from "
            "real Groq measurements."
        )
        print(
            "- Additional 90 ms per active "
            "request above concurrency 4."
        )
        print(
            "- Synthetic provider error "
            "probability: 3%."
        )
        print(
            "- Synthetic token usage: "
            "650 input + 120 output."
        )
        print(
            "- No retry policy implemented yet."
        )

        print("\nFILES SAVED")
        print("- results.csv")
        print("- events_calibrated.csv")
        print("=" * 55)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "RELAY calibrated stand-in model"
        )
    )

    parser.add_argument(
        "scenario",
        choices=list(SCENARIOS),
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
    )

    args = parser.parse_args()

    simulator = Simulator(
        args.scenario,
        args.seed,
    )

    asyncio.run(simulator.run())

    simulator.save()
    simulator.summary()


if __name__ == "__main__":
    main()
