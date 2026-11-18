"""Frozen training, weighting and bootstrap regression fixtures."""
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import phase1_model_metrics as metrics


def row(identifier, label, probability, at=10, end=20, available=20):
    return dict(round_id=identifier, planned_start_us=0, offset=30, at_us=at,
        ends_at_us=end, label_available_at_us=available, label=label,
        p_up=probability, valuation_status="VALUED", model="M0")


def test_training_cutoff_microseconds_and_allowed_empty_states():
    assert metrics.fit_m1([], cutoff_us=100, as_of_us=200)["fit_status"] == "FIT_EMPTY"
    assert metrics.fit_m1([row("u", "UP", .9)], cutoff_us=100, as_of_us=200)["fit_status"] == "FIT_SINGLE_CLASS"
    rows = [row("u", "UP", .9), row("d", "DOWN", .1),
            row("future", "UP", .01, available=101)]
    fit = metrics.fit_m1(rows, cutoff_us=100, as_of_us=200)
    reference = metrics.fit_m1(rows[:2], cutoff_us=100, as_of_us=200)
    assert fit["fit_status"] == "FIT_OK"
    assert fit["a"] == reference["a"]
    assert fit["b"] == reference["b"]


def test_b1_uses_unique_official_rounds_not_slot_coverage():
    rows = [row("u", "UP", None)] * 6 + [row("d", "DOWN", None)]
    result = metrics.fit_b1(rows, cutoff_us=100, as_of_us=200)
    assert result["counted_rounds"] == 2
    assert result["value"] == .5
    assert metrics.fit_b1([row("u", "UP", None)], cutoff_us=100, as_of_us=200)["value"] == 1
    assert metrics.fit_b1([row("d", "DRAW", None)], cutoff_us=100, as_of_us=200)["value"] is None


def test_objective_gradient_independent_finite_difference_and_round_weights():
    probabilities = np.array([.2, .8, .7])
    logits = np.log(probabilities / (1 - probabilities))
    labels = np.array([0., 1., 0.])
    weights = np.array([.25, .25, .5])
    slope, intercept = .7, -.2
    gradient = metrics._gradient(slope, intercept, logits, labels, weights)
    def objective(slope, intercept):
        scores = slope * logits + intercept
        return float(np.sum(weights * (np.logaddexp(0, scores) - labels * scores))
            + .0005 * ((slope - 1) ** 2 + intercept ** 2))
    epsilon = 1e-6
    expected = ((objective(slope + epsilon, intercept) - objective(slope - epsilon, intercept)) / (2 * epsilon),
                (objective(slope, intercept + epsilon) - objective(slope, intercept - epsilon)) / (2 * epsilon))
    assert gradient == pytest.approx(expected, abs=1e-9)
    assert metrics._objective(slope, intercept, logits, labels, weights) == pytest.approx(objective(slope, intercept), abs=1e-15)


def test_shared_pcg64_indices_keep_zero_days_and_small_period_not_applicable():
    rows = [dict(period="test", series=series, day=f"2026-08-{day:02}",
                 numerator=1 if day == 10 else 0, denominator=1 if day == 10 else 0)
            for series in ("left", "right") for day in (10, 11)]
    result = metrics.bootstrap_statistics(rows)["periods"]["test"]
    index = result["day_block"]["index"]
    expected = np.random.Generator(np.random.PCG64(42)).integers(0, 2, size=(1000, 2), dtype=np.int64)
    assert np.array_equal(index, expected)
    assert result["seven_day_block"]["status"] == "N/A_INSUFFICIENT_BLOCKS"
    assert result["day_block"]["series"]["left"] == result["day_block"]["series"]["right"]
    assert result["day_block"]["series"]["left"]["invalid_replicates"] > 0


