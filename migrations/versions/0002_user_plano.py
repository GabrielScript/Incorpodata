"""users.plano: tier de assinatura (free/pro/enterprise) para gate de features

Revision ID: 0002_user_plano
Revises: 0001_app_schema
Create Date: 2026-06-27
"""
from alembic import op

revision = "0002_user_plano"
down_revision = "0001_app_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # text + CHECK (não enum): tier é lista curta e estável; evita o atrito de ALTER TYPE.
    # Default 'free' → contas existentes caem no tier gratuito sem backfill.
    op.execute("ALTER TABLE app.users ADD COLUMN plano text NOT NULL DEFAULT 'free'")
    op.execute(
        "ALTER TABLE app.users ADD CONSTRAINT users_plano_chk "
        "CHECK (plano IN ('free', 'pro', 'enterprise'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE app.users DROP CONSTRAINT IF EXISTS users_plano_chk")
    op.execute("ALTER TABLE app.users DROP COLUMN IF EXISTS plano")
