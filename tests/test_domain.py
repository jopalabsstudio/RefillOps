import pytest
from refillops.domain import charge_minor, can_transition, container_position, distance_km, station_month


def test_location_is_not_a_container():
    assert container_position(2, [3, -2]) == 3
    assert charge_minor(3, 3000) == 9000


def test_distance_is_straight_line():
    assert distance_km(14.65, 121.05, 14.65, 121.05) == pytest.approx(0)
    assert distance_km(14.65, 121.05, 14.66, 121.05) == pytest.approx(1.11, abs=.02)


def test_state_machine_no_completion_after_cancellation():
    assert can_transition('CREATED', 'ASSIGNED')
    assert can_transition('OUT_FOR_DELIVERY', 'COMPLETED')
    assert not can_transition('CANCELLED', 'COMPLETED')
    assert not can_transition('COMPLETED', 'OUT_FOR_DELIVERY')
    assert can_transition('DELIVERY_FAILED', 'ASSIGNED')


def test_month_uses_station_timezone():
    assert station_month('2026-09-30T17:00:00+00:00', 'Asia/Manila') == '2026-10'
