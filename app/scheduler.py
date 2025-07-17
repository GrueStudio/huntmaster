# /app/scheduler.py

from typing import Optional
from datetime import datetime, timedelta, UTC
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session, joinedload
from models import Bid, Hunt, Spawn, TimeSlot, BidStatus, PointLedger
import logging

logger = logging.getLogger(__name__)

# Constants
BERLIN_TZ = ZoneInfo("Europe/Berlin")
TIBIAN_DAY_START_HOUR = 10  # 10 AM Berlin time

class SmartScheduler:
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

    def lock_timeslots_to_hunts(self, spawn_id: int, now: datetime) -> list[Hunt]:
        """
        Converts TimeSlots to Hunts when they're within the locking period.
        Returns the list of newly created Hunts.
        """
        now = now or datetime.now(UTC)
        if now.tzinfo == None:
            now.replace(tzinfo=UTC)
        spawn = self.db.query(Spawn).filter(Spawn.id == spawn_id).first()
        if not spawn:
            return []

        # Debug logging
        logger.info(f"Checking spawn {spawn_id} with locking period {spawn.locking_period}")
        lock_threshold = now + spawn.locking_period
        logger.info(f"Current time: {now}, Lock threshold: {lock_threshold}")

        timeslots_to_lock = self.db.query(TimeSlot).options(joinedload(TimeSlot.bid)).filter(
            TimeSlot.spawn_id == spawn_id,
            TimeSlot.start_time <= lock_threshold,
            TimeSlot.start_time > now  # Only future timeslots
        ).all()

        logger.info(f"Found {len(timeslots_to_lock)} timeslots to lock")

        locked_hunts = []
        for timeslot in timeslots_to_lock:
            # Create Hunt from TimeSlot
            hunt = Hunt(
                user_id=timeslot.user_id,
                spawn_id=timeslot.spawn_id,
                start_time=timeslot.start_time,
                end_time=timeslot.end_time,
                points_paid=timeslot.points_paid,
                bid_id=timeslot.bid_id
            )
            self.db.add(hunt)
            locked_hunts.append(hunt)

            timeslot.bid.status = BidStatus.SUCCESSFUL

            self.db.add(timeslot.bid)
            # Remove the locked timeslot
            self.db.delete(timeslot)

        return locked_hunts

    def get_earliest_future_hunt(self, spawn_id: int, now: datetime = None) -> Optional[datetime]:
        """
        Returns the start time of the earliest future Hunt for a spawn.
        Used to determine safe scheduling window.
        """
        now = now or datetime.now(UTC)
        if now.tzinfo == None:
            now.replace(tzinfo=UTC)

        earliest_hunt = self.db.query(Hunt).filter(
            Hunt.spawn_id == spawn_id,
            Hunt.start_time > now
        ).order_by(Hunt.start_time).first()

        return earliest_hunt.start_time if earliest_hunt else None

    def schedule_bids_for_spawn(
        self,
        spawn_id: int,
        heuristic: str = "points_per_hour",
        now: datetime = None
    ) -> list[TimeSlot]:
        """
        Creates optimal non-overlapping time slots from bids for a specific spawn.
        Takes into account existing future Hunts to avoid conflicts.
        """
        now = now or datetime.now(UTC)
        if now.tzinfo == None:
            now.replace(tzinfo=UTC)
        spawn = self.db.query(Spawn).filter(Spawn.id == spawn_id).first()
        if not spawn:
            return []

        active_bids = self.db.query(Bid).filter(
            Bid.spawn_id == spawn_id,
            Bid.deadline > now,
            Bid.status == BidStatus.PENDING
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

        # Get existing future hunts to avoid conflicts
        future_hunts = self.db.query(Hunt).filter(
            Hunt.spawn_id == spawn_id,
            Hunt.start_time > now
        ).all()

        # Build list of used windows (including future hunts)
        used_windows = [(hunt.start_time, hunt.end_time) for hunt in future_hunts]

        time_slots = []

        for bid_data in evaluated_bids:
            bid = bid_data['bid']
            proposed_start = bid.hunt_window_start
            proposed_end = proposed_start + bid.claim_time

            # Check conflicts with existing windows (hunts + other scheduled slots)
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

    def update_spawn_schedule(self, spawn_id: int) -> dict:
        """
        Full scheduling process for a spawn with locking mechanism.
        Returns summary of actions taken.
        """
        try:
            now = datetime.now(UTC)

            failed_bids = self.mark_expired_bids(spawn_id, now)

            # Step 1: Lock timeslots that are within locking period
            locked_hunts = self.lock_timeslots_to_hunts(spawn_id, now)

            # Step 2: Clear remaining future timeslots (non-locked ones)
            deleted_timeslots = self.db.query(TimeSlot).filter(
                TimeSlot.spawn_id == spawn_id,
                TimeSlot.start_time > now
            ).delete()

            # Step 3: Generate new schedule
            time_slots = self.schedule_bids_for_spawn(spawn_id, now=now)

            # Step 4: Add new timeslots to database
            for slot in time_slots:
                self.db.add(slot)

            self.db.commit()

            return {
                'success': True,
                'locked_hunts': len(locked_hunts),
                'deleted_timeslots': deleted_timeslots,
                'new_timeslots': len(time_slots),
                'earliest_future_hunt': self.get_earliest_future_hunt(spawn_id, now),
                'failed_bids': failed_bids
            }

        except Exception as e:
            self.db.rollback()
            raise e

    def should_run_full_schedule(self) -> bool:
        """Determine if we need to run full scheduling"""
        now = datetime.now(UTC)

        # Check if any timeslots are close to locking period
        spawns_needing_locking = self.db.query(Spawn).join(TimeSlot).filter(
            TimeSlot.start_time <= now + Spawn.locking_period + timedelta(minutes=1),
            TimeSlot.start_time > now
        ).distinct().all()

        return len(spawns_needing_locking) > 0

    def get_spawns_needing_update(self) -> list[int]:
        """Get list of spawn IDs that need scheduling updates"""
        now = datetime.now(UTC)

        # Spawns with timeslots approaching locking period
        spawns_for_locking = self.db.query(Spawn.id).join(TimeSlot).filter(
            TimeSlot.start_time <= now + Spawn.locking_period + timedelta(minutes=1),
            TimeSlot.start_time > now
        ).distinct().all()

        # Spawns with recent bid changes (you'd need to track this)
        # For now, just return all spawns with active bids
        spawns_with_bids = self.db.query(Spawn.id).join(Bid).filter(
            Bid.deadline > now,
            Bid.status == BidStatus.PENDING
        ).distinct().all()

        return list(set([s.id for s in spawns_for_locking + spawns_with_bids]))

    def smart_update(self) -> dict:
        """Smart scheduling that only updates what's needed"""
        spawns_to_update = self.get_spawns_needing_update()

        if not spawns_to_update:
            logger.info("No spawns need updating")
            return {"message": "No spawns need updating", "spawns_updated": 0}

        results = {}
        total_updated = 0

        for spawn_id in spawns_to_update:
            try:
                result = self.update_spawn_schedule(spawn_id)
                results[spawn_id] = result
                total_updated += 1
                logger.info(f"Updated spawn {spawn_id}: {result}")
            except Exception as e:
                logger.error(f"Failed to update spawn {spawn_id}: {e}")
                results[spawn_id] = {"error": str(e)}

        return {
            "message": f"Updated {total_updated} spawns",
            "spawns_updated": total_updated,
            "results": results
        }

    def update_all_spawns_schedule(self) -> dict:
        """
        Updates schedule for all spawns with active bids.
        Returns summary of actions taken across all spawns.
        """
        try:
            now = datetime.now(UTC)

            payout_results = self.process_completed_hunts()

            # Get all spawns with active bids
            spawns_with_bids = self.db.query(Spawn).join(Bid).filter(
                Bid.deadline > now,
                Bid.status == BidStatus.PENDING
            ).distinct().all()

            total_summary = {
                'success': True,
                'spawns_updated': 0,
                'total_locked_hunts': 0,
                'total_deleted_timeslots': 0,
                'total_new_timeslots': 0,
                'spawn_details': {},
                'payout_results': payout_results
            }

            for spawn in spawns_with_bids:
                spawn_summary = self.update_spawn_schedule(spawn.id)
                total_summary['spawns_updated'] += 1
                total_summary['total_locked_hunts'] += spawn_summary['locked_hunts']
                total_summary['total_deleted_timeslots'] += spawn_summary['deleted_timeslots']
                total_summary['total_new_timeslots'] += spawn_summary['new_timeslots']
                total_summary['spawn_details'][spawn.id] = spawn_summary

            return total_summary

        except Exception as e:
            self.db.rollback()
            raise e

    def get_spawn_schedule_status(self, spawn_id: int, now: datetime = None) -> dict:
        """
        Returns current scheduling status for a spawn.
        Useful for debugging and monitoring.
        """
        now = now or datetime.now(UTC)
        if now.tzinfo == None:
            now.replace(tzinfo=UTC)
        spawn = self.db.query(Spawn).filter(Spawn.id == spawn_id).first()
        if not spawn:
            return {'error': 'Spawn not found'}

        # Get current timeslots
        timeslots = self.db.query(TimeSlot).filter(
            TimeSlot.spawn_id == spawn_id,
            TimeSlot.start_time > now
        ).order_by(TimeSlot.start_time).all()

        # Get future hunts
        hunts = self.db.query(Hunt).filter(
            Hunt.spawn_id == spawn_id,
            Hunt.start_time > now
        ).order_by(Hunt.start_time).all()

        # Get active bids
        active_bids = self.db.query(Bid).filter(
            Bid.spawn_id == spawn_id,
            Bid.deadline > now
        ).all()

        # Calculate locking threshold
        lock_threshold = now + spawn.locking_period

        return {
            'spawn_id': spawn_id,
            'spawn_name': spawn.name,
            'locking_period': spawn.locking_period,
            'lock_threshold': lock_threshold,
            'current_time': now,
            'timeslots': {
                'total': len(timeslots),
                'within_locking_period': len([ts for ts in timeslots if ts.start_time <= lock_threshold]),
                'details': [(ts.start_time, ts.end_time, ts.user_id) for ts in timeslots]
            },
            'hunts': {
                'total': len(hunts),
                'details': [(h.start_time, h.end_time, h.user_id) for h in hunts]
            },
            'active_bids': len(active_bids)
        }

    def mark_expired_bids(self, spawn_id: int, now: datetime = None) -> int:
        """Mark bids past deadline as FAILED and return count of affected bids"""
        now = now or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)

        result = self.db.query(Bid)\
            .filter(
                Bid.spawn_id == spawn_id,
                Bid.deadline <= now,
                Bid.status == BidStatus.PENDING
            )\
            .update({"status": BidStatus.FAILED})

        self.db.commit()
        logger.info(f"Marked {result} bids as FAILED for spawn {spawn_id}")
        return result


    def spawn_needs_immediate_update(self, spawn_id: int) -> bool:
        """
        Check if a spawn needs immediate scheduling update.
        Used to determine if we should trigger scheduling after bid changes.
        """
        now = datetime.now(UTC)
        spawn = self.db.query(Spawn).filter(Spawn.id == spawn_id).first()
        if not spawn:
            return False

        # Check if any timeslots are close to locking period
        lock_threshold = now + spawn.locking_period + timedelta(minutes=1)

        timeslots_near_lock = self.db.query(TimeSlot).filter(
            TimeSlot.spawn_id == spawn_id,
            TimeSlot.start_time <= lock_threshold,
            TimeSlot.start_time > now
        ).count()

        return timeslots_near_lock > 0

    def process_completed_hunts(self) -> dict:
        """
        Find completed hunts and process payouts.
        Returns summary of processed hunts.
        """
        now = datetime.now(UTC)
        completed_hunts = self.db.query(Hunt).filter(
            Hunt.end_time <= now,
            Hunt.points_paid > 0,
            ~Hunt.ledger_entries.any()  # Only process hunts without existing payouts
        ).all()

        results = {}

        for hunt in completed_hunts:
            try:
                result = hunt.execute_payouts(self.db)
                results[hunt.id] = {
                    'spawn_id': hunt.spawn_id,
                    'user_id': hunt.user_id,
                    'payouts_issued': len(result.get('user_payouts', {})),
                    'total_points_distributed': sum(result.get('user_payouts', {}).values())
                }
            except Exception as e:
                logger.error(f"Failed to process payouts for hunt {hunt.id}: {e}")
                results[hunt.id] = {'error': str(e)}

        return {
            'total_processed': len(completed_hunts),
            'results': results
        }
