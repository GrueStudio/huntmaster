"""Add Recovery Token Model, Remove Email Hash from User

Revision ID: 42646cafeeba
Revises: 0d55182ac7c4
Create Date: 2025-05-21 18:29:49.621947

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '42646cafeeba'
down_revision: Union[str, None] = '0d55182ac7c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('recovery_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token', sa.String(length=255), nullable=False),
    sa.Column('expiration_time', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('used', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token')
    )
    op.drop_constraint('users_email_hash_key', 'users', type_='unique')
    op.drop_column('users', 'email_hash')
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('users', sa.Column('email_hash', sa.VARCHAR(length=120), autoincrement=False, nullable=False))
    op.create_unique_constraint('users_email_hash_key', 'users', ['email_hash'])
    op.drop_table('recovery_tokens')
    # ### end Alembic commands ###
