"""Config YAML sanity: tiers map to the schema enum, gates default safe."""

from app.config import (
    escalation_config,
    feature_flags,
    pos_facility_map,
    pricing_thresholds,
)

# flow2_findings.benchmark_tier CHECK values
VALID_TIERS = {"below_threshold", "higher_side", "solid_leverage", "strong_leverage"}


def test_pricing_tiers_match_schema_enum():
    tiers = pricing_thresholds()["tiers"]
    assert {t["tier"] for t in tiers} == VALID_TIERS
    # exactly one open-ended (null max) band, and it suggests escalation
    open_ended = [t for t in tiers if t["max_multiple"] is None]
    assert len(open_ended) == 1
    assert open_ended[0]["tier"] == "strong_leverage"
    assert open_ended[0]["suggest_escalation"] is True


def test_feature_gates_default_safe():
    flags = feature_flags()
    assert flags["nsa_citations_enabled"] is False
    assert flags["flow3_air_ambulance_enabled"] is False
    assert flags["appeal_letter_generation_enabled"] is False


def test_pos_map_default_non_facility():
    pos = pos_facility_map()
    assert pos["default"] == "non_facility"
    assert "11" in pos["non_facility"]  # office
    assert "21" in pos["facility"]  # inpatient hospital


def test_escalation_handoff_type():
    esc = escalation_config()["human_advocate"]
    assert esc["default_handoff_type"] == "in_house_advocate"
    trigger_ids = {t["id"] for t in esc["triggers"]}
    assert "air_ambulance_out_of_scope" in trigger_ids
