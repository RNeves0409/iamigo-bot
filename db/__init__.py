"""Acesso ao banco de dados (SQLite)."""

from db.connection import (
    DB_PATH,
    connect,
    delete_config,
    get_config,
    get_config_value,
    set_config,
    set_config_value,
)

__all__ = [
    "DB_PATH",
    "connect",
    "delete_config",
    "get_config",
    "get_config_value",
    "set_config",
    "set_config_value",
]