def test_streamed_round_weights_and_orthogonal_draw_coverage():
    def slot(planned, offset, probability, label="UP"):
        return dict(planned_start_us=planned, round_id=str(planned), offset=offset,
            starts_at_us=planned, ends_at_us=planned+300_000_000,
            at_us=planned+offset*1_000_000, label_available_at_us=planned+300_000_000,
            label=label, label_status=label, m0_p_up=probability, m0_samples=20,
            m0_sigma_raw=.00005, m0_sigma=.00005, m0_floor_hit=True,
            m0_valuation_status="VALUED" if probability is not None else "WARMUP",
            m2_low_p_up=probability, m2_high_p_up=probability, spot=100., strike=100.,
            m0_source_epoch=1, m0_reset_reason="FIRST_SAMPLE")
    rows = [slot(0, 30, .8), slot(0, 60, .6), slot(300_000_000, 30, .2),
            slot(600_000_000, 30, None, "DRAW")]
    accumulator = metrics.Statistics(0, 900_000_000, 10**15)
    for group in ([rows[0], rows[1]], [rows[2]], [rows[3]]):
        accumulator.add_round([metrics.model_rows(item, {}) for item in group])
    raw = accumulator.finish({})
    record = next(item for item in raw["rows"] if item["period"] == "ALL" and
        item["comparison_set"] == "OWN" and item["model"] == "M0" and
        item["metric"] == "binary_brier" and item["offset"] == "ALL" and item["stratum"] == "ALL")
    assert record["numerator"] == pytest.approx(.1 + .64)
    assert record["denominator"] == 2
    assert record["value"] == pytest.approx(.37)
    assert raw["coverage"]["M0"]["draw_label"] == 1
    assert raw["coverage"]["M0"]["unvalued"] == 1
    assert raw["coverage"]["B2"]["valid_probability"] == 0


# Contract fixture for the abstain counter (SPEC-06-003 4.6.2). One round of six
# offsets holding a legal probability above/at/below 0.5, a warmup slot, a
# missing-spot slot and exactly tied spot/strike pairs.
# (offset, M0 p, M2-low p, M2-high p, native status, spot, strike, label)
ABSTAIN_SLOTS = (
    (30, .7, .6, .8, "VALUED", 101., 100., "UP"),
    (60, .5, .5, .5, "VALUED", 100., 100., "DOWN"),
    (120, None, None, None, "WARMUP", 100., 100., "UP"),
    (180, .3, .2, .4, "VALUED", 99., 100., "DOWN"),
    (240, None, None, None, "MISSING_SPOT", None, 100., "UP"),
    (270, .5, .55, .45, "VALUED", 100., 100., "UP"),
)
ABSTAIN_EXPECTED = {
    "M0": dict(valid_probability=4, unvalued=2, directed=2, abstain=2),
    "M1": dict(valid_probability=0, unvalued=6, directed=0, abstain=0),
    "M2-low": dict(valid_probability=4, unvalued=2, directed=3, abstain=1),
    "M2-high": dict(valid_probability=4, unvalued=2, directed=3, abstain=1),
    "B0": dict(valid_probability=6, unvalued=0, directed=0, abstain=6),
    "B1": dict(valid_probability=0, unvalued=6, directed=0, abstain=0),
    "B2": dict(valid_probability=0, unvalued=6, directed=2, abstain=3),
}
ABSTAIN_AS_OF = 10**15


def abstain_wide(index, values):
    offset, m0_p, low_p, high_p, status, spot, strike, label = values
    planned = 0
    at_us = offset*1_000_000
    return dict(planned_start_us=planned, round_id=str(planned), offset=offset,
        starts_at_us=planned, ends_at_us=planned+300_000_000, at_us=at_us,
        label=label, label_available_at_us=planned+300_000_000, label_status="BINARY_"+label,
        m0_p_up=m0_p, m0_sigma_raw=.00005, m0_sigma=.00005, m0_samples=20,
        m0_valuation_status=status, m0_source_epoch=1, m0_reset_reason="FIRST_SAMPLE",
        m2_low_p_up=low_p, m2_low_sigma_raw=.00005, m2_low_sigma=.00005, m2_low_samples=20,
        m2_low_valuation_status=status, m2_high_p_up=high_p, m2_high_sigma_raw=.00005,
        m2_high_sigma=.00005, m2_high_samples=20, m2_high_valuation_status=status,
        spot=spot, strike=strike, spot_available_at_us=at_us if spot is not None else None,
        strike_available_at_us=planned)


def abstain_implementation():
    slots = [metrics.model_rows(abstain_wide(index, values), {})
             for index, values in enumerate(ABSTAIN_SLOTS)]
    accumulator = metrics.Statistics(0, 300_000_000, ABSTAIN_AS_OF)
    accumulator.add_round(slots)
    return accumulator


