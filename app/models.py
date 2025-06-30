import bcrypt
import hashlib
import enum
import math

from datetime import datetime, UTC, timedelta

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, CheckConstraint, Boolean, Numeric, event, Enum, Table, Interval
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func, select, and_
from sqlalchemy.ext.hybrid import hybrid_property

class ProposalStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"

class NotificationType(enum.Enum):
    PROPOSAL_STATUS = "proposal_status"
    RECOVERY_TOKEN_EXPIRY = "recovery_token_expiry"
    FAVOURITE_SPAWN_PROPOSAL = "favourite_spawn_proposal"
    GENERAL = "general"

class VoteType(enum.Enum):
    UPVOTE = "upvote"
    DOWNVOTE = "downvote"

Base = declarative_base()

proposal_sponsors = Table(
    'spawn_proposal_sponsors',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('spawn_proposal_id', Integer, ForeignKey('spawn_proposals.id'), primary_key=True)
)

class Vote(Base):
    __tablename__ = 'change_votes'
    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    proposal_id = Column(Integer, ForeignKey('spawn_change_proposals.id'), primary_key=True)
    vote_type = Column(Enum(VoteType))

    user = relationship('User', back_populates='votes', lazy='joined')
    proposal = relationship("SpawnChangeProposal", back_populates='votes', lazy='joined')



# New association table for User and Spawn (Favorites)
user_spawn_favorites = Table(
    'user_spawn_favorites',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('spawn_id', Integer, ForeignKey('spawns.id'), primary_key=True),
)

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(120), nullable=False)
    discord_id = Column(String(50), unique=True, nullable=True)  # Added for Discord integration
    characters = relationship('Character', back_populates='user', lazy='joined')
    recovery_tokens = relationship('RecoveryToken', back_populates='user', lazy='joined')
    is_admin = Column(Boolean, default=False)
    notifications = relationship('Notification', back_populates='user') # Added back_populates
    votes = relationship('Vote', back_populates='user', lazy='joined')

    sponsored_proposals = relationship(
        "SpawnProposal",
        secondary=proposal_sponsors,
        primaryjoin=lambda: User.id == proposal_sponsors.c.user_id, # Explicit primaryjoin
        secondaryjoin=lambda: SpawnProposal.id == proposal_sponsors.c.spawn_proposal_id, # Explicit secondaryjoin
        back_populates="sponsors"
    )

    favourite_spawns = relationship(
        "Spawn",
        secondary=user_spawn_favorites,
        primaryjoin=lambda: User.id == user_spawn_favorites.c.user_id,
        secondaryjoin=lambda: Spawn.id == user_spawn_favorites.c.spawn_id,
        back_populates="favourited_by"
    )

    def set_password(self, password):
        password = password.encode('utf-8')
        salt = bcrypt.gensalt()
        self.password_hash = str(bcrypt.hashpw(password, salt),'utf-8')

    def check_password(self, password):
        password = bytes(password.encode('utf-8'))
        password_hash = bytes(str(self.password_hash), 'utf-8')
        return bcrypt.checkpw(password, password_hash) # added str

    def __repr__(self):
        return f'<User {self.username}>'

class RecoveryToken(Base):
    __tablename__ = 'recovery_tokens'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    token = Column(String(255), unique=True, nullable=False)
    expiration_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    used = Column(Boolean, default=False, nullable=False)

    user = relationship('User', back_populates='recovery_tokens')

    def __repr__(self):
        return f'<RecoveryToken {self.token[:10]}... for User {self.user_id}>'

class Character(Base):
    __tablename__ = 'characters'
    id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False) # This is now the Tibia.com name, globally unique
    level = Column(Integer, nullable=False) # Added back, nullable
    vocation = Column(String(50), nullable=False) # Added back, nullable
    user_id = Column(Integer, ForeignKey('users.id')) # Changed to nullable for disown
    last_login = Column(DateTime, nullable=True)
    world_id = Column(Integer, ForeignKey('worlds.id'), nullable=False)
    validation_hash = Column(String(120), unique=True, nullable=True) # NULL means validated, non-NULL means pending validation

    user = relationship('User', back_populates='characters')
    world = relationship('World', back_populates='characters')
    bids = relationship('Bid', back_populates='character')
    hunts = relationship('Hunt', back_populates='character')

    __table_args__ = (
        UniqueConstraint('name', 'user_id', name='_name_user_id_uc'),
    )

    # Hybrid property for 'validated' status
    @hybrid_property
    def validated(self):
        """Returns True if the character is validated (validation_hash is NULL)."""
        return self.validation_hash is None

    @validated.expression
    def validated_sql(cls):
        """SQL expression for the validated property."""
        return cls.validation_hash.is_(None)

    # Removed UniqueConstraint('user_id', 'name') as name is now globally unique (Tibia.com name)

    def __repr__(self):
        return f'<Character {self.name}>'

