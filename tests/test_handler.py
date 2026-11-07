"""Testes da camada de serviço — Fase 3 (fluxo com IA + modo legado)."""

import os
import sys
import tempfile
import unittest
from unittest import mock

# Adicionar o diretório raiz do projeto ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Variáveis de ambiente ANTES de importar services (imports de módulos
# leem essas variáveis imediatamente)
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_USER_ID", "12345")

import services.handler as handler
from db import connection as db_connection
from services import ai


class MockMessage:
    """Objeto de mensagem simulado para testes."""

    def __init__(self, text, user_id=12345, chat_type="private"):
        self.text = text
        self.from_user = {"id": user_id} if user_id else {}
        self.chat = {"type": chat_type}
        self.message_id = 1

    def get(self, key, default=None):
        """Simula o comportamento de dict.get()."""
        if key == "from":
            return self.from_user
        if key == "chat":
            return self.chat
        if key == "text":
            return self.text
        return default


class TestRouteDirectText(unittest.TestCase):
    """Caminho da IA (texto livre -> interpreta -> salva)."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.original_db_path = db_connection.DB_PATH
        db_connection.DB_PATH = self.temp_db.name
        self.send_patcher = mock.patch("services.handler.send")
        self.mock_send = self.send_patcher.start()

    def tearDown(self):
        db_connection.DB_PATH = self.original_db_path
        self.send_patcher.stop()
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def _record(self):
        return {
            "titulo": "Consulta odontológica",
            "data": "05/11/2026",
            "hora": "14:00",
            "aviso_minutos": 60,
            "repeticao": "",
            "fuso": "America/Sao_Paulo",
        }

    def test_direct_text_saves_reminder_and_confirms(self):
        """Fase 3: texto livre + IA OK -> agenda salva + mensagem de confirmação."""
        with mock.patch.object(ai, "interpret", return_value=self._record()):
            message = MockMessage("Consulta odontológica | 05/11/2026 14:00 | 60")
            handler.handle(message)
            self.mock_send.assert_called_once()
            sent = self.mock_send.call_args[0][0]
            self.assertIn("Lembrete salvo", sent)
            self.assertIn("Consulta odontológica", sent)

        db = db_connection.connect()
        try:
            row = db.execute(
                "SELECT titulo, estado FROM agenda WHERE titulo='Consulta odontológica'"
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[1], "pendente")
        finally:
            db.close()

    def test_direct_text_with_repetition_saves(self):
        """Fase 3: repetição e fuso são preservados no registro."""
        with mock.patch.object(
            ai,
            "interpret",
            return_value={
                "titulo": "Reunião",
                "data": "06/11/2026",
                "hora": "09:00",
                "aviso_minutos": 30,
                "repeticao": "semanal",
                "fuso": "America/Sao_Paulo",
            },
        ):
            handler.handle(MockMessage("Reunião semanal | 06/11/2026 09:00 | 30"))
        db = db_connection.connect()
        try:
            row = db.execute(
                "SELECT titulo FROM agenda WHERE titulo='Reunião'"
            ).fetchone()
            self.assertIsNotNone(row)
        finally:
            db.close()
        sent = self.mock_send.call_args[0][0]
        self.assertIn("🔁 Repetição: semanal", sent)

    def test_direct_ai_unavailable_falls_back_to_legacy(self):
        """Fase 3: IA fora do ar -> modo legado com suporte /novo."""
        with mock.patch.object(ai, "interpret", side_effect=ai.OllamaUnavailable):
            handler.handle(MockMessage("Consulta odontológica | 05/11/2026 14:00 | 60"))
            sent = self.mock_send.call_args[0][0]
            self.assertIn("/novo", sent)
            self.assertIn("modo legado", sent)

    def test_direct_ai_parse_error_falls_back_to_legacy(self):
        """Fase 3: IA não extraiu título/data -> modo legado."""
        with mock.patch.object(
            ai, "interpret", side_effect=ai.OllamaError("não extraiu titulo")
        ):
            handler.handle(MockMessage("Consulta odontológica | 05/11/2026 14:00 | 60"))
            sent = self.mock_send.call_args[0][0]
            self.assertIn("/novo", sent)


class TestRouteLegacy(unittest.TestCase):
    """Caminho legado (comandos /novo, /confirmar, ...) — equivalente à Fase 2."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.original_db_path = db_connection.DB_PATH
        db_connection.DB_PATH = self.temp_db.name
        self.send_patcher = mock.patch("services.handler.send")
        self.mock_send = self.send_patcher.start()

    def tearDown(self):
        db_connection.DB_PATH = self.original_db_path
        self.send_patcher.stop()
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_route_legacy_novo_save_draft(self):
        message = MockMessage("/novo Consulta | 12/11/2026 14:00 | 60")
        handler.handle(message)
        self.mock_send.assert_called_once()
        db = db_connection.connect()
        try:
            row = db.execute("SELECT valor FROM config WHERE chave='rascunho'").fetchone()
            self.assertIsNotNone(row)
            draft = __import__("json").loads(row[0])
            self.assertEqual(draft["titulo"], "Consulta")
        finally:
            db.close()

    def test_route_legacy_confirm_adds_agenda(self):
        handler.handle(MockMessage("/novo Consulta | 12/11/2026 14:00 | 60"))
        handler.handle(MockMessage("/confirmar"))
        db = db_connection.connect()
        try:
            row = db.execute(
                "SELECT titulo, estado FROM agenda WHERE titulo='Consulta'"
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[1], "pendente")
        finally:
            db.close()

    def test_route_legacy_abandon_removes_draft(self):
        handler.handle(MockMessage("/novo Teste | 12/11/2026 14:00 | 60"))
        handler.handle(MockMessage("/abandonar"))
        db = db_connection.connect()
        try:
            row = db.execute("SELECT valor FROM config WHERE chave='rascunho'").fetchone()
            self.assertIsNone(row)
        finally:
            db.close()

    def test_route_legacy_agenda_empty(self):
        handler.handle(MockMessage("/agenda"))
        self.mock_send.assert_called_once()
        call_args = self.mock_send.call_args[0][0]
        self.assertIn("Nenhum compromisso", call_args)

    def test_route_legacy_cancel(self):
        handler.handle(MockMessage("/novo Teste | 12/11/2026 14:00 | 60"))
        handler.handle(MockMessage("/confirmar"))
        handler.handle(MockMessage("/cancelar 1"))
        db = db_connection.connect()
        try:
            row = db.execute(
                "SELECT estado FROM agenda WHERE id=1"
            ).fetchone()
            self.assertEqual(row[0], "cancelado")
        finally:
            db.close()

    def test_route_legacy_invalid_novo(self):
        handler.handle(MockMessage("/novo | 12/11/2026 14:00 | 60"))
        self.mock_send.assert_called_once()
        self.assertIn("Use: /novo", self.mock_send.call_args[0][0])

    def test_route_legacy_unknown_command(self):
        handler.handle(MockMessage("/comando_desconhecido"))
        self.mock_send.assert_called_once()
        self.assertIn("Comando não reconhecido", self.mock_send.call_args[0][0])


class TestSecurityAndRouting(unittest.TestCase):
    """Regras de acesso e roteamento gerais."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.original_db_path = db_connection.DB_PATH
        db_connection.DB_PATH = self.temp_db.name
        self.send_patcher = mock.patch("services.handler.send")
        self.mock_send = self.send_patcher.start()

    def tearDown(self):
        db_connection.DB_PATH = self.original_db_path
        self.send_patcher.stop()
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_non_owner_ignored(self):
        handler.handle(MockMessage("/novo Teste | 12/11/2026 14:00 | 60", user_id=99999))
        self.mock_send.assert_not_called()

    def test_non_private_chat_ignored(self):
        handler.handle(MockMessage("/novo Teste | 12/11/2026 14:00 | 60", chat_type="group"))
        self.mock_send.assert_not_called()

    def test_empty_text_ignored(self):
        handler.handle(MockMessage("   "))
        self.mock_send.assert_not_called()

    def test_help_shows_direct_and_legacy_modes(self):
        handler.handle(MockMessage("/ajuda"))
        sent = self.mock_send.call_args[0][0]
        self.assertIn("MODO DIRETO", sent)
        self.assertIn("MODO LEGADO", sent)


if __name__ == "__main__":
    unittest.main()