def abstain_reference_rows():
    """The independent reference view of the same contract fixture."""
    probabilities = {"M0": [values[1] for values in ABSTAIN_SLOTS],
                     "M1": [None]*len(ABSTAIN_SLOTS),
                     "M2-low": [values[2] for values in ABSTAIN_SLOTS],
                     "M2-high": [values[3] for values in ABSTAIN_SLOTS],
                     "B0": [.5]*len(ABSTAIN_SLOTS),
                     "B1": [None]*len(ABSTAIN_SLOTS),
                     "B2": [None]*len(ABSTAIN_SLOTS)}
    rows = []
    for index, values in enumerate(ABSTAIN_SLOTS):
        offset, _, _, _, status, spot, strike, label = values
        at_us = offset*1_000_000
        for model in metrics.MODEL_NAMES:
            probability = probabilities[model][index]
            if model == "B2":
                direction = None
                if status in ("VALUED", "WARMUP") and spot is not None:
                    direction = "UP" if spot > strike else "DOWN" if spot < strike else None
            elif probability is None:
                direction = None
            else:
                direction = "UP" if probability > .5 else "DOWN" if probability < .5 else None
            rows.append(dict(model=model, offset=offset, planned_start_us=0, round_id="0",
                at_us=at_us, label=label, label_available_at_us=300_000_000,
                p_up=probability, direction=direction,
                valuation_status=(status if model in ("M0", "M1", "M2-low", "M2-high")
                                 else "NOT_APPLICABLE"),
                spot=spot, strike=strike, sigma_raw=.00005,
                spot_available_at_us=at_us if spot is not None else None,
                strike_available_at_us=0, period="TRAIN_PREFIX", fold=None))
    return rows


def test_abstain_counts_only_legal_exact_ties_not_unvalued_slots():
    accumulator = abstain_implementation()
    for model, expected in ABSTAIN_EXPECTED.items():
        for name, value in expected.items():
            assert accumulator.coverage[model][name] == value, (model, name)


def test_reference_abstain_counts_only_legal_exact_ties_not_unvalued_slots():
    import phase1_reference as reference
    _, _, coverage = reference.reference_reduction(iter(abstain_reference_rows()), ABSTAIN_AS_OF)
    for model, expected in ABSTAIN_EXPECTED.items():
        for name, value in expected.items():
            assert coverage[model][name] == value, (model, name)


def test_reference_and_implementation_agree_slot_by_slot_on_abstain():
    import phase1_reference as reference
    accumulator = abstain_implementation()
    _, _, coverage = reference.reference_reduction(iter(abstain_reference_rows()), ABSTAIN_AS_OF)
    for model in metrics.MODEL_NAMES:
        expected = {name: value for name, value in coverage[model].items()
                    if name != "probability_coverage"}
        assert expected == dict(accumulator.coverage[model]), model


def test_reference_audit_statistics_accepts_the_fixed_contract_fixture(tmp_path):
    """The independent reference audit recomputes coverage from the samples."""
    import json

    import phase1_reference as reference
    directory = tmp_path / "fixture"
    directory.mkdir()
    wide = [abstain_wide(index, values) for index, values in enumerate(ABSTAIN_SLOTS)]
    metrics.materialize_run(iter(wide), directory, mode="small", start_us=0,
                            end_us=300_000_000, as_of_us=ABSTAIN_AS_OF, check=lambda: None)
    (directory / "params.json").write_text(json.dumps(dict(
        start_us=0, end_us=300_000_000, as_of_us=ABSTAIN_AS_OF)))
    audited = reference.audit_statistics(directory)
    for model, expected in ABSTAIN_EXPECTED.items():
        assert audited["coverage"][model]["abstain"] == expected["abstain"], model
        assert audited["coverage"][model]["unvalued"] == expected["unvalued"], model


@pytest.mark.parametrize("field", ["spot_available_at_us", "strike_available_at_us"])
def test_b2_future_price_ties_never_abstain_in_statistics_or_independent_audit(tmp_path, field):
    """Exact ties are not abstentions until both prices are available."""
    import json
    import phase1_reference as reference
    wide = [abstain_wide(index, values) for index, values in enumerate(ABSTAIN_SLOTS)]
    for row in wide:
        if row["spot"] == row["strike"]:
            row[field] = row["at_us"] + 1
    slots = [metrics.model_rows(row, {}) for row in wide]
    accumulator = metrics.Statistics(0, 300_000_000, ABSTAIN_AS_OF)
    accumulator.add_round(slots)
    assert accumulator.coverage["B2"]["abstain"] == 0
    assert accumulator.coverage["B2"]["unvalued"] == 6
    assert accumulator.coverage["B2"]["directed"] == 2
    directory = tmp_path / "future-tie"
    directory.mkdir()
    metrics.materialize_run(iter(wide), directory, mode="small", start_us=0,
        end_us=300_000_000, as_of_us=ABSTAIN_AS_OF, check=lambda: None)
    (directory / "params.json").write_text(json.dumps(dict(
        start_us=0, end_us=300_000_000, as_of_us=ABSTAIN_AS_OF)))
    audited = reference.audit_statistics(directory)
    assert audited["coverage"]["B2"]["abstain"] == 0
    assert audited["coverage"]["B2"]["unvalued"] == 6
    assert audited["coverage"]["B2"]["directed"] == 2


