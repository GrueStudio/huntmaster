import bcrypt
import hashlib
import enum

from datetime import datetime, UTC

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, CheckConstraint, Boolean, Numeric, event, Enum, Table
from sqlalchemy.orm import relationship, session
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func, select
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
proposal_votes = Table(
    'spawn_change_proposal_votes',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('spawn_change_proposal_id', Integer, ForeignKey('spawn_change_proposals.id'), primary_key=True),
    Column('vote_type', Enum(VoteType))
)

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

    sponsored_proposals = relationship(
        "SpawnProposal",
        secondary=proposal_sponsors,
        primaryjoin=lambda: User.id == proposal_sponsors.c.user_id, # Explicit primaryjoin
        secondaryjoin=lambda: SpawnProposal.id == proposal_sponsors.c.spawn_proposal_id, # Explicit secondaryjoin
        back_populates="sponsors"
    )
    spawn_change_proposals_voted = relationship(
        "SpawnChangeProposal",
        secondary=proposal_votes,
        primaryjoin=lambda: User.id == proposal_votes.c.user_id,
        secondaryjoin=lambda: SpawnChangeProposal.id == proposal_votes.c.spawn_change_proposal_id,
        back_populates="voters"
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
    spawns = relationship('Spawn', back_populates='world', lazy='joined')
    spawn_proposals = relationship('SpawnProposal', back_populates='world', lazy='joined')
    characters = relationship('Character', back_populates='world', lazy='joined')

    def __repr__(self):
        return f'<World {self.name}>'

class Spawn(Base):
    __tablename__ = 'spawns'
    id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False) # Made name non-unique
    description = Column(String(200), nullable=True)
    locking_period = Column(Integer, nullable=False) # Time in minutes before a winning bid starts
    claim_time_min = Column(Integer, nullable=False)
    claim_time_max = Column(Integer, nullable=False)
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

    new_locking_period = Column(Integer, nullable=False) # Time in minutes before a winning bid starts
    new_claim_time_min = Column(Integer, nullable=False)
    new_claim_time_max = Column(Integer, nullable=False)

    status = Column(Enum(ProposalStatus), default=ProposalStatus.PENDING)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    approved_at = Column(DateTime(timezone=True), nullable=True)

    # Link to the actual Spawn if the proposal is approved and spawn created
    spawn_id = Column(Integer, ForeignKey('spawns.id'), nullable=True)
    spawn = relationship('Spawn', foreign_keys=[spawn_id], back_populates='change_proposals') # Link back to the created Spawn

    voters = relationship(
        "User",
        secondary=proposal_votes,
        primaryjoin=lambda: SpawnChangeProposal.id == proposal_votes.c.spawn_change_proposal_id,
        secondaryjoin=lambda: User.id == proposal_votes.c.user_id,
        back_populates="spawn_change_proposals_voted"
    )

    __table_args__ = (
        CheckConstraint(
            '(start_time IS NULL AND end_time IS NULL) OR (start_time IS NOT NULL AND end_time IS NOT NULL AND end_time > start_time)',
            name='_spawn_change_proposal_time_constraint'
        ),
    )

    @hybrid_property
    def votes_for(self) -> int:
        """Calculates the total upvotes for this change proposal."""
        # This implementation queries the association table directly for the instance.
        # It's less efficient than a single query with the expression, but works for hybrid properties.
        # Ensure that self.id is available (i.e., object is persistent).
        if self.id is None:
            # If the object is not yet committed or not associated with a session,
            # we can't query, so return 0. This might happen for new, unsaved objects.
            return 0

        return (
            session.object_session(self).query(func.count(proposal_votes.c.user_id))
            .filter(
                proposal_votes.c.spawn_change_proposal_id == self.id,
                proposal_votes.c.vote_type == VoteType.UPVOTE
            )
            .scalar() or 0
        )
    @property
    def total_votes(self):
        return self.votes_for + self.votes_against

    @votes_for.expression
    def votes_for_ex(cls):
        return (
            select(func.count(proposal_votes.c.user_id))
            .where(proposal_votes.c.spawn_change_proposal_id == cls.id)
            .where(proposal_votes.c.vote_type == VoteType.UPVOTE)
            .label("total_upvotes")
        )

    @hybrid_property
    def votes_against(self) -> int:
        """Calculates the total downvotes for this change proposal."""
        if self.id is None or not session.object_session(self):
            return 0

        return (
            session.object_session(self).query(func.count(proposal_votes.c.user_id))
            .filter(
                proposal_votes.c.spawn_change_proposal_id == self.id,
                proposal_votes.c.vote_type == VoteType.DOWNVOTE
            )
            .scalar() or 0
        )

    @votes_against.expression
    def votes_against_ex(cls):
        return (
            select(func.count(proposal_votes.c.user_id))
            .where(proposal_votes.c.spawn_change_proposal_id == cls.id)
            .where(proposal_votes.c.vote_type == VoteType.DOWNVOTE)
            .label("total_downvotes")
        )

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
    character = relationship('Character')
    spawn = relationship('Spawn')
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
    character = relationship('Character', back_populates='hunts')
    spawn = relationship('Spawn', back_populates='hunts')
    bid = relationship('Bid')

    def __repr__(self):
        return f'<Hunt {self.id} - {self.character.name} on {self.spawn.name}>'
