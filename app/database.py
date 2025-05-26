"""
Filename: database.py
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typing import Generator

import os

# This is better for security (passwords) and deployment.
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT")
DB_NAME = os.environ.get("DB_NAME")

SQLALCHEMY_DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Check if the database URL is set.  If not, raise an exception.
if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set.  Please set it before running this script.")


# Create the SQLAlchemy engine.  This is the entry point for interacting with the database.
# echo=True will log all SQL statements to the console, which can be helpful for debugging.
engine = create_engine(SQLALCHEMY_DATABASE_URL, echo=False) #Set echo to false for production


# Create a SessionLocal class.  This class will be used to create database sessions.
# A session is a connection to the database, and it's used to perform operations
# like querying, adding, and updating data.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Dependency to get a database session.
# This function will create a new session, yield it to the caller, and then close it.
# This ensures that the session is properly closed after it's used.
def get_db() -> Generator: # Changed the return type to Generator
    """
    Get a database session.  This is a dependency that can be used in FastAPI
    route handlers.  It ensures that the database session is properly closed
    after it's used.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

if __name__ == "__main__":
    # This block of code will only be executed if this file is run directly (e.g.,
    # with `python database.py`).  It's a good place to put code that tests
    # the database connection.
    print("Testing database connection...")
    try:
        # Try to get a session.  If this succeeds, the connection is working.
        db = next(get_db()) # Get the first value from the generator
        print("Database connection successful!")
    except Exception as e:
        # If there's an exception, print the error message.
        print(f"Error connecting to database: {e}")
    finally:
        #  get_db() already closes, so nothing to do here
        print("Testing complete.")
