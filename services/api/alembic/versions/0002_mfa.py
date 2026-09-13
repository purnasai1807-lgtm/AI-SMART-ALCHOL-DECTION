"""Add user MFA state."""
from alembic import op
import sqlalchemy as sa

revision = "0002_mfa"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    if "mfa_secret_ciphertext" not in existing:
        op.add_column("users", sa.Column("mfa_secret_ciphertext", sa.String(length=512), nullable=True))
    if "mfa_enabled" not in existing:
        op.add_column("users", sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "mfa_enrolled_at" not in existing:
        op.add_column("users", sa.Column("mfa_enrolled_at", sa.DateTime(timezone=True), nullable=True))

def downgrade() -> None:
    op.drop_column("users", "mfa_enrolled_at")
    op.drop_column("users", "mfa_enabled")
    op.drop_column("users", "mfa_secret_ciphertext")