# SQLAlchemy event listener to generate validation_hash before insert
@event.listens_for(Character, 'before_insert')
def receive_before_insert(mapper, connection, target):
    """
    Generate validation_hash if not already set and user_id is present.
    The hash is MD5(username + character_name).
    """
    # Only generate if user_id is set and validation_hash is not explicitly provided
    if target.user_id is not None and target.validation_hash is None:
        # Ensure the user object is loaded to get the username.
        # This might trigger a flush if the user is new, but it's necessary
        # to get the username for hashing.
        user = target.user
        if user: # Check if user relationship is loaded and not None
            combined_string = f"{user.username}{target.name}"
            target.validation_hash = hashlib.md5(combined_string.encode()).hexdigest()

class World(Base):
    __tablename__ = 'worlds'
    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True, nullable=False)
    location = Column(String(255), nullable=True) # e.g., "North America", "Europe"

    inactive_threshold = Column(Interval, nullable=False, default=timedelta(days=30))
    engagement_threshold = Column(Numeric, nullable=False, default=0.5)
    favourability_approval = Column(Numeric, nullable=False, default=0.6)
    favourability_rejection = Column(Numeric, nullable=False, default=0.3)
    sponsorship_flat = Column(Integer, nullable=False, default=5)
    sposorship_fraction = Column(Numeric, nullable=False, default=0.1)

    spawns = relationship('Spawn', back_populates='world', lazy='joined')
    spawn_proposals = relationship('SpawnProposal', back_populates='world', lazy='joined')
    characters = relationship('Character', back_populates='world', lazy='joined')

    def get_active_users(self, db):
        """
        Returns a list of User objects who are considered active in this world.
        An active user has at least one character in this world with a bid or hunt
        activity within the world's inactive_threshold (in days).
        This method requires a database session.
        """
        # Calculate the threshold date in Python for the query
        threshold_date = datetime.now(UTC) - self.inactive_threshold

        # Query to find the latest activity date (Bid or Hunt) for each user
        # across their characters in this specific world.
        latest_user_activity_in_world = (
            db.query(
                User.id.label('user_id'),
                func.max(func.greatest(
                    Bid.hunt_window_start,
                    Hunt.start_time
                )).label('overall_last_activity')
            )
            .join(Character, Character.user_id == User.id)
            .outerjoin(Bid, Bid.character_id == Character.id)
            .outerjoin(Hunt, Hunt.character_id == Character.id)
            .filter(Character.world_id == self.id) # Filter characters to this specific world instance
            .group_by(User.id)
        ).subquery()

        # Query for User objects based on their latest activity date in this world
        active_users_query = (
            db.query(User)
            .join(latest_user_activity_in_world, latest_user_activity_in_world.c.user_id == User.id)
            .filter(
                and_(
                    latest_user_activity_in_world.c.overall_last_activity.isnot(None), # Must have activity
                    latest_user_activity_in_world.c.overall_last_activity >= threshold_date # Activity is recent enough
                )
            )
            .distinct() # Ensure distinct User objects
        )

        return active_users_query.all()


    def __repr__(self):
        return f'<World {self.name}>'

