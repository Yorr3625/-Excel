"""Локальная учётная запись администратора веб-дашборда."""

from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import json
import os
import secrets
import tempfile
from pathlib import Path

from modules.paths import DASHBOARD_AUTH_FILE


AUTH_VERSION = 1
AUTH_ALGORITHM = "pbkdf2_sha256"
AUTH_ITERATIONS = 600_000
_SALT_BYTES = 16
_HASH_BYTES = 32
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"


class AuthConfigurationError(RuntimeError):
    """Локальная конфигурация входа отсутствует или повреждена."""


def _encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode(value: object, field: str) -> bytes:
    if not isinstance(value, str):
        raise AuthConfigurationError(f"Некорректное поле {field}.")
    try:
        return base64.b64decode(value, validate=True)
    except ValueError as error:
        raise AuthConfigurationError(f"Некорректное поле {field}.") from error


def _validate_configuration(config: object) -> dict:
    if not isinstance(config, dict):
        raise AuthConfigurationError("Некорректная конфигурация входа.")

    username = config.get("username")
    if not isinstance(username, str) or not username.strip() or len(username) > 256:
        raise AuthConfigurationError("Некорректное имя пользователя.")
    if config.get("version") != AUTH_VERSION:
        raise AuthConfigurationError("Неподдерживаемая версия конфигурации входа.")
    if config.get("algorithm") != AUTH_ALGORITHM:
        raise AuthConfigurationError("Неподдерживаемый алгоритм входа.")

    iterations = config.get("iterations")
    if not isinstance(iterations, int) or not 100_000 <= iterations <= 2_000_000:
        raise AuthConfigurationError("Некорректные параметры входа.")

    salt = _decode(config.get("salt"), "salt")
    password_hash = _decode(config.get("password_hash"), "password_hash")
    if len(salt) < _SALT_BYTES or len(password_hash) != _HASH_BYTES:
        raise AuthConfigurationError("Некорректные параметры входа.")

    return {
        "username": username,
        "iterations": iterations,
        "salt": salt,
        "password_hash": password_hash,
    }


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
        )
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as error:
        raise AuthConfigurationError("Не удалось сохранить конфигурацию входа.") from error
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def provision_credentials(
    username: str,
    password: str,
    path: str | Path = DASHBOARD_AUTH_FILE,
) -> None:
    """Создаёт или заменяет локальную учётную запись администратора."""

    username = username.strip()
    if not username:
        raise AuthConfigurationError("Имя пользователя не может быть пустым.")
    if not password:
        raise AuthConfigurationError("Пароль не может быть пустым.")

    salt = secrets.token_bytes(_SALT_BYTES)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        AUTH_ITERATIONS,
        dklen=_HASH_BYTES,
    )
    config = {
        "version": AUTH_VERSION,
        "username": username,
        "algorithm": AUTH_ALGORITHM,
        "iterations": AUTH_ITERATIONS,
        "salt": _encode(salt),
        "password_hash": _encode(password_hash),
    }
    _atomic_write(Path(path), json.dumps(config, ensure_ascii=False, indent=2) + "\n")


def ensure_default_credentials(path: str | Path = DASHBOARD_AUTH_FILE) -> None:
    """Создаёт требуемую локальную учётную запись при первом запуске."""

    config_path = Path(path)
    if not config_path.exists():
        provision_credentials(DEFAULT_USERNAME, DEFAULT_PASSWORD, config_path)


def load_auth_configuration(path: str | Path = DASHBOARD_AUTH_FILE) -> dict:
    """Загружает и проверяет локальную конфигурацию входа."""

    try:
        payload = Path(path).read_text(encoding="utf-8")
        config = json.loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AuthConfigurationError("Конфигурация входа недоступна.") from error
    return _validate_configuration(config)


def verify_credentials(
    username: str,
    password: str,
    path: str | Path = DASHBOARD_AUTH_FILE,
) -> bool:
    """Проверяет имя и пароль без раскрытия причины отказа."""

    ensure_default_credentials(path)
    config = load_auth_configuration(path)
    candidate_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        config["salt"],
        config["iterations"],
        dklen=_HASH_BYTES,
    )
    usernames_match = hmac.compare_digest(username, config["username"])
    passwords_match = hmac.compare_digest(candidate_hash, config["password_hash"])
    return usernames_match and passwords_match


def main() -> None:
    """Интерактивно меняет локальные реквизиты администратора."""

    username = input(f"Логин [{DEFAULT_USERNAME}]: ").strip() or DEFAULT_USERNAME
    password = getpass.getpass("Новый пароль: ")
    repeated_password = getpass.getpass("Повторите пароль: ")
    if password != repeated_password:
        raise SystemExit("Пароли не совпадают.")
    provision_credentials(username, password)
    print("Учётные данные администратора сохранены.")


if __name__ == "__main__":
    main()
