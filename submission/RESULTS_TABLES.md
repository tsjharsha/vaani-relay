# Table 1 — Real Groq limits

| Limit | Value | How found | Confidence |
|---|---|---|---|
| Requests/min | Published 30; account not verified | Groq documentation | Low |
| Tokens/min | 8,000 TPM | Actual Groq HTTP 429 response: limit 8,000, used 6,749, requested 1,705 | High |
| Requests/day | Published 1,000; account not verified | Groq documentation | Low |
| Tokens/day | Published 200,000; account not verified | Groq documentation | Low |
| Concurrent requests | Not measured | No real concurrency probe | Low |
| Limit response | HTTP 429 observed | Retrieval experiments | High |
| Recovery time | Not measured | No verified recovery interval | Low |

# Table 2a — Latency

| Scenario | Source | Requests | Duration (s) | Offered rate/min | First token p50/p95/p99 (ms) | Total p50/p95/p99 (ms) |
|---|---|---:|---:|---:|---|---|
| steady | stand-in | 20 | 20.3 | 59.6 | 1004.3 / 1121.3 / 1126.5 | 1098.5 / 1215.3 / 1219.9 |
| burst | stand-in | 50 | 9.7 | 958.2 | 3811.8 / 6003.5 / 6472.9 | 3905.2 / 6097.2 / 6566.5 |
| overload | stand-in | 80 | 5.4 | 959.6 | 2006.5 / 3117.3 / 3640.9 | 2100.7 / 3210.9 / 3735.3 |
| halved | stand-in | 40 | 4.3 | 548.8 | 1379.7 / 1800.8 / 1921.9 | 1478.9 / 1894.6 / 2016.6 |
| daily_exhausted | stand-in | 20 | 3.9 | 294.4 | not measured / not measured / not measured | not measured / not measured / not measured |
| real_probe | real | 10 | 27.9 | 20.0 | 954.3 / 1077.3 / 1111.6 | 996.3 / 1120.1 / 1153.4 |
| single_real | real | 2 | 38689.0 | 0.0 | 1352.9 / 1379.8 / 1382.2 | 1490.7 / 1504.9 / 1506.1 |
| retrieval_small | real | 15 | 51.6 | 16.6 | 1075.5 / 3218.7 / 6917.1 | 1132.0 / 3300.0 / 7069.6 |
| retrieval_balanced | real | 16 | 1461.7 | 0.6 | 1184.0 / 1570.4 / 1751.5 | 1301.5 / 1716.8 / 1875.7 |
| retrieval_large | real | 10 | 2766.5 | 0.2 | 1598.8 / 2012.3 / 2103.5 | 1811.6 / 2047.1 / 2115.4 |
| retry_off | stand-in | 12 | 1.3 | 600.0 | not measured / not measured / not measured | not measured / not measured / not measured |
| retry_on | stand-in | 12 | 1.7 | 600.0 | not measured / not measured / not measured | not measured / not measured / not measured |

# Table 2b — Outcomes

| Scenario | Succeeded | Rate-limited | Timed out/given up | Retries/request | Peak queue | Tokens/answer | Cost/1,000 answers |
|---|---:|---:|---:|---:|---|---|---|
| single_real | 100.0% | 0.0% | 0.0% | 0.00 | not measured | 1625 | $0.185 (list price) |
| real_probe | 100.0% | 0.0% | 0.0% | 0.00 | not measured | 195 | $0.038 (list price) |
| retry_on | 0.0% | 100.0% | 0.0% | 1.00 | not measured | not measured | not measured |
| retry_off | 0.0% | 100.0% | 0.0% | 0.00 | not measured | not measured | not measured |
| steady | 100.0% | 0.0% | 0.0% | 0.00 | 1 | 770 (assumed) | $0.085 (modeled) |
| burst | 100.0% | 0.0% | 0.0% | 0.00 | 28 | 770 (assumed) | $0.085 (modeled) |
| overload | 31.2% | 56.2% | 12.5% | 0.00 | 30 | 770 (assumed) | $0.085 (modeled) |
| halved | 35.0% | 62.5% | 2.5% | 0.00 | 6 | 770 (assumed) | $0.085 (modeled) |
| daily_exhausted | 0.0% | 100.0% | 0.0% | 0.00 | 1 | not measured | not measured |
| retrieval_small | 100.0% | 0.0% | 0.0% | 0.00 | not measured | 890 | $0.116 (list price) |
| retrieval_balanced | 93.8% | 6.2% | 0.0% | 0.00 | not measured | 1585 | $0.182 (list price) |
| retrieval_large | 70.0% | 30.0% | 0.0% | 0.00 | not measured | 3143 | $0.305 (list price) |

# Table 3 — Retrieval configurations

| Setting | Questions asked | Correct and cited | Wrong | Correctly refused | Tokens/answer | First token p50/p95 (ms) | Total p50/p95 (ms) |
|---|---:|---:|---:|---:|---:|---|---|
| small (120w, top3, no rerank) | 15/15 | 53.3% | 26.7% | 20.0% | 890 | 1075.5 / 3218.7 | 1132.0 / 3300.0 |
| balanced (220w, top4, no rerank) | 14/15 | 64.3% | 14.3% | 21.4% | 1567 | 1184.0 / 1570.4 | 1268.4 / 1731.0 |
| large (400w, top6, no rerank) | 7/15 | 71.4% | 28.6% | 0.0% | 3143 | 1598.8 / 2012.3 | 1811.6 / 2047.1 |

Latency percentiles are calculated over successful requests only. Simulated tokens and modeled costs are assumptions, not measured Groq usage. Offered rate uses the observed arrival interval. Account limits require console verification.