class Spawn(Base):
    __tablename__ = 'spawns'
    id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False) # Made name non-unique
    description = Column(String(200), nullable=True)

    locking_period = Column(Interval, nullable=False, default=timedelta(minutes=15)) # Time in minutes before a winning bid starts
    claim_time_min = Column(Interval, nullable=False, default=timedelta(minutes=15))
    claim_time_max = Column(Interval, nullable=False, default=timedelta(hours=3, minutes=15))
    deprioratize_time = Column(Interval, nullable=True)

    proposal_id = Column(Integer, ForeignKey('spawn_proposals.id'))
    world_id = Column(Integer, ForeignKey('worlds.id'), nullable=False)

    world = relationship('World', back_populates='spawns')
    proposal_origin = relationship('SpawnProposal', back_populates='spawn')
    change_proposals = relationship('SpawnChangeProposal', back_populates='spawn')
    hunts = relationship('Hunt', back_populates='spawn', lazy='joined')
    bids = relationship('Bid', back_populates='spawn', lazy='joined')

    # Updated: Using association table for favourited by users
    favourited_by = relationship(
        "User",
        secondary=user_spawn_favorites,
        primaryjoin=lambda: Spawn.id == user_spawn_favorites.c.spawn_id,
        secondaryjoin=lambda: User.id == user_spawn_favorites.c.user_id,
        back_populates="favourite_spawns"
    )
    __table_args__ = (
        UniqueConstraint('name', 'world_id', name='_spawn_name_world_uc'),
    )

    def get_active_users(self, db):
        """
        Returns a list of User objects who are considered active for this specific spawn.
        An active user has at least one character with activity on this spawn
        within the spawn's associated world's inactive_threshold days.
        This method requires a database session.
        """
        if not self.world: # Ensure world is loaded for inactive_threshold
            db.refresh(self, attribute_names=['world']) # Eager load if not already

        threshold_date = datetime.now(UTC) - self.world.inactive_threshold

        # Query to find the latest activity date (Bid or Hunt) for each user
        # across their characters on this specific spawn.
        latest_user_activity_on_spawn = (
            db.query(
                User.id.label('user_id'),
                func.max(func.greatest(
                    Bid.hunt_window_start,
                    Hunt.start_time
                )).label('overall_last_activity')
            )
            .join(Character, Character.user_id == User.id)
            .outerjoin(Bid, and_(Bid.character_id == Character.id, Bid.spawn_id == self.id)) # Filter bids to this spawn
            .outerjoin(Hunt, and_(Hunt.character_id == Character.id, Hunt.spawn_id == self.id)) # Filter hunts to this spawn
            .filter(Character.world_id == self.world_id) # Ensure character is in the same world as spawn
            .group_by(User.id)
        ).subquery()

        # Query for User objects based on their latest activity date on this spawn
        active_users_query = (
            db.query(User)
            .join(latest_user_activity_on_spawn, latest_user_activity_on_spawn.c.user_id == User.id)
            .filter(
                and_(
                    latest_user_activity_on_spawn.c.overall_last_activity.isnot(None), # Must have activity
                    latest_user_activity_on_spawn.c.overall_last_activity >= threshold_date # Activity is recent enough
                )
            )
            .distinct()
        )
        return active_users_query.all()

    def __repr__(self):
        return f'<Spawn {self.name}>'


class SpawnProposal(Base):
    __tablename__ = 'spawn_proposals'
    id = Column(Integer, primary_key=True)

    # Fields for the proposed spawn (these will be copied to Spawn if approved)
    name = Column(String(100), unique=True, index=True) # Name of the proposed spawn
    description = Column(String(255), nullable=True)
    world_id = Column(Integer, ForeignKey('worlds.id'), nullable=False)
    world = relationship("World",back_populates="spawn_proposals") # Relationship to World

    min_level = Column(Integer, nullable=True)
    max_level = Column(Integer, nullable=True)

    locking_period = Column(Interval, nullable=False, default=timedelta(minutes=15)) # Time in minutes before a winning bid starts
    claim_time_min = Column(Interval, nullable=False, default=timedelta(minutes=15))
    claim_time_max = Column(Interval, nullable=False, default=timedelta(hours=3, minutes=15))
    deprioratize_time = Column(Interval, nullable=True)

    status = Column(Enum(ProposalStatus), default=ProposalStatus.PENDING)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    approved_at = Column(DateTime(timezone=True), nullable=True)

    spawn = relationship('Spawn', back_populates="proposal_origin") # Link back to the created Spawn

    sponsors = relationship(
        "User",
        secondary=proposal_sponsors,
        primaryjoin=lambda: SpawnProposal.id == proposal_sponsors.c.spawn_proposal_id, # Explicit primaryjoin
        secondaryjoin=lambda: User.id == proposal_sponsors.c.user_id, # Explicit secondaryjoin
        back_populates="sponsored_proposals"
    )

    @hybrid_property
    def num_sponsors(self) -> int:
        """Calculates the number of unique sponsors for this proposal."""
        return len(self.sponsors)

    @num_sponsors.expression
    def num_sponsors_unique(cls):
        """Provides the SQL expression for querying the number of unique sponsors."""
        return (
            select(func.count(func.distinct(proposal_sponsors.c.user_id)))
            .where(proposal_sponsors.c.spawn_proposal_id == cls.id)
            .label("num_unique_sponsors")
        )

    def __repr__(self) -> str:
        return f"<SpawnProposal(id={self.id}, name='{self.name}', status='{self.status.value}')>"


