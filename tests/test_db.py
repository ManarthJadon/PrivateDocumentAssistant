import pytest

from app.db import AlreadyExists, create_workspace, get_workspace, init_db, list_workspaces


# --- creating the tables ---

def test_init_db_twice_is_safe(conn):
    # The fixture already ran init_db once; a second run must not fail.
    # (The app runs it on every start, so this happens all the time.)
    init_db(conn)


# --- workspaces ---

def test_create_and_list_workspaces(conn):
    home_id = create_workspace(conn, "Home")
    create_workspace(conn, "College")

    names = [workspace["name"] for workspace in list_workspaces(conn)]
    assert names == ["College", "Home"]  # sorted by name, not by creation order
    assert get_workspace(conn, home_id)["name"] == "Home"


def test_duplicate_name_raises(conn):
    create_workspace(conn, "College")
    with pytest.raises(AlreadyExists, match="A workspace called College already exists."):
        create_workspace(conn, "College")


def test_name_differing_only_in_case_is_duplicate(conn):
    create_workspace(conn, "College")
    with pytest.raises(AlreadyExists):
        create_workspace(conn, "college")


def test_get_missing_workspace_returns_none(conn):
    assert get_workspace(conn, 999) is None