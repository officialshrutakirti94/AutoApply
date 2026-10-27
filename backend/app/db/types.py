"""Column types that work on both Postgres and SQLite.

Production is Neon Postgres and uses JSONB and native arrays. The test suite runs
against SQLite so it needs no server; there the same columns degrade to JSON,
which stores the identical Python values. Only these columns are affected, and no
query in the codebase relies on Postgres array or JSONB operators, so behaviour is
the same on both.
"""

from __future__ import annotations

from sqlalchemy import JSON, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

JsonDict = JSONB().with_variant(JSON(), "sqlite")
StringList = ARRAY(Text()).with_variant(JSON(), "sqlite")