def test_real_small_evidence_abstain_counts_read_only():
    """Existing archived small run: read-only recomputation of the fixed counters."""
    import phase1_reference as reference
    source = reference.EVIDENCE / "validate-small" / "samples.csv"
    if not source.exists():
        pytest.skip("archived small evidence is not present")
    _, _, coverage = reference.reference_reduction(reference.decoded_csv(source), ABSTAIN_AS_OF)
    assert coverage["M0"]["abstain"] == 0
    assert coverage["M0"]["unvalued"] == 2
    assert coverage["M1"]["abstain"] == 0
    assert coverage["M1"]["unvalued"] == 6
    assert coverage["M2-low"]["abstain"] == 0
    assert coverage["M2-high"]["abstain"] == 0
    assert coverage["B0"]["abstain"] == 6
    assert coverage["B1"]["abstain"] == 0
    assert coverage["B1"]["unvalued"] == 6
    assert coverage["B2"]["abstain"] == 0


@pytest.mark.parametrize("field,value", [
    ("spot_available_at_us", None), ("strike_available_at_us", None),
    ("spot_available_at_us", 60_000_001), ("strike_available_at_us", 60_000_001)])
def test_b2_unavailable_tie_is_not_an_abstention(field, value):
    import phase1_reference as reference
    slots = []
    for index, values in enumerate(ABSTAIN_SLOTS):
        wide = abstain_wide(index, values)
        if wide["offset"] == 60:
            wide[field] = value
        slots.append(metrics.model_rows(wide, {}))
    accumulator = metrics.Statistics(0, 300_000_000, ABSTAIN_AS_OF)
    accumulator.add_round(slots)
    independent_rows = abstain_reference_rows()
    for sample in independent_rows:
        if sample["offset"] == 60:
            sample[field] = value
    _, _, coverage = reference.reference_reduction(iter(independent_rows), ABSTAIN_AS_OF)
    # Only the other two exact-price ties have causally available inputs.
    assert accumulator.coverage["B2"]["abstain"] == 2
    assert coverage["B2"]["abstain"] == 2
    assert accumulator.coverage["B0"]["abstain"] == coverage["B0"]["abstain"] == 6


def test_memmap_fitting_matches_scalar_and_filters_late_label(tmp_path):
    data = np.zeros(4, dtype=metrics.FIT_DTYPE)
    data["planned_start_us"] = [0, 0, 300_000_000, 600_000_000]
    data["offset"] = [30, 60, 30, 30]
    data["at_us"] = data["planned_start_us"] + data["offset"]*1_000_000
    data["ends_at_us"] = data["planned_start_us"]+300_000_000
    data["label_available_at_us"] = [300_000_000, 300_000_000, 600_000_000, 1_000_000_001]
    data["p0"] = [.8, .6, .2, .999]
    data["label_code"] = [1, 1, 0, 0]
    data["valued"] = True
    path = tmp_path / "day.npy"
    np.save(path, data, allow_pickle=False)
    fit = metrics.fit_days([path], cutoff_us=1_000_000_000, as_of_us=2_000_000_000)
    scalar = metrics.fit_m1([dict(round_id=str(int(item["planned_start_us"])),
        planned_start_us=int(item["planned_start_us"]), offset=int(item["offset"]),
        at_us=int(item["at_us"]), ends_at_us=int(item["ends_at_us"]),
        label_available_at_us=int(item["label_available_at_us"]),
        label="UP" if item["label_code"] else "DOWN", p_up=float(item["p0"])) for item in data],
        cutoff_us=1_000_000_000, as_of_us=2_000_000_000)
    assert fit["fit_status"] == scalar["fit_status"] == "FIT_OK"
    assert [fit["a"], fit["b"]] == pytest.approx([scalar["a"], scalar["b"]], abs=1e-10)
    assert fit["unique_rounds"] == 2 and fit["slot_count"] == 3
    import phase1_reference as reference
    independent = reference.independent_fit([path], 1_000_000_000, 2_000_000_000)
    assert independent["fit_status"] == "FIT_OK"
    assert [fit["a"], fit["b"]] == pytest.approx([independent["a"], independent["b"]], abs=1e-5)
    assert fit["objective"] == pytest.approx(independent["objective"], abs=1e-10)
    data["p0"][-1] = .01
    data["label_code"][-1] = 1
    np.save(path, data, allow_pickle=False)
    changed_future = metrics.fit_days([path], cutoff_us=1_000_000_000, as_of_us=2_000_000_000)
    assert changed_future["input_hash"] == fit["input_hash"]
    assert changed_future["a"] == fit["a"] and changed_future["b"] == fit["b"]


