import unittest
import os
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from sqlalchemy import event

# Import your models
from app.models import User, Character, World, Spawn, Points, Bid, Hunt, Base  # Adjust the import path if needed

# Use an in-memory SQLite database for testing.  This is faster and doesn't require a separate database server.
TEST_DB_URL = "sqlite:///:memory:"

# Create a SQLAlchemy engine for the test database
test_engine = create_engine(TEST_DB_URL)

# Create a session class for interacting with the test database
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Function to get a database session for testing
def get_test_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

# Set up the database before running the tests.  This ensures that the tables
# are created and that the database is in a clean state before each test run.
@event.listens_for(test_engine, "connect")
def connect(dbapi_connection, connection_record):
    """
    Listen for the connect event and set the isolation level to SERIALIZABLE.
    This is important for testing, especially with SQLite, to ensure that
    tests are run in a consistent and isolated manner.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")  # Use WAL mode for better concurrency
    cursor.execute("PRAGMA synchronous=NORMAL") # NORMAL is a good balance for testing
    cursor.close()

class TestModels(unittest.TestCase):
    """
    This class contains unit tests for the SQLAlchemy models defined in models.py.
    It inherits from unittest.TestCase, which provides the basic framework for
    writing and running tests.
    """

    def setUp(self):
        """
        Set up the test environment before each test method is executed.
        This includes creating the database tables and creating a new
        database session.
        """
        # Create all tables in the test database.
        Base.metadata.create_all(bind=test_engine)
        # Get a new database session for this test.
        self.db_generator = get_test_db()
        self.db = next(self.db_generator)

    def tearDown(self):
        """
        Clean up the test environment after each test method is executed.
        This includes rolling back the database session and dropping all tables
        in the test database.  This ensures that each test is independent
        and doesn't affect the results of other tests.
        """
        self.db.rollback()  # Rollback the session to undo any changes
        Base.metadata.drop_all(bind=test_engine)  # Drop all tables
        self.db.close()

    def test_user_model(self):
        """
        Test the User model.  This includes testing the creation of a new user,
        setting and checking the password, and the string representation of the user.
        """
        # Create a new user.
        user = User(username='testuser')
        user.set_email_hash('email@mail.gg')
        user.set_password('password')
        self.db.add(user)
        self.db.commit()

        # Retrieve the user from the database.
        retrieved_user = self.db.query(User).filter_by(username='testuser').first()
        self.assertEqual(retrieved_user.username, 'testuser')
        self.assertTrue(retrieved_user.check_password('password'))
        self.assertFalse(retrieved_user.check_password('wrongpassword'))
        self.assertEqual(repr(retrieved_user), '<User testuser>')

    def test_character_model(self):
        """
        Test the Character model. This includes testing character creation,
        relationships with User and World, and the string representation.
        """
        # Create a user and a world for the character.
        user = User(username='testuser', email_hash='test@example.com')
        user.set_password('password')
        world = World(name='TestWorld')
        self.db.add_all([user, world])
        self.db.commit()

        # Create a character.
        character = Character(name='TestCharacter', user=user, world=world)
        self.db.add(character)
        self.db.commit()

        # Retrieve the character and check its attributes.
        retrieved_character = self.db.query(Character).filter_by(name='TestCharacter').first()
        self.assertEqual(retrieved_character.name, 'TestCharacter')
        self.assertEqual(retrieved_character.user.username, 'testuser')
        self.assertEqual(retrieved_character.world.name, 'TestWorld')
        self.assertEqual(repr(retrieved_character), '<Character TestCharacter>')

    def test_world_model(self):
        """
        Test the World model.  This includes testing the creation of a world
        and its string representation.
        """
        # Create a world.
        world = World(name='TestWorld', location='TestLocation')
        self.db.add(world)
        self.db.commit()

        # Retrieve the world and check its attributes.
        retrieved_world = self.db.query(World).filter_by(name='TestWorld').first()
        self.assertEqual(retrieved_world.name, 'TestWorld')
        self.assertEqual(retrieved_world.location, 'TestLocation')
        self.assertEqual(repr(retrieved_world), '<World TestWorld>')

    def test_spawn_model(self):
        """
        Test the Spawn model.  This includes testing the creation of a spawn,
        its relationship with World, and its string representation.
        """
        # Create a world for the spawn.
        world = World(name='TestWorld')
        self.db.add(world)
        self.db.commit()

        # Create a spawn.
        spawn = Spawn(name='TestSpawn', world=world, locking_period=60, claim_time_min=10, claim_time_max=20)
        self.db.add(spawn)
        self.db.commit()

        # Retrieve the spawn and check its attributes.
        retrieved_spawn = self.db.query(Spawn).filter_by(name='TestSpawn').first()
        self.assertEqual(retrieved_spawn.name, 'TestSpawn')
        self.assertEqual(retrieved_spawn.world.name, 'TestWorld')
        self.assertEqual(retrieved_spawn.locking_period, 60)
        self.assertEqual(retrieved_spawn.claim_time_min, 10)
        self.assertEqual(retrieved_spawn.claim_time_max, 20)
        self.assertEqual(repr(retrieved_spawn), '<Spawn TestSpawn>')

    def test_points_model(self):
        """
        Test the Points model. This includes testing the creation of points
        for a character on a spawn, and the string representation.
        """
        # Create a user, world, character, and spawn.
        user = User(username='testuser', email_hash='test@example.com')
        user.set_password('password')
        world = World(name='TestWorld')
        self.db.add_all([user, world])
        self.db.commit()
        character = Character(name='TestCharacter', user=user, world=world)
        spawn = Spawn(name='TestSpawn', world=world, locking_period=60, claim_time_min=10, claim_time_max=20)
        self.db.add_all([character, spawn])
        self.db.commit()

        # Create points for the character on the spawn.
        points = Points(character=character, spawn=spawn, points=100)
        self.db.add(points)
        self.db.commit()

        # Retrieve the points and check its attributes.
        retrieved_points = self.db.query(Points).first()
        self.assertEqual(retrieved_points.points, 100)
        self.assertEqual(retrieved_points.character.name, 'TestCharacter')
        self.assertEqual(retrieved_points.spawn.name, 'TestSpawn')
        self.assertEqual(repr(retrieved_points), '<Points 100.00 for Character 1 on Spawn 1>')

    def test_bid_model(self):
        """
        Test the Bid model. This includes testing bid creation, relationships,
        and constraints.
        """
        # Create a user, world, character, and spawn.
        user = User(username='testuser', email_hash='test@example.com')
        user.set_password('password')
        world = World(name='TestWorld')
        self.db.add_all([user, world])
        self.db.commit()
        character = Character(name='TestCharacter', user=user, world=world)
        spawn = Spawn(name='TestSpawn', world=world, locking_period=60, claim_time_min=10, claim_time_max=20)
        self.db.add_all([character, spawn])
        self.db.commit()

        # Create a bid.
        now = datetime.utcnow()
        hunt_start = now + timedelta(hours=1)
        hunt_end = now + timedelta(hours=2)
        bid = Bid(character=character, spawn=spawn, bid_points=50, hunt_window_start=hunt_start, hunt_window_end=hunt_end, claim_time=15, scheduled_start=hunt_start)
        self.db.add(bid)
        self.db.commit()

        # Retrieve the bid and check its attributes.
        retrieved_bid = self.db.query(Bid).first()
        self.assertEqual(retrieved_bid.bid_points, 50)
        self.assertEqual(retrieved_bid.character.name, 'TestCharacter')
        self.assertEqual(retrieved_bid.spawn.name, 'TestSpawn')
        self.assertEqual(retrieved_bid.hunt_window_start, hunt_start)
        self.assertEqual(retrieved_bid.hunt_window_end, hunt_end)
        self.assertEqual(retrieved_bid.claim_time, 15)
        self.assertEqual(repr(retrieved_bid), '<Bid 1 - TestCharacter on TestSpawn>')

        # Test the UniqueConstraint.
        with self.assertRaises(IntegrityError):
            duplicate_bid = Bid(character=character, spawn=spawn, bid_points=60, hunt_window_start=hunt_start, hunt_window_end=hunt_end, claim_time=15, scheduled_start=hunt_start)
            self.db.add(duplicate_bid)
            self.db.commit()
        self.db.rollback()

        # Test the CheckConstraint for hunt_window_end > hunt_window_start
        with self.assertRaises(IntegrityError):
            invalid_bid = Bid(character=character, spawn=spawn, bid_points=60, hunt_window_start=hunt_end, hunt_window_end=hunt_start, claim_time=15, scheduled_start=hunt_start)
            self.db.add(invalid_bid)
            self.db.commit()
        self.db.rollback()

        # Test the CheckConstraint for scheduled_start within hunt_window
        with self.assertRaises(IntegrityError):
            invalid_bid = Bid(character=character, spawn=spawn, bid_points=60, hunt_window_start=hunt_start, hunt_window_end=hunt_end, claim_time=15, scheduled_start=hunt_end + timedelta(seconds=1))
            self.db.add(invalid_bid)
            self.db.commit()

    def test_hunt_model(self):
        """
        Test the Hunt model.  This includes testing hunt creation and relationships.
        """
        # Create a user, world, character, and spawn.
        user = User(username='testuser', email_hash='test@example.com')
        user.set_password('password')
        world = World(name='TestWorld')
        self.db.add_all([user, world])
        self.db.commit()
        character = Character(name='TestCharacter', user=user, world=world)
        spawn = Spawn(name='TestSpawn', world=world, locking_period=60, claim_time_min=10, claim_time_max=20)
        self.db.add_all([character, spawn])
        self.db.commit()

        #create a bid
        now = datetime.utcnow()
        hunt_start = now + timedelta(hours=1)
        hunt_end = now + timedelta(hours=2)
        bid = Bid(character=character, spawn=spawn, bid_points=50, hunt_window_start=hunt_start, hunt_window_end=hunt_end, claim_time=15, scheduled_start=hunt_start)
        self.db.add(bid)
        self.db.commit()

        # Create a hunt.
        hunt_start_time = datetime.utcnow()
        hunt_end_time = hunt_start_time + timedelta(hours=1)
        hunt = Hunt(character=character, spawn=spawn, start_time=hunt_start_time, end_time=hunt_end_time, bid=bid)
        self.db.add(hunt)
        self.db.commit()

        # Retrieve the hunt and check its attributes.
        retrieved_hunt = self.db.query(Hunt).first()
        self.assertEqual(retrieved_hunt.character.name, 'TestCharacter')
        self.assertEqual(retrieved_hunt.spawn.name, 'TestSpawn')
        self.assertEqual(retrieved_hunt.start_time, hunt_start_time)
        self.assertEqual(retrieved_hunt.end_time, hunt_end_time)
        self.assertEqual(repr(retrieved_hunt), '<Hunt 1 - TestCharacter on TestSpawn>')

if __name__ == '__main__':
    unittest.main()
