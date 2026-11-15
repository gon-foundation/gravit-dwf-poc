# AI loan desk: two ways to put Gravit next to an AI agent

A real open model decides on collateral loan requests against prediction-market
positions. The same 150 synthetic requests run through two variants, so the
choice can be made on numbers:

- **Variant A, Gravit in the risk path.** The collateral gate checks every
  model approval *before* execution and blocks it if the policy does not hold.
  The gate is open source and runs on the partner's own machine; no outside
  service is involved.
- **Variant B, Gravit outside the risk path.** The model's decision is executed
  as today. The post-trade observer re-checks it afterwards, signs every
  finding into a hash-chained log and seals the day. Nothing is delayed or
  blocked.

In both variants every finding goes to the partner only.

## Result (15 November 2026)

Model: Qwen2.5-3B-Instruct Q4_K_M (weights sha256 `626b4a66...5c62d`), llama.cpp,
greedy decoding. 150 synthetic requests (seed 20261115): 84 that meet the
policy, 66 that break it in one of seven ways.

| | Variant A: gate before execution | Variant B: observer after execution |
|---|---|---|
| Risky model approvals | 53 | 53 |
| ...executed | **0** (all 53 blocked) | **53** (all 53 found and reported) |
| Sound requests the model refused | 12 | 12 (reported as lost business) |
| Added latency per decision | median 2.5 ms, p99 2.8 ms | none |
| Signed, sealed record | gate log, 150 entries | observer log, 150 entries, seal verifies |

The 53 risky approvals by kind: price confirmed by one oracle only 13, loan
above LTV 9, position concentrated 8, mark above oracle price 8, value
overstated 7, resolved market 6, market not allowed 2.

Re-sending every fifth request (30) to the same model returned byte-identical
answers in 30 of 30 cases.

What this means: the model is useful but not safe on its own. With the gate,
none of its 53 risky approvals is executed, at a cost of about 2.5 ms per
decision. With the observer, all 53 are executed but each one is found, named
and provable afterwards. Which variant fits is the partner's decision; both
can also run together (gate for new limits, observer for everything).

## Run it

```bash
make setup PYTHON=python3.12
.venv/bin/python -m ai_desk.desk                    # stand-in model, no LLM needed
llama-server -m qwen2.5-3b-instruct-q4_k_m.gguf --port 8080 --seed 1 &
.venv/bin/python -m ai_desk.desk http://127.0.0.1:8080 "Qwen2.5-3B-Instruct Q4_K_M"
.venv/bin/python -m pytest -q
```

Results: `results/ai-desk-log.jsonl`, `results/ai-desk-seal.json`, `results/ai-desk-summary.json`.

All requests, prices, oracles, keys and the policy are fictitious test data.
No connection to DWF Labs systems or any venue.
