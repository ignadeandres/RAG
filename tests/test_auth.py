import pytest

from roboost_rag.config import ConfigError
from roboost_rag.domain import Role
from roboost_rag.services.auth import UserDirectory, hash_password


@pytest.fixture(scope="module")
def users():
    return UserDirectory(
        f"ana:{hash_password('ana-pass')}:public,"
        f"luis:{hash_password('luis-pass')}:hr_manager,"
        f"eva:{hash_password('eva-pass')}:admin"
    )


def test_valid_credentials_give_role(users):
    assert users.authenticate("ana", "ana-pass") is Role.PUBLIC
    assert users.authenticate("luis", "luis-pass") is Role.HR_MANAGER
    assert users.authenticate("eva", "eva-pass") is Role.ADMIN


def test_wrong_password_rejected(users):
    assert users.authenticate("luis", "ana-pass") is None


def test_unknown_user_rejected(users):
    assert users.authenticate("mallory", "x") is None


def test_unknown_role_is_config_error():
    with pytest.raises(ConfigError, match="Rol desconocido"):
        UserDirectory(f"x:{hash_password('p')}:superuser")


def test_malformed_entry_is_config_error():
    with pytest.raises(ConfigError):
        UserDirectory("solo-nombre")


def test_empty_spec_has_no_users():
    assert len(UserDirectory("")) == 0
