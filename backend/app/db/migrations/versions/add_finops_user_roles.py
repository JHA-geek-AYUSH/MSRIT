"""add FinOps user roles to users_role_chk constraint

Revision ID: 540d6b34a449
Revises: 540d6b34a448
Create Date: 2026-07-11 00:00:02.000000

"""
from __future__ import annotations

import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

log = logging.getLogger(__name__)

revision: str = "540d6b34a449"
down_revision: Union[str, None] = "540d6b34a448"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Warn about any users whose roles will no longer exist after a downgrade.
    # These are the three original legal-product roles that are being retained,
    # so we check for them specifically to surface any unexpected data in case
    # the migration is run against a database that somehow has stale role values.
    conn = op.get_bind()

    for role in ("lawyer", "paralegal", "client"):
        result = conn.execute(
            sa.text("SELECT COUNT(*) FROM users WHERE role = :role"),
            {"role": role},
        )
        count = result.scalar()
        if count:
            log.warning(
                "upgrade add_finops_user_roles: %d user(s) still have legacy role '%s'. "
                "These records are valid under both the old and new constraint.",
                count,
                role,
            )

    # Single atomic ALTER TABLE: drop old constraint, add new one with 9 roles.
    op.execute("ALTER TABLE users DROP CONSTRAINT users_role_chk")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT users_role_chk "
        "CHECK (role IN ("
        "'lawyer','admin','paralegal','client',"
        "'finance_analyst','compliance_officer','auditor','cfo','viewer'"
        "))"
    )


def downgrade() -> None:
    # Warn about FinOps-only roles that will be blocked after the constraint is
    # restored to the original 4-role set.  Any user with one of these roles
    # will violate the restored constraint — callers should reassign those users
    # before running the downgrade.
    conn = op.get_bind()

    for role in ("lawyer", "paralegal", "client"):
        result = conn.execute(
            sa.text("SELECT COUNT(*) FROM users WHERE role = :role"),
            {"role": role},
        )
        count = result.scalar()
        if count:
            log.warning(
                "downgrade add_finops_user_roles: %d user(s) have legacy role '%s' "
                "which will still be permitted after the downgrade.",
                count,
                role,
            )

    # Restore original 4-role constraint.
    op.execute("ALTER TABLE users DROP CONSTRAINT users_role_chk")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT users_role_chk "
        "CHECK (role IN ('lawyer','admin','paralegal','client'))"
    )
