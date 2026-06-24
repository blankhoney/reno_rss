import pytest


def test_create_admin_returns_one_time_recovery_code(capsys):
    from app.db.auth_store import MemoryAuthStore
    from app.seed import create_admin, print_seed_result

    result = create_admin(MemoryAuthStore(), display_name="Root")
    print_seed_result(result)

    output = capsys.readouterr()
    recovery_lines = [line for line in output.out.splitlines() if line.startswith("recovery_code=")]
    assert result.created is True
    assert result.user is not None
    assert result.user.role == "admin"
    assert len(recovery_lines) == 1
    assert recovery_lines[0].removeprefix("recovery_code=")
    assert "recovery_code" not in output.err


def test_create_admin_refuses_existing_admin_without_explicit_flag():
    from app.db.auth_store import MemoryAuthStore
    from app.seed import AdminAlreadyExists, create_admin

    store = MemoryAuthStore()
    create_admin(store, display_name="Root")

    with pytest.raises(AdminAlreadyExists):
        create_admin(store, display_name="Second Root")


def test_create_admin_if_missing_does_not_create_duplicate():
    from app.db.auth_store import MemoryAuthStore
    from app.seed import create_admin

    store = MemoryAuthStore()
    first = create_admin(store, display_name="Root")
    second = create_admin(store, display_name="Second Root", if_missing=True)

    assert first.created is True
    assert second.created is False
    assert second.user is None
    assert second.recovery_code is None