class SpawnChangeProposal(Base):
    __tablename__ = 'spawn_change_proposals'
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(String(255), nullable=True)

    start_time = Column(DateTime(timezone=True), nullable=True)
    end_time = Column(DateTime(timezone=True), nullable=True)

    locking_period = Column(Interval, nullable=False, default=timedelta(minutes=15)) # Time in minutes before a winning bid starts
    claim_time_min = Column(Interval, nullable=False, default=timedelta(minutes=15))
    claim_time_max = Column(Interval, nullable=False, default=timedelta(hours=3, minutes=15))
    deprioratize_time = Column(Interval, nullable=True)

    status = Column(Enum(ProposalStatus), default=ProposalStatus.PENDING)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    approved_at = Column(DateTime(timezone=True), nullable=True)

    # Link to the actual Spawn if the proposal is approved and spawn created
    spawn_id = Column(Integer, ForeignKey('spawns.id'), nullable=True)
    spawn = relationship('Spawn', foreign_keys=[spawn_id], back_populates='change_proposals') # Link back to the created Spawn
    votes = relationship('Vote', back_populates='proposal', lazy='joined')

    __table_args__ = (
        CheckConstraint(
            '(start_time IS NULL AND end_time IS NULL) OR (start_time IS NOT NULL AND end_time IS NOT NULL AND end_time > start_time)',
            name='_spawn_change_proposal_time_constraint'
        ),
    )

    @property
    def total_votes(self):
        return len(self.votes)

    @property
    def favourability(self):
        return math.floor(self.votes_for / max(self.total_votes, 1) * 100)

    def get_engagement(self, session):
        return math.floor(self.total_votes / max(len(self.spawn.get_active_users(session)),1))

    @hybrid_property
    def votes_for(self) -> int:
        """Calculates the total upvotes for this change proposal."""
        return sum([1 for vote in self.votes if vote.vote_type == VoteType.UPVOTE])

    @votes_for.expression
    def votes_for_ex(cls):
        return func.count(Vote.id).filter((Vote.proposal_id == cls.id) & (Vote.vote_type == 'UPVOTE'))

    @hybrid_property
    def votes_against(self) -> int:
        """Calculates the total downvotes for this change proposal."""
        return sum([1 for vote in self.votes if vote.vote_type == VoteType.DOWNVOTE])

    @votes_against.expression
    def votes_against_ex(cls):
        return func.count(Vote.id).filter((Vote.proposal_id == cls.id) & (Vote.vote_type == 'DOWNVOTE'))

    def __repr__(self) -> str:
        return f"<SpawnChangeProposal(id={self.id}, name='{self.name}', status='{self.status.value}')>"

class Notification(Base):
    __tablename__ = 'notifications'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    user = relationship("User", back_populates="notifications")

    message = Column(String(500))
    notification_type = Column(Enum(NotificationType))
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Optional: link to a specific entity if the notification is about it
    # For example, if it's about a proposal, link to proposal ID
    related_entity_id = Column(Integer, nullable=True)
    related_entity_type = Column(String(50), nullable=True) # e.g., 'spawn_change_proposal'

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, user_id={self.user_id}, type='{self.notification_type.value}', is_read={self.is_read})>"

class Points(Base):
    __tablename__ = 'points'
    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey('characters.id'), nullable=False)
    spawn_id = Column(Integer, ForeignKey('spawns.id'), nullable=False)
    points = Column(Numeric, nullable=False) # Changed to Numeric for fractional values
    character = relationship('Character', lazy='joined')
    spawn = relationship('Spawn', lazy='joined')
    __table_args__ = (
        UniqueConstraint('character_id', 'spawn_id', name='_character_spawn_points_uc'),
    )
    def __repr__(self):
        return f'<Points {self.points:.2f} for Character {self.character_id} on Spawn {self.spawn_id}>'

class Bid(Base):
    __tablename__ = 'bids'
    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey('characters.id'), nullable=False)
    spawn_id = Column(Integer, ForeignKey('spawns.id'), nullable=False)
    bid_points = Column(Integer, nullable=False)
    hunt_window_start = Column(DateTime, nullable=False) # Renamed from start_time
    hunt_window_end = Column(DateTime, nullable=False) # Renamed from end_time
    claim_time = Column(Integer, nullable=False)
    scheduled_start = Column(DateTime, nullable=True) # Added scheduled_start
    is_locked = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint('character_id', 'spawn_id', 'hunt_window_start', name='_character_spawn_start_uc'),
        CheckConstraint('hunt_window_end > hunt_window_start', name='_end_after_start'),
        # Add a check constraint to ensure scheduled_start is within hunt_window
        CheckConstraint('scheduled_start >= hunt_window_start AND scheduled_start <= hunt_window_end', name='_scheduled_start_within_window'),
    )
    character = relationship('Character', back_populates='bids')
    spawn = relationship('Spawn', back_populates='bids')

    def __repr__(self):
        return f'<Bid {self.id} - {self.character.name} on {self.spawn.name}>'

class Hunt(Base):
    __tablename__ = 'hunts'
    id = Column(Integer, primary_key=True)
    character_id = Column(Integer, ForeignKey('characters.id'), nullable=False)
    spawn_id = Column(Integer, ForeignKey('spawns.id'), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    points_paid = Column(Integer, default=0)
    bid_id = Column(Integer, ForeignKey('bids.id'), nullable=True)
    character = relationship('Character', back_populates='hunts', lazy='joined')
    spawn = relationship('Spawn', back_populates='hunts', lazy='joined')
    bid = relationship('Bid')

    def __repr__(self):
        return f'<Hunt {self.id} - {self.character.name} on {self.spawn.name}>'
