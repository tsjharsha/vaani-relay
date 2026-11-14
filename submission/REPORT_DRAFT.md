# The Relay — Engineering Report

## 1. What I built and why

I built a Python retrieval-augmented generation (RAG) pipeline using three versioned papers: *Attention Is All You Need* (1706.03762v7), *Moshi* (2410.00037v1), and *Dynamic Chunking* (2507.07955v2). The pipeline retrieves relevant passages using TF-IDF, constructs a grounded prompt, calls Groq's `openai/gpt-oss-20b`, streams the response, and records request-level metrics. I prioritized traceable citations and explicit refusals over unsupported answers.

## 2. The real service and my stand-in

Ten successful real Groq probes measured median time to first token (TTFT) of **954.3 ms** and median total latency of **996.3 ms**. The stand-in uses these measurements for calibration, then models concurrency, queueing, token streaming, errors, and exhausted quotas.

The stand-in assumes an additional 90 ms of latency per active request beyond four concurrent requests, with a 3% injected error probability. These are assumptions, **not experimentally established properties of Groq**. Therefore, simulated tail latencies are useful for comparing load-handling strategies, not predicting Groq's actual production performance.

## 3. Results

The accompanying `RESULTS_TABLES.md` contains the three required detailed tables; `results.csv` contains the underlying per-request records.

Under calibrated stand-in load, steady traffic completed **20/20** requests with **1,004 ms** median TTFT, while a 50-request burst completed **50/50** with **3,812 ms** median TTFT. Under overload, only **25/80** succeeded; **45** were rate-limited and **10** timed out. Halving the modeled limit produced **14/40** successes. The daily-exhaustion scenario rejected **20/20** requests. These are simulated results, not real Groq concurrency tests.

Across real retrieval experiments, some requests received HTTP 429 responses. A real Groq error reported an **8,000-token/minute** limit, including the current token usage and requested amount. Other published account-limit figures were not independently verified.

## 4. Where the time goes

A slow calibrated stand-in request took **6,628.8 ms**: **5,280.9 ms** queue waiting (79.7%), **1,255.1 ms** processing before the first token (18.9%), and **92.8 ms** streaming afterward (1.4%). It had no retries. In this example, queueing—not streaming—dominated user-perceived delay. This is a stand-in event trace, not internal Groq instrumentation.

## 5. When a limit is hit

A temporary 429 should trigger a bounded retry only when the server's recovery guidance fits the request deadline. Otherwise, the system should report the limit instead of silently waiting. Daily quota exhaustion should fail fast with an honest user-facing explanation. The current real pipeline detects and reports rate limits but does **not** implement predictive global admission control or automatic live-provider retries.

## Retrieval: quality versus cost

Three TF-IDF configurations were evaluated without reranking:

| Setting | Completed | Correct and cited | Wrong | Correct refusal |
|---|---:|---:|---:|---:|
| Small: 120 words, top 3 | 15/15 | 53.3% | 26.7% | 20.0% |
| Balanced: 220 words, top 4 | 14/15 | 64.3% | 14.3% | 21.4% |
| Large: 400 words, top 6 | 7/15 | 71.4% | 28.6% | 0.0% |

These percentages use **completed, reviewed questions as their denominators**. They are not directly comparable accuracy estimates because rate limits prevented completion of the balanced and large test sets. Larger retrieval contexts also consumed more tokens per request. I would provisionally favor balanced retrieval rather than claim large is best based on seven questions.

## How this library will mislead a naive retriever

The documents contain overlapping technical vocabulary but discuss different architectures. For example, the encoder–decoder question retrieved training-data material rather than the relevant Transformer explanation. The Moshi question encountered unrelated H-Net material, while a residual-connection question produced an unnecessary refusal. Keyword similarity alone does not guarantee evidence relevance; a more reliable system needs better passage selection and citation validation.

## 6. Retries

The proposed policy allows **at most one retry** for a transient failure, subject to recovery guidance and a deadline. Synthetic retry experiments demonstrate a case where repeating a 429 without quota recovery **does not improve success** and increases delay. These retry comparisons are simulated; the real pipeline does not yet implement automatic retry execution.

## 7. What the person sees

When daily model allowance is exhausted, the interface should say: *“I can't answer from the papers right now because the model allowance is exhausted. I won't guess or invent citations. Please try again when the quota resets.”* For transient throttling, it should distinguish a temporary delay from a full-day exhaustion rather than repeatedly showing a loading indicator.

## 8. What I'm unsure about, what I left out, what I learned

My largest uncertainty is the stand-in's concurrency penalty, because it was not validated against real parallel Groq traffic. I did not build a neural reranker, predictive quota controller, or hosted deployment. The largest lesson was that low median model latency does not guarantee good interactive performance: queueing, quota limits, and retrieval quality can dominate the experience.

## Your feedback on Vaani

Vaani's focus on conversational latency and turn-taking makes the distinction between the first audible response and complete turn latency especially important. I would like to see interruption-stop latency and end-to-end conversational-turn latency defined and reported separately alongside benchmarks. This is my suggested product feedback, not a measured finding from the Relay experiments.

## How I worked with the assistant

I used AI assistance to structure the Python pipeline, create experimental scripts, debug streaming, and summarize measured results. Three consequential interactions were requesting a runnable implementation, investigating malformed streaming output, and correcting incomplete retrieval-quality percentages. I checked the resulting code and outputs rather than treating generated text as evidence.

One important correction involved streamed UTF-8 handling, where malformed output required changes to decoding. I also retained incomplete test counts instead of presenting missing measurements as successes. The reported measurements come from the executed scripts and recorded outputs; synthetic observations are explicitly labeled. The complete conversation history is supplied separately rather than reconstructed as invented prompts.