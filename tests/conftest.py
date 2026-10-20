import os

import pytest

from app.config import get_settings
from app.db import connect, init_db

# Point every test at the test database before any test reads the settings.
# load_dotenv() never overwrites a variable that is already set, so .env can't undo this.
os.environ["POSTGRES_DB"] = "docassistant_test"


@pytest.fixture
def conn():
    conninfo = get_settings().db_conninfo

    # Safety lock: the next lines delete every table. Never do that to real data.
    if "dbname=docassistant_test" not in conninfo:
        pytest.fail("Tests only run on the docassistant_test database.")

    # Start every test with brand-new, empty tables.
    connection = connect(conninfo)
    connection.execute("DROP TABLE IF EXISTS chunks, documents, workspaces")
    init_db(connection)

    yield connection  # the test runs here

    connection.close()