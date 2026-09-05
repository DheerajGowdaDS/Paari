"""Step 9 validation: risk engine rules and thresholds."""

from __future__ import annotations

from paari.risk import RISK_ENGINE, RiskEngine, RiskLevel


def _ctx(**overrides) -> dict:
    base = {
        "tx": {"count_per_minute": 1, "seconds_since_last": 600, "amount_paise": 1000, "hour_utc": 12},
        "merchant": {
            "average_transaction_paise": 120000,
            "autonomous_limit_paise": 2000000,
            "active_hours_utc": [9, 10, 11, 12, 13, 14, 15, 16, 17],
        },
        "agent": {"age_hours": 48, "requested_cap_in_history": True},
    }
    for k, v in overrides.items():
        base[k] = v
    return base


def test_low_score_no_escalation() -> None:
    score = RISK_ENGINE.evaluate(_ctx())
    assert score.score < 30
    assert score.level == RiskLevel.LOW


def test_high_frequency_rule() -> None:
    score = RISK_ENGINE.evaluate(_ctx(tx={"count_per_minute": 6, "seconds_since_last": 600, "amount_paise": 1000, "hour_utc": 12}))
    assert "high_frequency" in score.triggered_rules
    assert score.score >= 40


def test_rapid_repeat_rule() -> None:
    score = RISK_ENGINE.evaluate(_ctx(tx={"count_per_minute": 1, "seconds_since_last": 10, "amount_paise": 1000, "hour_utc": 12}))
    assert "rapid_repeat" in score.triggered_rules


def test_large_transaction_rule() -> None:
    # amount > avg * 3 (120000 * 3 = 360000)
    score = RISK_ENGINE.evaluate(_ctx(tx={"count_per_minute": 1, "seconds_since_last": 600, "amount_paise": 500000, "hour_utc": 12}))
    assert "large_transaction" in score.triggered_rules


def test_just_below_limit_rule() -> None:
    # amount > limit * 0.95 (2000000 * 0.95 = 1900000)
    score = RISK_ENGINE.evaluate(_ctx(tx={"count_per_minute": 1, "seconds_since_last": 600, "amount_paise": 1950000, "hour_utc": 12}))
    assert "just_below_limit" in score.triggered_rules


def test_new_agent_high_value_rule() -> None:
    score = RISK_ENGINE.evaluate(_ctx(agent={"age_hours": 2, "requested_cap_in_history": True}, tx={"count_per_minute": 1, "seconds_since_last": 600, "amount_paise": 600000, "hour_utc": 12}))
    assert "new_agent_high_value" in score.triggered_rules


def test_capability_escalation_rule() -> None:
    score = RISK_ENGINE.evaluate(_ctx(agent={"age_hours": 48, "requested_cap_in_history": False}))
    assert "capability_escalation" in score.triggered_rules


def test_round_amount_rule() -> None:
    score = RISK_ENGINE.evaluate(_ctx(tx={"count_per_minute": 1, "seconds_since_last": 600, "amount_paise": 1500000, "hour_utc": 12}))
    assert "round_amount" in score.triggered_rules


def test_unusual_hour_rule() -> None:
    score = RISK_ENGINE.evaluate(_ctx(tx={"count_per_minute": 1, "seconds_since_last": 600, "amount_paise": 1000, "hour_utc": 3}))
    assert "unusual_hour" in score.triggered_rules


def test_high_score_forces_review() -> None:
    score = RISK_ENGINE.evaluate(
        _ctx(
            tx={"count_per_minute": 6, "seconds_since_last": 10, "amount_paise": 1950000, "hour_utc": 3},
            agent={"age_hours": 2, "requested_cap_in_history": False},
        )
    )
    assert score.level == RiskLevel.HIGH
    assert score.is_high


def test_custom_rules() -> None:
    from paari.risk import RiskRule

    custom = RiskRule("always", "tx.flag", True, "eq", 100)
    engine = RiskEngine(rules=(custom,))
    score = engine.evaluate(_ctx(tx={"flag": True}))
    assert score.triggered_rules == ["always"]
    assert score.score == 100
