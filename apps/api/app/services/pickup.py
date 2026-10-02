from collections import Counter
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Order, OrderStatus, PickupDay

# Orders in these states no longer hold a pickup slot; everything else counts
# against the day's slot_capacity.
_RELEASED_STATUSES = (OrderStatus.CANCELLED, OrderStatus.EXPIRED)


def cafe_tz() -> ZoneInfo:
    """The café's local timezone. A PickupDay's date/start/end are wall-clock values
    in this zone; they only become UTC instants once combined here."""
    return ZoneInfo(get_settings().pickup_timezone)


def _as_utc(value: datetime) -> datetime:
    """Normalise a datetime to aware-UTC. SQLite hands tz-aware columns back naive,
    and clients may send naive pickup_at values; slot arithmetic assumes UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _day_window(day: PickupDay) -> tuple[datetime, datetime]:
    # Interpret the admin's 16:00-19:00 as café wall-clock time, then convert to
    # UTC so slot instants are unambiguous (16:00 Stockholm = 14:00Z in summer).
    tz = cafe_tz()
    return (
        datetime.combine(day.date, day.start_time, tzinfo=tz).astimezone(UTC),
        datetime.combine(day.date, day.end_time, tzinfo=tz).astimezone(UTC),
    )


def available_days(db: Session) -> list[PickupDay]:
    """Available pickup days from today (café time) onward, soonest first."""
    today = datetime.now(cafe_tz()).date()
    return list(
        db.scalars(
            select(PickupDay)
            .where(PickupDay.date >= today, PickupDay.is_available.is_(True))
            .order_by(PickupDay.date)
        )
    )


def upcoming_days(db: Session) -> list[PickupDay]:
    """All pickup days from today onward, including unavailable ones (admin view)."""
    today = datetime.now(cafe_tz()).date()
    return list(
        db.scalars(select(PickupDay).where(PickupDay.date >= today).order_by(PickupDay.date))
    )


def slots_for_day(db: Session, day: PickupDay) -> list[dict]:
    """All slots on the day's start..end grid with their remaining capacity."""
    day_start, day_end = _day_window(day)
    counts: Counter[datetime] = Counter()
    taken = db.scalars(
        select(Order.pickup_at).where(
            Order.pickup_at >= day_start,
            Order.pickup_at < day_end,
            Order.status.not_in(_RELEASED_STATUSES),
        )
    )
    for value in taken:
        counts[_as_utc(value)] += 1
    slots = []
    candidate = day_start
    while candidate < day_end:
        slots.append({"time": candidate, "remaining": day.slot_capacity - counts[candidate]})
        candidate += timedelta(minutes=day.slot_minutes)
    return slots


def validate_and_lock_slot(db: Session, pickup_at: datetime) -> datetime:
    """Validate a requested pickup slot and reserve the right to fill it.

    Locks the PickupDay row FOR UPDATE *before* counting orders in the slot: the
    legacy app checked capacity outside the write lock, so two concurrent checkouts
    could both see one seat left and both take it. Holding the day's row lock
    serialises competing checkouts for that date until the caller commits.

    Returns the normalised (aware-UTC) pickup time to persist on the order.
    """
    pickup_at = _as_utc(pickup_at).replace(second=0, microsecond=0)
    # The PickupDay row is keyed by the café-local date, which can differ from the
    # UTC date near midnight, so convert before looking up the day.
    cafe_date = pickup_at.astimezone(cafe_tz()).date()
    day = db.scalar(select(PickupDay).where(PickupDay.date == cafe_date).with_for_update())
    if day is None or not day.is_available:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Pickup is not available on that date"
        )
    if pickup_at <= datetime.now(UTC):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pickup time is in the past")
    day_start, day_end = _day_window(day)
    offset = pickup_at - day_start
    if (
        pickup_at < day_start
        or pickup_at >= day_end
        or offset % timedelta(minutes=day.slot_minutes)
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Pickup time is not an offered slot"
        )
    taken = (
        db.scalar(
            select(func.count(Order.id)).where(
                Order.pickup_at == pickup_at,
                Order.status.not_in(_RELEASED_STATUSES),
            )
        )
        or 0
    )
    if taken >= day.slot_capacity:
        raise HTTPException(status.HTTP_409_CONFLICT, "That pickup slot is full")
    return pickup_at
