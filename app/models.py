import os
import bcrypt
from typing import List, Optional
from datetime import datetime, timedelta
import pytz  # For handling time zones
from dotenv import load_dotenv

from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, CheckConstraint, Boolean, Numeric
from sqlalchemy.orm import relationship, backref, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import unittest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(120), nullable=False)
    email_hash = Column(String(120), unique=True, nullable=False) # Changed to store hashed email
    discord_id = Column(String(50), unique=True, nullable=True)  # Added for Discord integration
    characters = relationship('Character', back_populates='user', lazy='joined')
    is_admin = Column(Boolean, default=False)

    def set_password(self, password):
        password = password.encode('utf-8')
        salt = bcrypt.gensalt()
        self.password_hash = str(bcrypt.hashpw(password, salt),'utf-8')

    def check_password(self, password):
        password = bytes(password.encode('utf-8'))
        password_hash = bytes(str(self.password_hash), 'utf-8')
        return bcrypt.checkpw(password, password_hash) # added str

    def set_email_hash(self, email): # Added email hashing function
        self.email_hash = email

    def check_email_hash(self, email):
        return self.email_hash == email # added str

    def __repr__(self):
        return f'<User {self.username}>'

class Character(Base):
    __tablename__ = 'characters'
    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True, nullable=False) # Changed to store character name
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    last_login = Column(DateTime, nullable=True)
    world_id = Column(Integer, ForeignKey('worlds.id'), nullable=False)
    verification_id = Column(String(120), unique=True, nullable=True) # Added for character verification
    verified = Column(Boolean, default=False, nullable=False)  # Added verified field
    user = relationship('User', back_populates='characters')
    world = relationship('World', backref='characters')
    bids = relationship('Bid', back_populates='character')  # This line is related to the error.
    hunts = relationship('Hunt', back_populates='character')
    def __repr__(self):
        return f'<Character {self.name}>'

class World(Base):
    __tablename__ = 'worlds'
    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True, nullable=False)
    location = Column(String(255), nullable=True) # e.g., "North America", "Europe"

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
    world_id = Column(Integer, ForeignKey('worlds.id'), nullable=False)

    world = relationship('World', backref='spawns')
    hunts = relationship('Hunt', back_populates='spawn', lazy='joined')
    bids = relationship('Bid', back_populates='spawn', lazy='joined')
    __table_args__ = (
        UniqueConstraint('name', 'world_id', name='_spawn_name_world_uc'),
    )

    def __repr__(self):
        return f'<Spawn {self.name}>'

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
