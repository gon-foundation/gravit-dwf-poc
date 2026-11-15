"""Synthetic loan requests, deterministic per seed. Kinds mirror the seven scenarios of scenarios/run.py."""

import random

from pm_collateral.gate import LoanRequest, Position
from scenarios.run import AS_OF, TWO, quotes

MARKETS = ["FED-CUT-DEC26", "BTC-150K-2026", "EU-AIACT-FINES-2026"]
KINDS = ["valid"] * 8 + ["ltv_over", "inflated_mark", "overstated_value", "one_oracle", "resolved",
                         "concentrated", "not_allowed"]


def _basket(rnd):
    ms = rnd.sample(MARKETS, 3)
    return [Position(m, rnd.choice(["YES", "NO"]), rnd.randrange(10_000, 40_001, 1_000),
                     round(rnd.uniform(0.2, 0.8), 2)) for m in ms]


def _value(ps):
    return round(sum(p.quantity * p.mark_price for p in ps), 2)


def _balanced(rnd):
    while True:
        b = _basket(rnd)
        v = _value(b)
        if max(p.quantity * p.mark_price for p in b) / v <= 0.45:
            return b


def generate(n=150, seed=20261115):
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        kind = rnd.choice(KINDS)
        rid = f"req-{i + 1:04d}"
        b = _balanced(rnd)
        v = _value(b)
        loan = round(v * rnd.uniform(0.15, 0.38), -2)
        override, oracles = None, TWO
        if kind == "ltv_over":
            loan = round(v * rnd.uniform(0.45, 0.70), -2)
        elif kind == "inflated_mark":
            p = b[0]
            true = p.mark_price
            b[0] = Position(p.market, p.outcome, p.quantity, round(min(true + rnd.uniform(0.08, 0.2), 0.97), 2))
            override = {p.market: true}
            v = _value(b)
        elif kind == "overstated_value":
            v = round(v * rnd.uniform(1.05, 1.25), 2)
        elif kind == "one_oracle":
            oracles = ("oracle-venue-a",)
        elif kind == "resolved":
            b = b + [Position("OLD-ELECTION-25", "YES", rnd.randrange(5_000, 15_001, 1_000), 0.99)]
            v = _value(b)
        elif kind == "concentrated":
            b[0] = Position(b[0].market, b[0].outcome, b[0].quantity * 4, b[0].mark_price)
            v = _value(b)
        elif kind == "not_allowed":
            b = b + [Position("SPORTS-FINAL-26", "YES", 10_000, 0.5)]
            v = _value(b)
        req = LoanRequest(rid, "dwf-agent-ai", b, v, loan, AS_OF)
        view = {p.market: {o: (override or {}).get(p.market, p.mark_price) for o in oracles} for p in b}
        out.append((kind, req, quotes(req, oracles=oracles, price_override=override), view))
    return out