def test_primary_support_is_not_diagnostic_and_selector():
    primary = dict(difference=-.01, interval=dict(lo95=-.02, hi95=-.001),
        availability=dict(folds_fit_ok=True, every_fold_nonempty=True,
            interval_usable=True), numerically_identical=False)
    assert metrics.classify(primary, engineering=True) == "SUPPORT_FURTHER_VALIDATION"
    primary["availability"]["every_fold_nonempty"] = False
    assert metrics.classify(primary, engineering=True) == "INSUFFICIENT_EVIDENCE"
    assert metrics.classify(primary, engineering=False) == "DATA_ENGINEERING_INELIGIBLE"


@pytest.mark.parametrize("probability,label", [(0., "UP"), (1., "DOWN"), (.5, "UP"), (.9999999999999999, "DOWN")])
def test_scoring_clip_uses_probability_before_complement(probability, label):
    import math
    import phase1_reference as reference
    clipped = min(1-1e-12, max(1e-12, probability))
    expected = -math.log(clipped if label == "UP" else 1-clipped)
    assert metrics._binary_loss(probability, label) == pytest.approx(expected, abs=1e-12)
    assert reference.reference_logloss(probability, label) == pytest.approx(expected, abs=1e-12)


def test_eight_fold_primary_improvement_keeps_logloss_conflict_and_independent_sums():
    import phase1_reference as reference
    start, end = metrics.CUTOFFS[0], metrics.CUTOFFS[8]
    fits = {str(index): dict(m1=dict(fit_status="FIT_OK", a=1., b=8.),
        b1=dict(value=.5)) for index in range(9)}
    engine = metrics.Statistics(start, end, end+10**12)
    samples = []
    for day in range(56):
        for number in range(11):
            planned = start+day*metrics._DAY_US+number*300_000_000
            label, probability = ("UP", .6) if number < 10 else ("DOWN", .4)
            slots = []
            for offset in metrics.OFFSETS:
                wide = dict(planned_start_us=planned, round_id=str(planned), starts_at_us=planned,
                    ends_at_us=planned+300_000_000, at_us=planned+offset*1_000_000,
                    offset=offset, label=label, label_available_at_us=planned+300_000_000,
                    label_status="BINARY_"+label, m0_p_up=probability,
                    m0_sigma_raw=.00005, m0_sigma=.00005, m0_samples=20,
                    m0_valuation_status="VALUED", m2_low_p_up=probability,
                    m2_high_p_up=probability, spot=100.+probability, strike=100.)
                rows = metrics.model_rows(wide, fits)
                slots.append(rows)
                samples.extend(rows)
            engine.add_round(slots)
    raw = engine.finish(fits)
    assert raw["preaudit_classification"] == "SUPPORT_FURTHER_VALIDATION"
    assert raw["primary_evidence"]["availability"]["every_fold_nonempty"]
    assert raw["primary_evidence"]["interval"]["hi95"] < 0
    assert any(row.get("metric") == "binary_logloss_difference" and row["value"] > 0
        for row in raw["diagnostic_conflicts"])
    losses, buckets, coverage = reference.reference_reduction(iter(samples), end+10**12)
    assert coverage == raw["coverage"]
    for row in raw["rows"]:
        if row["metric"] in ("ece", "ece_difference"):
            continue
        key = tuple(row[name] for name in ("period", "offset", "stratum", "model", "reference", "comparison_set", "metric"))
        values = losses[key]
        assert row["numerator"] == pytest.approx(sum(value[0] for value in values.values()), abs=1e-12)
        assert row["denominator"] == sum(value[1] for value in values.values())
    expected_index = np.random.Generator(np.random.PCG64(42)).integers(0, 56, size=(1000, 56), dtype=np.int64)
    assert np.array_equal(raw["indices"]["VALIDATION_day"], expected_index)
    assert raw["bootstrap"]["FOLD_0"]["seven_key"] is None


