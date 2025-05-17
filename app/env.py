from alembic import context
from sqlalchemy import create_engine
from app.models import Base
import re
import os
# Get database connection details from environment variables
db_user = os.environ.get("DB_USER")
db_password = os.environ.get("DB_PASSWORD")
db_host = os.environ.get("DB_HOST")
db_port = os.environ.get("DB_PORT", "5432")  # Default port if not set
db_name = os.environ.get("DB_NAME", "mydb")  # Default database name

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

url_tokens = {
    "DB_USER": os.getenv("DB_USER", ""),
    "DB_PASS": os.getenv("DB_PASSWORD", ""),
    "DB_PORT": os.getenv("DB_PORT", "5432"),
    "DB_HOST": os.getenv("DB_HOST", ""),
    "DB_NAME": os.getenv("DB_NAME", "")
}

url = config.get_main_option("sqlalchemy.url")

url = re.sub(r"\${(.+?)}", lambda m: url_tokens[m.group(1)], url))
config.set_main_option("sqlalchemy.url", url)
target_metadata = Base.metadata

def run_migrations_online():
    engine = create_engine(url)

    with engine.connect() as connection:
        context.configure(
                    connection=connection,
                    target_metadata=target_metadata
                    )

        with context.begin_transaction():
            context.run_migrations()
