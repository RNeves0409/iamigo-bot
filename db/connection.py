"""Acesso ao banco de dados (SQLite)."""

import os
import sqlite3

DB_PATH = os.environ.get("IAMIGO_DB_PATH", "/var/lib/iamigo/agenda.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS agenda (
    id INTEGER PRIMARY KEY,
    titulo TEXT NOT NULL,
    evento REAL NOT NULL,
    aviso REAL NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pendente',
    tentativas INTEGER NOT NULL DEFAULT 0,
    proxima REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS config (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
"""


def connect():
    """Abre uma conexão com o banco de dados e garante a existência do esquema."""
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA)
    db.commit()
    return db


def get_config(db, chave):
    """Recupera um valor da tabela config."""
    row = db.execute("SELECT valor FROM config WHERE chave = ?", (chave,)).fetchone()
    return row[0] if row else None


def set_config(db, chave, valor):
    """Insere ou substitui um valor na tabela config."""
    db.execute(
        "INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)",
        (chave, valor),
    )


def delete_config(db, chave):
    """Remove um valor da tabela config."""
    db.execute("DELETE FROM config WHERE chave = ?", (chave,))


def get_config_value(key):
    """Recupera um valor da tabela config (nova conexão)."""
    db = connect()
    try:
        row = db.execute("SELECT valor FROM config WHERE chave = ?", (key,)).fetchone()
        return row[0] if row else None
    finally:
        db.close()


def set_config_value(key, value):
    """Insere ou substitui um valor na tabela config (nova conexão)."""
    db = connect()
    try:
        db.execute(
            "INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)",
            (key, value),
        )
        db.commit()
    finally:
        db.close()
