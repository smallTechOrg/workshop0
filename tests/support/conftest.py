"""tests/support needs no database: the fake issuer is pure HTTP.

The root conftest's autouse fixtures migrate and truncate the PostgreSQL test database for
every test. Overriding them here (same names, closer scope) keeps this self-test independent
of TEST_DATABASE_URL and stops it racing other suites on the shared test database.
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def _schema():
    yield


@pytest.fixture(autouse=True)
def _isolated_env():
    yield
