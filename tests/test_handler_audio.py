"""Fluxo de áudio do bot (Fase 4) — voz/audio → STT (Whisper) → IA → salva.

Testes baseiam-se no contrato da camada de áudio do handler:
  message.voice / message.audio / document(mime_type=audio/*)
  → api("getFile") → download → ai.transcribe (Whisper) → ai.interpret
  → salva na agenda + confirma ao usuário.
Toda a chamada externa é simulada em memória (nenhuma rede, nenhum modelo).
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

# Adicionar o diretório raiz do projeto ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Variáveis de ambiente ANTES de importar services
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_USER_ID", "12345")

from api.client import ApiError

import services.handler as handler
from db import connection as db_connection
from services import ai


class MockMessage:
    """Objeto de mensagem simulado, com suporte a áudio/voz/documento."""

    def __init__(self, text=None, voice=None, audio=None, document=None,
                 user_id=12345, chat_type="private"):
        self.text = text or ""
        self.voice = voice or None
        self.audio = audio or None
        self.document = document or None
        self.from_user = {"id": user_id} if user_id else {}
        self.chat = {"type": chat_type}
        self.message_id = 1

    def get(self, key, default=None):
        """Simula o comportamento de dict.get()."""
        if key == "from":
            return self.from_user
        if key == "chat":
            return self.chat
        if key == "voice":
            return self.voice
        if key == "audio":
            return self.audio
        if key == "document":
            return self.document
        if key == "text":
            return self.text
        return default


class TestRouteAudio(unittest.TestCase):
    """Caminho de áudio: voz → transcrição → IA → salvamento."""

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

    def test_route_audio_full_success(self):
        """Fase 4: áudio → STT → IA → IA salva lembrete + confirma."""
        mock_api = mock.MagicMock(return_value={"file_path": "photos/vc.ogg"})
        mock_client = mock.MagicMock()
        mock_client.transcribe.return_value = "Consulta odontológica | 08/11/2026 20:00"
        mock_download = mock.MagicMock(return_value=b"audio-data")
        mock_open = mock.mock_open()
        mock_class = mock.MagicMock(return_value=mock_client)
        with mock.patch("services.handler.api", mock_api), \
             mock.patch("services.handler.ai.OllamaClient", mock_class), \
             mock.patch("services.handler.ai.interpret", return_value={
                 "titulo": "Consulta odontológica",
                 "data": "08/11/2026",
                 "hora": "20:00",
                 "aviso_minutos": 0,
                 "repeticao": "",
                 "fuso": "America/Sao_Paulo",
             }), \
             mock.patch("services.handler.open", mock_open), \
             mock.patch("services.handler._download_file", mock_download):
            handler.handle(MockMessage(voice={"file_id": "voice-123"}))
        self.mock_send.assert_called_once()
        sent = self.mock_send.call_args[0][0]
        self.assertIn("Lembrete salvo", sent)
        self.assertIn("Consulta odontológica", sent)
        # a cadeia completa foi pericada na ordem certa
        mock_api.assert_called_once_with("getFile", file_id="voice-123")
        mock_client.transcribe.assert_called_once()

    def test_route_audio_transcribe_fails_uses_legacy(self):
        """Fase 4: Whisper falha → modo legado, sem salvar."""
        mock_api = mock.MagicMock(return_value={"file_path": "photos/vc.ogg"})
        mock_client = mock.MagicMock()
        mock_client.transcribe.side_effect = ai.OllamaUnavailable
        mock_download = mock.MagicMock(return_value=b"audio-data")
        mock_open = mock.mock_open()
        mock_class = mock.MagicMock(return_value=mock_client)
        with mock.patch("services.handler.api", mock_api), \
             mock.patch("services.handler.ai.OllamaClient", mock_class), \
             mock.patch("services.handler.open", mock_open), \
             mock.patch("services.handler._download_file", mock_download):
            handler.handle(MockMessage(voice={"file_id": "voice-123"}))
        self.mock_send.assert_called_once()
        self.assertIn("modo legado", self.mock_send.call_args[0][0])
        # nenhum record foi salvo
        with mock.patch("services.handler.open", mock_open):
            db = db_connection.connect()
            try:
                row = db.execute(
                    "SELECT valor FROM config WHERE chave='rascunho'"
                ).fetchone()
                self.assertIsNone(row)
            finally:
                db.close()

    def test_route_audio_getfile_fails_uses_legacy(self):
        """Fase 4: getFile falha → modo legado."""
        mock_api = mock.MagicMock(side_effect=ApiError(code=403))
        with mock.patch("services.handler.api", mock_api):
            handler.handle(MockMessage(voice={"file_id": "voice-123"}))
        self.mock_send.assert_called_once()
        self.assertIn("modo legado", self.mock_send.call_args[0][0])

    def test_route_audio_no_audio_message_ignored(self):
        """Fase 4: mensagem sem áudio segue o fluxo normal (texto)."""
        record = {
            "titulo": "Consulta odontológica",
            "data": "08/11/2026",
            "hora": "20:00",
            "aviso_minutos": 0,
            "repeticao": "",
            "fuso": "America/Sao_Paulo",
        }
        with mock.patch("services.handler.ai.interpret", return_value=record):
            handler.handle(MockMessage("Consulta odontológica | 08/11/2026 20:00"))
        self.mock_send.assert_called_once()
        self.assertIn("Lembrete salvo", self.mock_send.call_args[0][0])


class TestRouteAudioEdgeCases(unittest.TestCase):
    """Casos extremos de entrada de áudio."""

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

    def test_route_audio_document_audio(self):
        """Fase 4: áudio pode vir como document (mime_type audio/*)."""
        doc = {"mime_type": "audio/mpeg", "file_id": "doc-456",
               "file_size": 12345}
        mock_api = mock.MagicMock(return_value={"file_path": "docs/d.ogg"})
        mock_client = mock.MagicMock()
        mock_client.transcribe.return_value = "Reunião de equipe | 09/11/2026 10:00"
        mock_download = mock.MagicMock(return_value=b"audio-data")
        mock_open = mock.mock_open()
        with mock.patch("services.handler.api", mock_api), \
             mock.patch("services.handler.ai.OllamaClient", mock_client), \
             mock.patch("services.handler.ai.interpret", return_value={
                 "titulo": "Reunião",
                 "data": "09/11/2026",
                 "hora": "10:00",
                 "aviso_minutos": 0,
                 "repeticao": "",
                 "fuso": "America/Sao_Paulo",
             }), \
             mock.patch("services.handler.open", mock_open), \
             mock.patch("services.handler._download_file", mock_download):
            handler.handle(MockMessage(document=doc))
        self.mock_send.assert_called_once()
        self.assertIn("Lembrete salvo", self.mock_send.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
