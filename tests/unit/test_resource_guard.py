from resource_guard.resource_guard import (
    ResourceSnapshot,
    ResourceThresholds,
    assess_resources,
)


def snapshot(**overrides):
    data = {
        "available_ram_mb": 800,
        "total_ram_mb": 2000,
        "swap_used_mb": 100,
        "swap_total_mb": 2000,
        "disk_used_percent": 70.0,
        "load_1m": 0.2,
        "cpu_count": 2,
        "gateway_status": "active",
        "daily_cost_total_usd": 1.0,
        "daily_cost_limit_usd": 2.0,
    }
    data.update(overrides)
    return ResourceSnapshot(**data)


def test_allows_safe_targeted_operation():
    decision = assess_resources(snapshot(), operation="targeted_tests")

    assert decision.allowed is True
    assert decision.blocked_reasons == []


def test_blocks_low_ram():
    decision = assess_resources(snapshot(available_ram_mb=100), operation="story")

    assert decision.allowed is False
    assert any("available_ram_mb" in reason for reason in decision.blocked_reasons)


def test_blocks_high_disk():
    decision = assess_resources(snapshot(disk_used_percent=90.0), operation="story")

    assert decision.allowed is False
    assert any("disk_used_percent" in reason for reason in decision.blocked_reasons)


def test_blocks_high_load_per_cpu():
    decision = assess_resources(snapshot(load_1m=4.0, cpu_count=2), operation="story")

    assert decision.allowed is False
    assert any("load_1m" in reason for reason in decision.blocked_reasons)


def test_blocks_gateway_down_for_non_diagnostics():
    decision = assess_resources(snapshot(gateway_status="failed"), operation="story")

    assert decision.allowed is False
    assert any("hermes-gateway" in reason for reason in decision.blocked_reasons)


def test_allows_gateway_down_for_diagnostics():
    decision = assess_resources(snapshot(gateway_status="failed"), operation="diagnostics")

    assert decision.allowed is True


def test_blocks_cost_guarded_reviewer_call():
    decision = assess_resources(
        snapshot(daily_cost_total_usd=2.16, daily_cost_limit_usd=2.0),
        operation="reviewer_call",
    )

    assert decision.allowed is False
    assert any("daily_cost_total_usd" in reason for reason in decision.blocked_reasons)


def test_does_not_block_targeted_tests_on_cost_guard():
    decision = assess_resources(
        snapshot(daily_cost_total_usd=2.16, daily_cost_limit_usd=2.0),
        operation="targeted_tests",
    )

    assert decision.allowed is True


def test_warns_on_high_swap_usage():
    decision = assess_resources(
        snapshot(swap_used_mb=1000, swap_total_mb=2000),
        operation="targeted_tests",
    )

    assert decision.allowed is True
    assert any("swap_used_mb" in warning for warning in decision.warnings)


def test_thresholds_are_configurable():
    decision = assess_resources(
        snapshot(available_ram_mb=250),
        operation="story",
        thresholds=ResourceThresholds(min_available_ram_mb=200),
    )

    assert decision.allowed is True
