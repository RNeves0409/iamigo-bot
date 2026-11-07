import sys
import os
import tempfile
import unittest
from unittest import mock
from unittest.mock import patch

# Adicionar o diretório raiz do projeto ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configurar variáveis de ambiente para os testes ANTES de importar services
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_USER_ID", "12345")

import services.handler as handler
from db import connection as db_connection


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


class TestFormatDate(unittest.TestCase):
    """Testes para a função format_date."""

    def test_format_date(self):
        result = handler.format_date(1700000000)
        self.assertIsInstance(result, str)
        self.assertIn("/", result)

    def test_format_date_with_timestamp(self):
        result = handler.format_date(1700000000)
        self.assertGreater(len(result), 0)


class TestHelpText(unittest.TestCase):
    """Testes para o texto de ajuda."""

    def test_help_contains_commands(self):
        help_text = handler.HELP
        self.assertIn("/novo", help_text)
        self.assertIn("/confirmar", help_text)
        self.assertIn("/abandonar", help_text)
        self.assertIn("/agenda", help_text)
        self.assertIn("/cancelar", help_text)
        self.assertIn("/ajuda", help_text)

    def test_help_mentions_timezone(self):
        self.assertIn("America/Sao_Paulo", handler.HELP)


class TestHandleCommand(unittest.TestCase):
    """Testes para a função handle (comandos do bot)."""

    def setUp(self):
        # Configurar o banco de dados para um arquivo temporário
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.original_db_path = db_connection.DB_PATH
        db_connection.DB_PATH = self.temp_db.name
        # Mock do send para não fazer chamadas HTTP reais
        self.send_patcher = patch("services.handler.send")
        self.mock_send = self.send_patcher.start()

    def tearDown(self):
        # Restaurar o caminho do banco
        db_connection.DB_PATH = self.original_db_path
        self.send_patcher.stop()
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_command_help(self):
        """Teste do comando /ajuda."""
        message = MockMessage("/ajuda")
        handler.handle(message)
        self.mock_send.assert_called_once()

    def test_command_start(self):
        """Teste do comando /start."""
        message = MockMessage("/start")
        handler.handle(message)
        self.mock_send.assert_called_once()

    def test_command_novo(self):
        """Teste do comando /novo."""
        message = MockMessage("/novo Consulta | 12/11/2026 14:00 | 60")
        handler.handle(message)
        self.mock_send.assert_called_once()

    def test_command_invalid(self):
        """Teste de comando inválido."""
        message = MockMessage("/comando_invalido")
        handler.handle(message)
        self.mock_send.assert_called_once()


class TestNotifications(unittest.TestCase):
    """Testes para a função notifications."""

    def setUp(self):
        # Configurar o caminho do banco de dados para um arquivo temporário
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.original_db_path = db_connection.DB_PATH
        db_connection.DB_PATH = self.temp_db.name
        # Mock do send
        self.send_patcher = patch("services.handler.send")
        self.mock_send = self.send_patcher.start()

    def tearDown(self):
        # Restaurar o caminho do banco
        db_connection.DB_PATH = self.original_db_path
        self.send_patcher.stop()
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_notifications_empty(self):
        """Testar que a função não falha com agenda vazia."""
        db = db_connection.connect()
        try:
            result = handler.notifications()
            self.assertIsNone(result)
        finally:
            db.close()


