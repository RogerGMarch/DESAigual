import duckdb

from desfibrilator.schema import TABLES, create_schema, table_counts


def test_create_schema_is_idempotent():
    connection = duckdb.connect(":memory:")
    create_schema(connection)
    create_schema(connection)

    assert set(TABLES) == {row[0] for row in connection.sql("SHOW TABLES").fetchall()}
    assert table_counts(connection) == dict.fromkeys(TABLES, 0)
