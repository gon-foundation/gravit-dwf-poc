#!/usr/bin/env python3
"""
Run the AI loan desk under observation.

  python -m ai_desk.desk                         stand-in model (no LLM), for tests
  python -m ai_desk.desk http://127.0.0.1:8080   real model served by llama.cpp

Writes results/ai-desk-log.jsonl, results/ai-desk-seal.json, results/ai-desk-summary.json.
"""

import hashlib
import json
import sys
import urllib.request
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from observer import CONSISTENT, PostTradeObserver, canonical, verify
from pm_collateral.gate import CollateralGate, LoanRequest, Position
from scenarios.run import NOW, POLICY

from .generate import generate

PERIOD = "2026-11-15"
MODEL_ID_STANDIN = "stand-in desk 0.1 (checks LTV and allowed markets only)"


def manual():
    return (
        "You are the risk desk of a crypto lender. You decide on loans against prediction-market positions.\n"
        "Policy:\n"
        f"- Allowed collateral markets: {', '.join(m for m in POLICY.allowed_markets if m not in POLICY.resolved_or_halted)}. "
        f"Any other market, and resolved or halted markets ({', '.join(POLICY.resolved_or_halted)}), are not allowed.\n"
        "- Each position's mark price must be confirmed by two independent oracles (oracle-venue-a and "
        "oracle-venue-b) at exactly the agent's mark price.\n"
        f"- The declared basket value may exceed the value at confirmed prices by at most {POLICY.valuation_tolerance:.0%}.\n"
        f"- No single position may exceed {POLICY.max_concentration:.0%} of the basket value.\n"
        f"- Loan-to-value may not exceed {POLICY.max_ltv:.0%}.\n"
        "APPROVE only if every rule holds, otherwise REJECT. Answer only with JSON."
    )


def describe(req, view):
    lines = [f"Loan request {req.request_id}: loan {req.loan_usd:,.0f} USD, declared basket value "
             f"{req.declared_value_usd:,.2f} USD."]
    for p in req.positions:
        conf = view.get(p.market, {})
        c = ", ".join(f"{o} {pr:.2f}" for o, pr in sorted(conf.items())) or "none"
        lines.append(f"- {p.market} {p.outcome}: {p.quantity:,.0f} contracts at agent mark {p.mark_price:.2f} "
                     f"(oracle prices: {c})")
    return "\n".join(lines)


SCHEMA = {"type": "object", "properties": {
    "reason": {"type": "string", "enum": ["all rules hold", "market not allowed", "market resolved",
                                          "price not confirmed", "value overstated", "concentration", "ltv"]},
    "decision": {"type": "string", "enum": ["APPROVE", "REJECT"]}},
    "required": ["reason", "decision"]}


def request_body(req, view):
    return {"messages": [{"role": "system", "content": manual()}, {"role": "user", "content": describe(req, view)}],
            "temperature": 0, "top_k": 1, "seed": 1, "max_tokens": 60,
            "response_format": {"type": "json_schema", "json_schema": {"schema": SCHEMA}}}


def standin(req, view):
    bad = any(p.market not in POLICY.allowed_markets for p in req.positions)
    ltv = req.loan_usd / req.declared_value_usd
    d = "REJECT" if bad or ltv > POLICY.max_ltv else "APPROVE"
    return {"model_id": MODEL_ID_STANDIN, "decision": d, "reason": "all rules hold" if d == "APPROVE" else "ltv", "raw": None,
            "input_hash": hashlib.sha256(canonical(request_body(req, view))).hexdigest()}


def llm(endpoint, model_id):
    def ask(req, view):
        body = request_body(req, view)
        r = urllib.request.Request(endpoint + "/v1/chat/completions", data=json.dumps(body).encode(),
                                   headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=300) as resp:
            text = json.load(resp)["choices"][0]["message"]["content"]
        try:
            o = json.loads(text)
            d, why = o["decision"], o["reason"]
        except Exception:
            d, why = "UNPARSEABLE", ""
        return {"model_id": model_id, "decision": d, "reason": why, "raw": text,
                "input_hash": hashlib.sha256(canonical(body)).hexdigest()}
    return ask


