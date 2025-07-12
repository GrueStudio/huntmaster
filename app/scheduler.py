# /app/scheduler.py

from typing import Optional
from datetime import datetime, timedelta, UTC
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from app.models import Bid, Hunt, Spawn, TimeSlot

# Constants
BERLIN_TZ = ZoneInfo("Europe/Berlin")
TIBIAN_DAY_START_HOUR = 10  # 10 AM Berlin time

class Scheduler:
    def __init__(self, db: Session):
        self.db = db

    def get_tibian_day_start(self, now: datetime) -> datetime:
        """
        Gets the start of the current Tibian day (10am Berlin time).
        """
        berlin_time = now.astimezone(BERLIN_TZ)
        if berlin_time.hour < TIBIAN_DAY_START_HOUR:
            # Before 10am Berlin time, use previous day
            tibian_day_start = datetime(
                berlin_time.year,
                berlin_time.month,
                berlin_time.day - 1,
                TIBIAN_DAY_START_HOUR,
                0,
                0,
                tzinfo=BERLIN_TZ
            )
        else:
            tibian_day_start = datetime(
                berlin_time.year,
                berlin_time.month,
                berlin_time.day,
                TIBIAN_DAY_START_HOUR,
                0,
                0,
                tzinfo=BERLIN_TZ
            )
        return tibian_day_start.astimezone(UTC)

    def get_user_hunt_duration(
        self,
        user_id: int,
        spawn_id: int,
        since: Optional[datetime] = None
    ) -> timedelta:
        """
        Calculates total hunt duration for a user on a spawn since given time.
        """
        since = since or self.get_tibian_day_start(datetime.now(UTC))

        hunts = self.db.query(Hunt).filter(
            Hunt.user_id == user_id,
            Hunt.spawn_id == spawn_id,
            Hunt.start_time >= since
        ).all()

        return sum(
            (hunt.end_time - hunt.start_time for hunt in hunts),
            timedelta()
        )

    def evaluate_bid_value(
        self,
        bid: Bid,
        heuristic: str = "points_per_hour",
        deprioritize_time: Optional[timedelta] = None
    ) -> tuple[float, bool]:
        """
        Enhanced bid evaluation with deprioritization and EDF support.
        """
        duration_hours = (bid.hunt_window_end - bid.hunt_window_start).total_seconds() / 3600

        if heuristic == "absolute_points":
            base_value = float(bid.bid_points)
        elif heuristic == "points_per_hour_squared":
            base_value = bid.bid_points / (duration_hours ** 2)
        elif heuristic == "early_bird":
            hours_until_start = (bid.hunt_window_start - datetime.now(UTC)).total_seconds() / 3600
            base_value = bid.bid_points / (1 + hours_until_start)
        else:  # Default "points_per_hour"
            base_value = bid.bid_points / duration_hours

        is_deprioritized = False
        if deprioritize_time and deprioritize_time.total_seconds() > 0:
            user_hunt_time = self.get_user_hunt_duration(
                bid.user_id,
                bid.spawn_id,
                self.get_tibian_day_start(datetime.now(UTC))
            )
            if user_hunt_time >= deprioritize_time:
                is_deprioritized = True
                base_value *= 0.1

        return (base_value, is_deprioritized)

    def schedule_bids_for_spawn(
        self,
        spawn_id: int,
        heuristic: str = "points_per_hour",
        now: datetime = None
    ) -> list[TimeSlot]:
        """
        Creates optimal non-overlapping time slots from bids for a specific spawn.
        """
        now = now or datetime.now(UTC)
        spawn = self.db.query(Spawn).filter(Spawn.id == spawn_id).first()
        if not spawn:
            return []

        active_bids = self.db.query(Bid).filter(
            Bid.spawn_id == spawn_id,
            Bid.deadline > now
        ).all()

        if not active_bids:
            return []

        evaluated_bids = []
        for bid in active_bids:
            value, is_deprioritized = self.evaluate_bid_value(
                bid,
                heuristic,
                spawn.deprioratize_time
            )
            evaluated_bids.append({
                'bid': bid,
                'value': value,
                'is_deprioritized': is_deprioritized,
                'deadline': bid.deadline
            })

        evaluated_bids.sort(key=lambda x: (
            x['is_deprioritized'],
            x['deadline'],
            -x['value']
        ))

        time_slots = []
        used_windows = []

        for bid_data in evaluated_bids:
            bid = bid_data['bid']
            proposed_start = bid.hunt_window_start
            proposed_end = proposed_start + bid.claim_time

            for slot_start, slot_end in sorted(used_windows):
                if proposed_start < slot_end and proposed_end > slot_start:
                    proposed_start = max(proposed_start, slot_end)
                    proposed_end = proposed_start + bid.claim_time

            if (proposed_start >= bid.hunt_window_start and
                proposed_end <= bid.hunt_window_end and
                proposed_start <= bid.deadline):

                time_slots.append(TimeSlot(
                    user_id=bid.user_id,
                    spawn_id=bid.spawn_id,
                    start_time=proposed_start,
                    end_time=proposed_end,
                    points_paid=bid.bid_points,
                    bid_id=bid.id
                ))
                used_windows.append((proposed_start, proposed_end))

        return time_slots

    def update_spawn_schedule(self, spawn_id: int) -> bool:
        """
        Full scheduling process for a spawn.
        """
        try:
            now = datetime.now(UTC)

            # Clear existing future slots
            self.db.query(TimeSlot).filter(
                TimeSlot.spawn_id == spawn_id,
                TimeSlot.start_time > now
            ).delete()

            # Generate new schedule
            time_slots = self.schedule_bids_for_spawn(spawn_id)

            # Add to database
            for slot in time_slots:
                self.db.add(slot)

            self.db.commit()
            return True

        except Exception as e:
            self.db.rollback()
            raise e
