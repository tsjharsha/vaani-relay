# The Relay — Vaani ML Engineering Assignment

A Python retrieval-augmented generation (RAG) pipeline with real Groq streaming, document retrieval, load simulation, answer-quality evaluation, and request-level performance measurements.

## Documents

The system uses these exact arXiv versions:

- Attention Is All You Need — `1706.03762v7`
- Moshi — `2410.00037v1`
- Dynamic Chunking — `2507.07955v2`

## Technology

- Python
- Groq API — `openai/gpt-oss-20b`
- PyMuPDF for PDF extraction
- scikit-learn TF-IDF for retrieval
- Requests for streaming API calls
- CSV and JSON for experiment records

## Setup

Requires Python and a Groq API key.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_own_groq_api_key
```

Never commit `.env` or the real API key.

## Running the system

Run the interactive retrieval pipeline:

```powershell
python relay.py
```

Run the real-provider calibration probe:

```powershell
python real_probe.py
python calibrate.py
```

Run the calibrated stand-in load experiments:

```powershell
python simulator.py
```

Run the retrieval-quality evaluation:

```powershell
python evaluate.py
```

Resume incomplete retrieval evaluation without repeating completed questions:

```powershell
python resume_evaluation.py --setting large --delay 10
```

Real-provider scripts consume API quota. Load-test and retry outputs must not be interpreted as real Groq concurrency measurements.

## Pipeline

1. Extract text from three versioned research papers.
2. Split the documents into retrievable passages.
3. Retrieve relevant passages using TF-IDF similarity.
4. Construct a question-and-evidence prompt.
5. Call the Groq model and stream the response.
6. Log request timings, outcomes, token counts, retrieval settings, and available answer grades.

## Experiments

Five calibrated stand-in traffic scenarios were evaluated: steady, burst, overload, halved rate limit, and exhausted daily quota.

Three retrieval settings were evaluated: small (120 words, top 3 passages), balanced (220 words, top 4), and large (400 words, top 6). The small configuration completed 15/15 questions, balanced completed 14/15, and large completed 7/15. Results must be interpreted with these differing completion counts.

Ten real Groq calibration probes measured median time to first token of approximately **954 ms** and median total latency of approximately **996 ms**.

## Results and submission files

Inside `submission/`:

- `results.csv` — consolidated per-request measurements
- `RESULTS_TABLES.md` — provider limits, latency and outcomes, retrieval comparisons
- `REPORT_DRAFT.md` — engineering report
- `quality_review.csv` — reviewed evaluation responses and grades
- `retry_trace.csv` — simulated retry experiment records
- `SLOW_TRACE.md` — calibrated stand-in latency breakdown
- `AUDIT.md` — record counts and completion checks

Raw experiment records include `groq_probe.csv`, `retrieval_runs.csv`, and `evaluation_answers.csv`.

## Important limitations

The stand-in was calibrated from sequential real calls, not real concurrent-provider measurements. Its concurrency penalty and injected error probability are assumptions.

Provider HTTP 429 errors were observed, including an 8,000-token-per-minute limit reported in an actual response. Other account quotas have not all been independently verified.

The real pipeline detects rate limits but does not implement predictive global admission control or automatic retry execution. Retry-policy experiments use synthetic failure injection.

Quality results for the balanced and large retrieval configurations are incomplete because of provider throttling. Missing measurements have not been fabricated.

## AI assistance

AI assistance was used for implementation, debugging, test generation, and reporting. The engineering report distinguishes observed measurements from simulated assumptions. The genuine conversation history is provided separately.

## Security

Do not upload `.env`, API credentials, virtual environments, or personal secrets. Repository users must supply their own Groq API key.