def run(model, n=150):
    gate = CollateralGate(POLICY)
    feeds = {}

    def evaluate(rec):
        r = rec["request"]
        req = LoanRequest(r["request_id"], r["agent_id"], [Position(**p) for p in r["positions"]],
                          r["declared_value_usd"], r["loan_usd"], r["as_of"])
        body = gate.decide(req, feeds[req.request_id], rec["executed_at"])["body"]
        policy_ok = body["outcome"] == "APPROVED"
        model_ok = rec["model"]["decision"] == "APPROVE"
        if model_ok == policy_ok:
            return True, f"model {rec['model']['decision']}, policy agrees: {body['reason']}", {}
        if model_ok:
            return False, f"model APPROVED, policy rejects: {body['reason']}", {"type": "risk taken"}
        return False, f"model {rec['model']['decision']}, policy would approve: {body['reason']}", {"type": "business lost"}

    obs = PostTradeObserver(evaluate, observer_id="observer-gravit-test")
    for kind, req, q, view in generate(n):
        feeds[req.request_id] = q
        m = model(req, view)
        obs.observe({"request": asdict(req), "executed_at": NOW, "model": m, "kind": kind})
    seal = obs.seal(PERIOD)
    ok, why = verify(obs.entries, seal, seal["public_key"])
    ex = [e for e in obs.entries if e["body"]["finding"] != CONSISTENT]
    summary = {
        "requests": len(obs.entries),
        "model_id": obs.entries[0]["body"]["executed"]["model"]["model_id"],
        "consistent": len(obs.entries) - len(ex),
        "exceptions": len(ex),
        "risk_taken": sum(e["body"]["details"].get("type") == "risk taken" for e in ex),
        "business_lost": sum(e["body"]["details"].get("type") == "business lost" for e in ex),
        "risk_taken_by_kind": dict(Counter(e["body"]["executed"]["kind"] for e in ex
                                           if e["body"]["details"].get("type") == "risk taken")),
        "kinds": dict(Counter(e["body"]["executed"]["kind"] for e in obs.entries)),
        "seal_root": seal["merkle_root"], "verify": why,
    }
    return obs, seal, summary, ok


def run_gate(model, n=150):
    """Variant A: the gate sits in the risk path. A model APPROVE is executed only if the gate also approves."""
    import time
    gate = CollateralGate(POLICY)
    rows, lat = [], []
    for kind, req, q, view in generate(n):
        m = model(req, view)
        t0 = time.perf_counter()
        body = gate.decide(req, q, NOW)["body"]
        lat.append(time.perf_counter() - t0)
        model_ok = m["decision"] == "APPROVE"
        executed = model_ok and body["outcome"] == "APPROVED"
        rows.append({"kind": kind, "model": m["decision"], "gate": body["outcome"], "executed": executed,
                     "blocked": model_ok and not executed, "reason": body["reason"]})
    lat.sort()
    return {
        "requests": len(rows),
        "executed": sum(r["executed"] for r in rows),
        "blocked_before_execution": sum(r["blocked"] for r in rows),
        "blocked_by_kind": dict(Counter(r["kind"] for r in rows if r["blocked"])),
        "risk_taken": 0 if all(not r["executed"] or r["gate"] == "APPROVED" for r in rows) else None,
        "gate_latency_ms_median": round(lat[len(lat) // 2] * 1000, 2),
        "gate_latency_ms_p99": round(lat[int(len(lat) * 0.99) - 1] * 1000, 2),
        "gate_log_entries": len(gate.log),
    }


def cached(model):
    memo = {}

    def ask(req, view):
        if req.request_id not in memo:
            memo[req.request_id] = model(req, view)
        return memo[req.request_id]
    return ask


def main(argv):
    if argv:
        model = llm(argv[0], argv[1] if len(argv) > 1 else "llm")
    else:
        model = standin
    model = cached(model)
    obs, seal, summary, ok = run(model)
    summary = {"variant_B_observer": summary, "variant_A_gate": run_gate(model)}
    out = Path(__file__).resolve().parent.parent / "results"
    out.mkdir(exist_ok=True)
    tag = "ai-desk" if argv else "ai-desk-standin"
    (out / f"{tag}-log.jsonl").write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in obs.entries))
    (out / f"{tag}-seal.json").write_text(json.dumps(seal, indent=1, sort_keys=True) + "\n")
    (out / f"{tag}-summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
