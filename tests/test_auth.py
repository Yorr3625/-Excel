import json

import pytest

from modules import auth


def test_provisioned_credentials_are_hashed_and_verified(tmp_path):
    path = tmp_path / "auth.json"

    auth.provision_credentials("manager", "secret-password", path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["username"] == "manager"
    assert "secret-password" not in path.read_text(encoding="utf-8")
    assert auth.verify_credentials("manager", "secret-password", path) is True
    assert auth.verify_credentials("manager", "wrong-password", path) is False
    assert auth.verify_credentials("other", "secret-password", path) is False


def test_default_credentials_are_created_on_first_login(tmp_path):
    path = tmp_path / "auth.json"

    assert auth.verify_credentials("admin", "admin", path) is True
    assert path.is_file()
    assert '"password": "admin"' not in path.read_text(encoding="utf-8")


def test_invalid_auth_configuration_denies_access(tmp_path):
    path = tmp_path / "auth.json"
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(auth.AuthConfigurationError):
        auth.verify_credentials("admin", "admin", path)


def test_empty_credentials_cannot_be_provisioned(tmp_path):
    with pytest.raises(auth.AuthConfigurationError):
        auth.provision_credentials("", "password", tmp_path / "auth.json")

    with pytest.raises(auth.AuthConfigurationError):
        auth.provision_credentials("admin", "", tmp_path / "auth.json")
