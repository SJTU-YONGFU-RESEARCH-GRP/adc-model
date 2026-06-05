"""Tests for cross-engine parity helpers."""

from __future__ import annotations

from adc_model.engine_compare import (
    EngineMetrics,
    collect_metric_spread_rows,
    compare_engine_metrics,
    format_metric_spread_table,
    within_relative_tol,
)


def _row(
    *,
    label: str = "default",
    engine: str = "python",
    max_inl_lsb: float = 4.441,
    max_dnl_lsb: float = 1.0,
    sndr_db: float = 58.92,
    sfdr_db: float = 85.66,
    thd_db: float = 79.85,
    enob_bits: float = 9.50,
) -> EngineMetrics:
    """Build a minimal metrics row for parity tests."""
    return EngineMetrics(
        label=label,
        engine=engine,
        max_inl_lsb=max_inl_lsb,
        max_dnl_lsb=max_dnl_lsb,
        sndr_db=sndr_db,
        sfdr_db=sfdr_db,
        thd_db=thd_db,
        enob_bits=enob_bits,
    )


def test_within_relative_tol_zero_lsb_uses_absolute() -> None:
    """Near-zero INL/DNL should use the 0.02 LSB absolute band."""
    assert within_relative_tol(0.0, 0.01, is_lsb=True)
    assert not within_relative_tol(0.0, 0.03, is_lsb=True)


def test_within_relative_tol_percent_error() -> None:
    """Non-zero metrics should use relative 2% tolerance."""
    assert within_relative_tol(58.92, 58.93, rtol=0.02)
    assert not within_relative_tol(58.92, 55.0, rtol=0.02)


def test_compare_engine_metrics_identical_rows_pass() -> None:
    """Identical Python and ngspice rows should pass all checks."""
    ref = _row(engine="python")
    ng = _row(engine="ngspice")
    deltas = compare_engine_metrics(ref, ng)
    assert all(delta.within_tol for delta in deltas)


def test_compare_engine_metrics_detects_sndr_drift() -> None:
    """A large SNDR delta should fail parity."""
    ref = _row(engine="python")
    ng = _row(engine="ngspice", sndr_db=55.0)
    deltas = compare_engine_metrics(ref, ng)
    sndr_delta = next(delta for delta in deltas if delta.metric == "sndr_db")
    assert not sndr_delta.within_tol


def test_format_metric_spread_table_lists_each_metric() -> None:
    """Spread table should include one row per condition and metric."""
    ref = _row(engine="python")
    ng = _row(engine="ngspice")
    rows = collect_metric_spread_rows({"default": {"python": ref, "ngspice": ng}})
    table = format_metric_spread_table(rows)
    assert "`default`" in table
    assert "`sndr_db`" in table
    assert "Spread %" in table
    assert "2.0" in table
    assert rows[0].spread_pct == 0.0


def test_format_metric_delta_table_lists_every_engine_metric() -> None:
    """Delta table should list each ngspice/Spectre metric vs Python."""
    from adc_model.engine_compare import collect_all_metric_deltas, format_metric_delta_table

    ref = _row(engine="python")
    ng = _row(engine="ngspice")
    sp = _row(engine="spectre", max_inl_lsb=4.374, sndr_db=59.09)
    by_label = {"default": {"python": ref, "ngspice": ng, "spectre": sp}}
    deltas = collect_all_metric_deltas(by_label)
    table = format_metric_delta_table(deltas)
    assert "`ngspice`" in table
    assert "`spectre`" in table
    assert "`max_inl_lsb`" in table
    assert len(deltas) == 12


def test_spectre_run_from_user_batch_within_two_percent() -> None:
    """Representative post-fix Spectre metrics should pass 2% spread checks."""
    ref = _row(engine="python")
    spectre = _row(
        engine="spectre",
        max_inl_lsb=4.374,
        sndr_db=59.09,
        sfdr_db=85.48,
        thd_db=78.77,
        enob_bits=9.52,
    )
    rows = collect_metric_spread_rows({"default": {"python": ref, "spectre": spectre}})
    assert all(row.ok for row in rows)
