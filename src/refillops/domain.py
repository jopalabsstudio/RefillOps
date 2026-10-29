"""Pure domain rules; no HTTP or persistence concerns."""
from datetime import datetime, timezone
from math import radians, sin, cos, asin, sqrt
from zoneinfo import ZoneInfo

TRANSITIONS = {
    'CREATED': {'ASSIGNED', 'CANCELLED'},
    'ASSIGNED': {'OUT_FOR_DELIVERY', 'CANCELLED'},
    'OUT_FOR_DELIVERY': {'COMPLETED', 'CANCELLED', 'DELIVERY_FAILED'},
    'DELIVERY_FAILED': {'ASSIGNED', 'CANCELLED'},
    'COMPLETED': set(), 'CANCELLED': set(),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def can_transition(source: str, target: str) -> bool:
    return target in TRANSITIONS.get(source, set())


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine great-circle distance, not road travel distance."""
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2)**2
    return 6371.0088 * 2 * asin(min(1, sqrt(a)))


def container_position(opening: int, movements: list[int]) -> int:
    return opening + sum(movements)


def charge_minor(delivered: int, unit_price_minor: int) -> int:
    if delivered <= 0 or unit_price_minor < 0:
        raise ValueError('Invalid price or delivery count')
    return delivered * unit_price_minor


def station_month(utc_iso: str, tz_name: str) -> str:
    dt = datetime.fromisoformat(utc_iso.replace('Z', '+00:00'))
    return dt.astimezone(ZoneInfo(tz_name)).strftime('%Y-%m')
