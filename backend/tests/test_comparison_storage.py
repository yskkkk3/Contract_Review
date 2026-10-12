"""Regression tests for storing large contract-comparison results."""

from sqlalchemy import Text
from sqlalchemy.dialects import mysql, sqlite

from app.models.comparison import ComparisonTask


def test_diff_result_uses_longtext_on_mysql() -> None:
    column_type = ComparisonTask.__table__.c.diff_result.type

    assert isinstance(column_type.dialect_impl(mysql.dialect()), mysql.LONGTEXT)
    assert isinstance(column_type.dialect_impl(sqlite.dialect()), Text)
