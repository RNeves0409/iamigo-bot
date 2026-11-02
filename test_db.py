"""Testes unitários da camada de dados (db.py).

Instruções de uso:
    cd /home/renato/projetos/iamigo
    . venv/bin/activate
    python -m unittest test_db -v
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db  # noqa: E402


def _in_memory():
    """Cria um diretório e retorna o caminho de um arquivo SQLite temporário."""
    tmpdir = tempfile.mkdtemp()
    return os.path.join(tmpdir, "test.db")


class TestDBSchema(unittest.TestCase):
    """Testa a conexão e o esquema do banco de dados."""

    def setUp(self):
        self._db_path = _in_memory()
        self._patch = mock.patch.object(db.connection, "DB_PATH", self._db_path)
        self._patch.start()
        self.connection = db.connect()

    def tearDown(self):
        self.connection.close()
        self._patch.stop()
        import shutil
        shutil.rmtree(os.path.dirname(self._db_path), ignore_errors=True)

    def test_tables_created(self):
        """A conexão cria as tabelas agenda e config."""
        tables = {
            row[0] for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertIn("agenda", tables)
        self.assertIn("config", tables)

    def test_get_config_value_returns_none_when_missing(self):
        self.assertIsNone(db.get_config_value("chave_inexistente"))


class TestConfigRepository(unittest.TestCase):
    """Testa operações de configuração persistida."""

    def setUp(self):
        self._db_path = _in_memory()
        self._patch = mock.patch.object(db.connection, "DB_PATH", self._db_path)
        self._patch.start()
        self.connection = db.connect()

    def tearDown(self):
        self.connection.close()
        self._patch.stop()
        import shutil
        shutil.rmtree(os.path.dirname(self._db_path), ignore_errors=True)

    def test_set_and_get_config(self):
        db.set_config(self.connection, "chave", "valor")
        self.assertEqual(db.get_config(self.connection, "chave"), "valor")

    def test_delete_config(self):
        db.set_config(self.connection, "chave", "valor")
        db.delete_config(self.connection, "chave")
        self.assertIsNone(db.get_config(self.connection, "chave"))

    def test_set_config_value_new(self):
        db.set_config_value("chave", "valor1")
        self.assertEqual(db.get_config_value("chave"), "valor1")

    def test_set_config_value_overrides(self):
        db.set_config_value("chave", "valor1")
        db.set_config_value("chave", "valor2")
        self.assertEqual(db.get_config_value("chave"), "valor2")


class TestAgendaRepository(unittest.TestCase):
    """Testa operações da tabela agenda via SQL."""

    def setUp(self):
        self._db_path = _in_memory()
        self._patch = mock.patch.object(db.connection, "DB_PATH", self._db_path)
        self._patch.start()
        self.connection = db.connect()

    def tearDown(self):
        self.connection.close()
        self._patch.stop()
        import shutil
        shutil.rmtree(os.path.dirname(self._db_path), ignore_errors=True)

    def test_insert_agenda(self):
        cursor = self.connection.execute(
            "INSERT INTO agenda (titulo, evento, aviso) VALUES (?, ?, ?)",
            ("Reunião", 1000, 900),
        )
        self.connection.commit()
        self.assertEqual(cursor.lastrowid, 1)

    def test_update_agenda_cancel(self):
        cursor = self.connection.execute(
            "INSERT INTO agenda (titulo, evento, aviso) VALUES (?, ?, ?)",
            ("Reunião", 1000, 900),
        )
        self.connection.commit()
        self.assertEqual(cursor.lastrowid, 1)

        cursor = self.connection.execute(
            "UPDATE agenda SET estado='cancelado' WHERE id=? AND estado!='cancelado'",
            (1,),
        )
        self.connection.commit()
        self.assertEqual(cursor.rowcount, 1)

        row = self.connection.execute(
            "SELECT estado FROM agenda WHERE id=?", (1,)
        ).fetchone()
        self.assertEqual(row[0], "cancelado")

    def test_insert_and_list(self):
        self.connection.execute(
            "INSERT INTO agenda (titulo, evento, aviso, estado) VALUES (?, ?, ?, ?)",
            ("A", 1000, 900, "pendente"),
        )
        self.connection.execute(
            "INSERT INTO agenda (titulo, evento, aviso, estado) VALUES (?, ?, ?, ?)",
            ("B", 2000, 1900, "pendente"),
        )
        self.connection.commit()

        rows = self.connection.execute(
            "SELECT titulo FROM agenda "
            "WHERE estado!='cancelado' AND evento>? ORDER BY evento LIMIT 30",
            (500,),
        ).fetchall()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], "A")
        self.assertEqual(rows[1][0], "B")

    def test_empty_query(self):
        rows = self.connection.execute(
            "SELECT titulo FROM agenda WHERE 1=0"
        ).fetchall()
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
