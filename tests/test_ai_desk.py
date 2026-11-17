import copy

from ai_desk.desk import run, standin
from observer import EXCEPTION, verify


def test_valid_requests_are_consistent_and_bad_ones_caught():
    obs, seal, summary, ok = run(standin)
    assert ok
    for e in obs.entries:
        kind = e["body"]["executed"]["kind"]
        if kind == "valid":
            assert e["body"]["finding"] != EXCEPTION, e["body"]["reason"]
    assert summary["risk_taken"] > 0
    # every risky approval of the stand-in is one of the kinds it does not check
    assert set(summary["risk_taken_by_kind"]) <= {"one_oracle", "concentrated", "inflated_mark",
                                                  "overstated_value", "resolved"}


def test_hiding_a_risky_approval_is_detected():
    obs, seal, _, _ = run(standin, n=60)
    entries = copy.deepcopy(obs.entries)
    i = next(k for k, e in enumerate(entries) if e["body"]["finding"] == EXCEPTION)
    entries[i]["body"]["finding"] = "CONSISTENT"
    ok, why = verify(entries, seal, seal["public_key"])
    assert not ok


def test_changing_the_model_answer_afterwards_is_detected():
    obs, seal, _, _ = run(standin, n=60)
    entries = copy.deepcopy(obs.entries)
    entries[3]["body"]["executed"]["model"]["decision"] = "REJECT"
    ok, why = verify(entries, seal, seal["public_key"])
    assert not ok and "modified" in why