def test_training_c_is_inclusive_for_label_but_exclusive_for_predictions():
    admitted = [row("up", "UP", .8, at=99, end=100, available=100),
                row("down", "DOWN", .2, at=99, end=100, available=100)]
    excluded = [row("late-label", "DOWN", .99, available=101),
                row("late-end", "DOWN", .99, end=101), row("at-c", "DOWN", .99, at=100),
                row("draw", "DRAW", .99)]
    actual = metrics.fit_m1(admitted+excluded, cutoff_us=100, as_of_us=1000)
    expected = metrics.fit_m1(admitted, cutoff_us=100, as_of_us=1000)
    assert actual["a"] == expected["a"] and actual["b"] == expected["b"]
    assert actual["slot_count"] == 2
    assert actual["availability_excluded_count"] == 1
    assert actual["window_excluded_count"] == 2
    assert actual["draw_excluded_count"] == 1


def test_not_converged_cannot_emit_identity_mapping_or_last_iterate_probability():
    rows = [row("up", "UP", .4), row("down", "DOWN", .6)]
    fit = metrics._fit_core(rows, 100, 200, {}, max_iterations=0)
    assert fit["fit_status"] == "FIT_NOT_CONVERGED"
    assert fit["a"] is fit["b"] is fit["p1"] is None
    assert fit["reason"] == "ITERATION_LIMIT"
    assert fit["last_iterate"] == dict(a=1., b=0.)


def test_all_nine_file_backed_fits_and_b1_official_denominator(tmp_path):
    import phase1_model_research as research
    import phase1_reference as reference
    directory = tmp_path / "fit-days"
    directory.mkdir()
    start = research.to_us(research.START)
    first = np.zeros(4, dtype=metrics.FIT_DTYPE)
    first["planned_start_us"] = [start, start, start+300_000_000, start+600_000_000]
    first["offset"] = [30, 60, 30, 30]
    first["at_us"] = first["planned_start_us"]+first["offset"]*1_000_000
    first["ends_at_us"] = first["planned_start_us"]+300_000_000
    first["label_available_at_us"] = first["ends_at_us"]
    first["p0"] = [.7, .8, .2, 0.]
    first["label_code"] = [1, 1, 0, 0]
    first["valued"] = [True, True, True, False]
    second = np.zeros(1, dtype=metrics.FIT_DTYPE)
    second["planned_start_us"] = metrics.CUTOFFS[0]
    second["offset"] = 30
    second["at_us"] = metrics.CUTOFFS[0]+30_000_000
    second["ends_at_us"] = second["label_available_at_us"] = metrics.CUTOFFS[0]+300_000_000
    second["p0"], second["label_code"], second["valued"] = .6, 1, True
    np.save(directory / "2026-08-10.npy", first, allow_pickle=False)
    np.save(directory / "2026-09-21.npy", second, allow_pickle=False)
    official = [dict(round_id=str(int(planned)), planned_start_us=int(planned),
        ends_at_us=int(planned)+300_000_000, label_available_at_us=int(planned)+300_000_000,
        label=label) for planned, label in ((start, "UP"), (start+300_000_000, "DOWN"),
            (start+600_000_000, "DOWN"), (metrics.CUTOFFS[0], "UP"))]
    research.write_csv(tmp_path / "rounds.csv", official)
    fits = metrics.fit_from_files(tmp_path, as_of_us=research.to_us(research.AS_OF), check=lambda: None)
    assert set(fits) == {str(index) for index in range(9)}
    assert fits["0"]["b1"]["counted_rounds"] == 3
    assert fits["0"]["b1"]["value"] == pytest.approx(1/3)
    assert fits["1"]["b1"]["counted_rounds"] == 4
    assert fits["1"]["b1"]["value"] == .5
    for index in range(9):
        actual = fits[str(index)]["m1"]
        expected = reference.independent_fit(list(directory.glob("*.npy")), metrics.CUTOFFS[index], research.to_us(research.AS_OF))
        assert actual["fit_status"] == expected["fit_status"] == "FIT_OK"
        assert actual["input_hash"] == expected["input_hash"]
        assert [actual["a"], actual["b"]] == pytest.approx([expected["a"], expected["b"]], abs=1e-5)
        assert actual["objective"] == pytest.approx(expected["objective"], abs=1e-10)