class TestIntegration(unittest.TestCase):
    """Testes de integração para a camada de serviço."""

    def setUp(self):
        # Criar um banco temporário para testes
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.original_db_path = db_connection.DB_PATH
        db_connection.DB_PATH = self.temp_db.name
        # Mock do send
        self.send_patcher = patch("services.handler.send")
        self.mock_send = self.send_patcher.start()

    def tearDown(self):
        # Restaurar o caminho do banco
        db_connection.DB_PATH = self.original_db_path
        self.send_patcher.stop()
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_novo_and_confirmar(self):
        """Teste de fluxo completo: novo -> confirmar."""
        # Simular o comando /novo
        message = MockMessage("/novo Teste | 12/11/2026 14:00 | 60")
        handler.handle(message)
        self.mock_send.assert_called_once()

        # Verificar que o rascunho foi salvo no config
        db = db_connection.connect()
        try:
            row = db.execute(
                "SELECT valor FROM config WHERE chave='rascunho'"
            ).fetchone()
            self.assertIsNotNone(row)
            # Verificar que o rascunho contém os dados corretos
            import json
            draft = json.loads(row[0])
            self.assertEqual(draft["titulo"], "Teste")
        finally:
            db.close()

    def test_confirmar_salva_agenda(self):
        """Teste: confirmar salva o compromisso na agenda."""
        # Criar rascunho via /novo
        message = MockMessage("/novo Consulta | 12/11/2026 14:00 | 60")
        handler.handle(message)

        # Confirmar
        message2 = MockMessage("/confirmar")
        handler.handle(message2)
        self.mock_send.assert_called()

        # Verificar que o compromisso está na agenda
        db = db_connection.connect()
        try:
            row = db.execute(
                "SELECT id, titulo, estado FROM agenda WHERE titulo='Consulta'"
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[2], "pendente")
        finally:
            db.close()

    def test_abandonar_descarta_rascunho(self):
        """Teste: abandonar descarta o rascunho."""
        message = MockMessage("/novo Teste | 12/11/2026 14:00 | 60")
        handler.handle(message)
        self.mock_send.assert_called()

        # Abandonar
        message2 = MockMessage("/abandonar")
        handler.handle(message2)
        self.mock_send.assert_called()

        # Verificar que o rascunho foi removido
        db = db_connection.connect()
        try:
            row = db.execute(
                "SELECT valor FROM config WHERE chave='rascunho'"
            ).fetchone()
            self.assertIsNone(row)
        finally:
            db.close()

    def test_agenda_empty(self):
        """Testar a agenda com nenhum compromisso."""
        message = MockMessage("/agenda")
        handler.handle(message)
        self.mock_send.assert_called_once()
        call_args = self.mock_send.call_args[0][0]
        self.assertIn("Nenhum compromisso", call_args)

    def test_cancelar(self):
        """Teste: cancelar um compromisso."""
        # Criar um compromisso
        message = MockMessage("/novo Teste | 12/11/2026 14:00 | 60")
        handler.handle(message)
        self.mock_send.assert_called_once()

        # Confirmar
        message2 = MockMessage("/confirmar")
        handler.handle(message2)
        self.mock_send.assert_called()

        # Cancelar
        message3 = MockMessage("/cancelar 1")
        handler.handle(message3)
        self.mock_send.assert_called()

        # Verificar que foi cancelado
        db = db_connection.connect()
        try:
            row = db.execute(
                "SELECT estado FROM agenda WHERE id=1"
            ).fetchone()
            self.assertEqual(row[0], "cancelado")
        finally:
            db.close()

    def test_invalid_input(self):
        """Teste: entrada inválida no /novo."""
        message = MockMessage("/novo | 12/11/2026 14:00 | 60")
        handler.handle(message)
        self.mock_send.assert_called_once()

    def test_past_date(self):
        """Teste: data passada no /novo."""
        # Data em 2020 (passada)
        message = MockMessage("/novo Teste | 01/01/2020 14:00 | 60")
        handler.handle(message)
        self.mock_send.assert_called_once()

    def test_notification_cycle(self):
        """Teste: ciclo de notificação para lembrete expirado."""
        # Criar um lembrete com aviso no passado
        # Manually insert into DB
        db = db_connection.connect()
        try:
            db.execute(
                "INSERT INTO agenda (titulo, evento, aviso, estado, tentativas, proxima) "
                "VALUES (?, ?, ?, 'pendente', 0, 0)",
                ("Teste notif", 1700000000, 1700000000),
            )
            db.commit()
        finally:
            db.close()

        # Chamar notifications
        result = handler.notifications()
        self.assertIsNone(result)
        # O aviso foi enviado (mock)
        self.mock_send.assert_called()


if __name__ == "__main__":
    unittest.main()
