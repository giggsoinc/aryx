"""Connection URLs must survive passwords with URL-special characters.

Regression: a password containing '@' was spliced raw into
``user:pass@host``, so the driver tried to resolve the part after '@' as the
host.
"""
from __future__ import annotations

import pytest
from sqlalchemy.engine import make_url

from aryx.store.datasource_store import build_url, open_url

TRICKY = ["s3cr@t", "a:b", "x/y", "h#sh", "q?uery", "100%", "@:/#?% all"]


@pytest.mark.parametrize("password", TRICKY)
def test_password_round_trips_through_url(password: str) -> None:
    url = make_url(open_url("postgres", {
        "host": "db.example.com", "port": "5432",
        "database": "example_db", "user": "example_user"}, password))

    assert url.password == password
    assert url.host == "db.example.com"
    assert url.port == 5432
    assert url.username == "example_user"
    assert url.database == "example_db"
    assert url.drivername == "postgresql+psycopg"


def test_no_user_means_no_credentials() -> None:
    url = make_url(build_url("postgres", host="db", database="d", password="secret"))
    assert url.username is None and url.password is None


def test_port_optional_and_validated() -> None:
    assert make_url(build_url("mysql", host="db", user="u", password="p")).port is None
    with pytest.raises(ValueError, match="port must be a number"):
        build_url("postgres", host="db", port="54x2", user="u", password="p")


def test_fields_are_trimmed() -> None:
    url = make_url(build_url("postgres", host=" db ", database=" example_db ",
                             user=" u ", password="p"))
    assert (url.host, url.database, url.username) == ("db", "example_db", "u")


def test_unsupported_kind() -> None:
    with pytest.raises(ValueError, match="unsupported datasource kind"):
        build_url("mongodb", host="db")


def test_sqlite_path_kept() -> None:
    assert build_url("sqlite", database="/tmp/x.db") == "sqlite:////tmp/x.db"
