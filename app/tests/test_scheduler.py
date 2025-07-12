# /app/tests/test_scheduler.py

import unittest
from datetime import datetime, timedelta, UTC
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, User, World, Spawn, Bid, Hunt
from app.scheduler import Scheduler

class TestScheduler(unittest.TestCase):
    def setUp(self):
        # Set up in-memory SQLite database
        self.engine = create_engine("sqlite:///:memory:")
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.SessionLocal()

        # Create test world
        self.world = World(
            name="TestWorld",
            inactive_threshold=timedelta(days=30),
            engagement_threshold=0.5,
            favourability_approval=0.6,
            favourability_rejection=0.3,
            sponsorship_flat=5,
            sposorship_fraction=0.1
        )
        self.db.add(self.world)
        self.db.commit()

        # Create test spawn with deprioratize_time (note the spelling to match your models)
        self.spawn = Spawn(
            name="TestSpawn",
            world=self.world,
            locking_period=timedelta(minutes=15),
            claim_time_min=timedelta(minutes=15),
            claim_time_max=timedelta(hours=3, minutes=15),
            deprioratize_time=timedelta(hours=2)  # 2 hours deprioritization threshold
        )
        self.db.add(self.spawn)
        self.db.commit()

        # Create 20 test users with bids
        self.now = datetime.now(UTC)
        self.users = []
        for i in range(1, 21):
            user = User(username=f"user{i}")
            user.set_password(f"password{i}")
            self.db.add(user)
            self.users.append(user)
        self.db.commit()

        # Create bids for each user in a 6-hour window
        self.bids = []
        for i, user in enumerate(self.users):
            # Vary hunt window times and points
            start_offset = timedelta(hours=i * 0.3)  # Stagger start times
            duration = timedelta(hours=1 + (i % 3))  # Vary duration 1-3 hours

            bid = Bid(
                user_id=user.id,
                spawn_id=self.spawn.id,
                bid_points=50 + (i * 10),  # Vary points from 50 to 240
                hunt_window_start=self.now + start_offset,
                hunt_window_end=self.now + start_offset + timedelta(hours=6),
                claim_time=duration
            )
            self.db.add(bid)
            self.bids.append(bid)
        self.db.commit()

        # Create hunts for some users to exceed deprioratize_time
        self.hunted_users = self.users[:2]  # First 2 users will have excessive hunts
        for user in self.hunted_users:
            # Create hunts totaling more than 2 hours (deprioratize_time)
            hunt1 = Hunt(
                user_id=user.id,
                spawn_id=self.spawn.id,
                start_time=self.now - timedelta(hours=3),
                end_time=self.now - timedelta(hours=2),
                points_paid=50
            )
            hunt2 = Hunt(
                user_id=user.id,
                spawn_id=self.spawn.id,
                start_time=self.now - timedelta(hours=1),
                end_time=self.now - timedelta(minutes=30),
                points_paid=50
            )
            self.db.add_all([hunt1, hunt2])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def test_scheduler_with_deprioratization(self):
        scheduler = Scheduler(self.db)
        time_slots = scheduler.schedule_bids_for_spawn(self.spawn.id)

        # Verify we got some time slots
        self.assertGreater(len(time_slots), 0)

        # Verify no overlapping time slots
        for i in range(len(time_slots) - 1):
            self.assertLessEqual(
                time_slots[i].end_time,
                time_slots[i+1].start_time,
                "Time slots should not overlap"
            )

        # Verify deprioratized users got fewer slots
        deprioritized_users = {slot.user_id for slot in time_slots
                              if slot.user_id in [u.id for u in self.hunted_users]}
        self.assertLessEqual(
            len(deprioritized_users),
            len(self.hunted_users) // 2,  # Expect at most half got slots
            "Too many deprioritized users got time slots"
        )

        # Verify highest value bids got slots first
        bid_values = {
            bid.user_id: scheduler.evaluate_bid_value(bid, "points_per_hour", self.spawn.deprioratize_time)[0]
            for bid in self.bids
        }
        time_slot_values = [bid_values[slot.user_id] for slot in time_slots]
        self.assertEqual(
            time_slot_values,
            sorted(time_slot_values, reverse=True),
            "Time slots should be ordered by bid value"
        )

    def test_scheduler_with_empty_spawn(self):
        # Test with spawn that has no bids
        empty_spawn = Spawn(
            name="EmptySpawn",
            world=self.world,
            locking_period=timedelta(minutes=15),
            claim_time_min=timedelta(minutes=15),
            claim_time_max=timedelta(hours=3, minutes=15)
        )
        self.db.add(empty_spawn)
        self.db.commit()

        scheduler = Scheduler(self.db)
        time_slots = scheduler.schedule_bids_for_spawn(empty_spawn.id)
        self.assertEqual(len(time_slots), 0)

if __name__ == '__main__':
    unittest.main()
