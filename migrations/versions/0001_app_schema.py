"""schema app: users + landbank_items

Revision ID: 0001_app_schema
Revises:
Create Date: 2026-06-16
"""
from alembic import op

revision = "0001_app_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS app")

    op.execute(
        """
        CREATE TABLE app.users (
            id         bigserial PRIMARY KEY,
            email      text UNIQUE NOT NULL,
            senha_hash text NOT NULL,
            nome       text,
            ativo      boolean NOT NULL DEFAULT true,
            criado_em  timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TYPE app.estagio_lote AS ENUM
            ('triagem', 'analise', 'opcao', 'due_diligence', 'adquirido', 'descartado')
        """
    )

    # lote_id é referência LÓGICA a geo.lotes (sem FK de propósito): os lotes são
    # recarregados pelo loader (TRUNCATE), e uma FK arrastaria o landbank junto.
    # Chave durável futura = geo.lotes.inscricao (CODI_CART). TODO migrar p/ inscricao.
    op.execute(
        """
        CREATE TABLE app.landbank_items (
            id            bigserial PRIMARY KEY,
            user_id       bigint NOT NULL REFERENCES app.users(id) ON DELETE CASCADE,
            lote_id       bigint NOT NULL,
            estagio       app.estagio_lote NOT NULL DEFAULT 'triagem',
            notas         text,
            criado_em     timestamptz NOT NULL DEFAULT now(),
            atualizado_em timestamptz NOT NULL DEFAULT now(),
            UNIQUE (user_id, lote_id)
        )
        """
    )
    op.execute("CREATE INDEX idx_landbank_user ON app.landbank_items (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app.landbank_items")
    op.execute("DROP TYPE IF EXISTS app.estagio_lote")
    op.execute("DROP TABLE IF EXISTS app.users")
    op.execute("DROP SCHEMA IF EXISTS app CASCADE")
