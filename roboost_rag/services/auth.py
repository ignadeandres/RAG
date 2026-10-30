"""Simulated local authentication: users and roles come from configuration."""

from __future__ import annotations

from dataclasses import dataclass

import bcrypt

from roboost_rag.config import ConfigError
from roboost_rag.domain import Role

# Compared against when the user does not exist, so timing does not reveal valid usernames.
_DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


@dataclass(frozen=True)
class _User:
    password_hash: bytes
    role: Role


class UserDirectory:
    def __init__(self, spec: str):
        """`spec` is "user:bcrypt_hash:role" entries separated by commas."""
        self._users: dict[str, _User] = {}
        for entry in filter(None, (e.strip() for e in spec.split(","))):
            parts = entry.split(":")
            if len(parts) != 3:
                raise ConfigError(f"Entrada de APP_USERS inválida: {parts[0]!r}")
            name, password_hash, role = parts
            try:
                self._users[name] = _User(password_hash.encode(), Role(role))
            except ValueError:
                raise ConfigError(f"Rol desconocido en APP_USERS para {name!r}: {role!r}") from None

    def __len__(self) -> int:
        return len(self._users)

    def authenticate(self, username: str, password: str) -> Role | None:
        user = self._users.get(username)
        stored = user.password_hash if user else _DUMMY_HASH
        try:
            ok = bcrypt.checkpw(password.encode(), stored)
        except ValueError:  # malformed hash in configuration
            return None
        return user.role if ok and user else None
