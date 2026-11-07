"""Contratos dos componentes de IA (Fase 4) — sem modelo real.

Toda a comunicação com a Ollama é simulada em memória, de modo que a suíte
não depende de rede, memória nem de cargas de modelo. Garante que o bot
está no caminho correto independente do modelo rodando.

Contrato validado:
  POST {base}/api/chat    -> {"message": {"role": "assistant", "content": "..."}}
  POST {base}/api/generate -> Whisper: {"content": "<texto transcrito>"}
  GET  {base}/api/tags
"""

import os
import sys
import unittest
from unittest import mock

# Adicionar o diretório raiz do projeto ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Variáveis de ambiente ANTES de importar services
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_USER_ID", "12345")

import services.ai as ai
import json
from services.ai import OllamaClient, OllamaError, OllamaTimeout, OllamaUnavailable


class TestOllamaClientGenerateContract(unittest.TestCase):
    """Contratos da geração (chat-completion) sem modelo real."""

    def setUp(self):
        self.client = OllamaClient(base_url="http://ollama:11434", timeout=5)

    def _fake_urlopen(self, payload):
        """Fake urllib response: payload dict -> JSON bytes, Context Manager."""
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = (
            payload if isinstance(payload, bytes)
            else json.dumps(payload).encode("utf-8")
        )
        mock_urlopen = mock.MagicMock()
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        return mock_urlopen

    def test_generate_returns_message_content(self):
        client = self.client
        with mock.patch(
            "services.ai.urllib.request.urlopen",
            self._fake_urlopen(
                {"message": {"role": "assistant", "content": "Olá, Renato!"}}
            ),
        ):
            content = client.generate("Teste de conexão")
        self.assertEqual(content, "Olá, Renato!")

    def test_generate_posts_chat_with_model(self):
        client = self.client
        with mock.patch(
            "services.ai.urllib.request.urlopen",
            self._fake_urlopen({"message": {"role": "assistant", "content": ""}}),
        ) as mock_urlopen:
            client.generate("Qual o horário do encontro?", model="llama3.2:3b")
        payload = mock_urlopen.call_args[0][0].data
        data = json.loads(payload)
        self.assertEqual(data["model"], "llama3.2:3b")
        self.assertFalse(data["stream"])
        self.assertEqual(len(data["messages"]), 1)

    def test_generate_low_timeout_raises_ollama_timeout(self):
        client = self.client
        with mock.patch(
            "services.ai.urllib.request.urlopen",
            side_effect=TimeoutError("connection timed out"),
        ):
            with self.assertRaises(OllamaTimeout):
                client.generate("rapido")

    def test_generate_http_error_raises_ollama_unavailable(self):
        client = self.client
        with mock.patch(
            "services.ai.urllib.request.urlopen",
            side_effect=ai.urllib.error.HTTPError(
                "http://ollama:11434/api/chat", "503", "Service Unavailable", {},
                None,
            ),
        ):
            with self.assertRaises(OllamaUnavailable):
                client.generate("rapido")


class TestOllamaClientTranscribeContract(unittest.TestCase):
    """Contratos da transcrição Whisper sem modelo real."""

    def setUp(self):
        self.client = OllamaClient(base_url="http://ollama:11434", timeout=10)

    def test_transcribe_returns_text(self):
        # transcribe lê o arquivo de áudio, depois chama a API (mockada)
        with open("/tmp/input.mp3", "wb") as handle:
            handle.write(b"fake-audio-bytes")
        mock_resp = mock.Mock()
        mock_resp.read.return_value = json.dumps({
            "content": "Consulta odontológica em 08/11/2026 20:00",
            "duration": 5.2,
        }).encode()
        mock_urlopen = mock.MagicMock()
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        with mock.patch(
            "services.ai.urllib.request.urlopen", mock_urlopen
        ):
            text = self.client.transcribe("/tmp/input.mp3")
        self.assertEqual(
            text, "Consulta odontológica em 08/11/2026 20:00"
        )
        os.remove("/tmp/input.mp3")

    def test_transcribe_http_error_raises_ollama_error(self):
        # prepara um arquivo de áudio real (transcribe lê o arquivo antes de
        # chamar a API)
        with open("/tmp/input.mp3", "wb") as handle:
            handle.write(b"fake-audio-bytes")
        with mock.patch(
            "services.ai.urllib.request.urlopen",
            side_effect=ai.urllib.error.HTTPError(
                "http://ollama:11434/api/generate", 503, "Service Unavailable",
                {}, None,
            ),
        ):
            with self.assertRaises(OllamaError):
                self.client.transcribe("/tmp/input.mp3")
        os.remove("/tmp/input.mp3")


class TestParseReminderContract(unittest.TestCase):
    """Contratos do parser de saída da IA (reuso de testes)."""

    def test_parse_accepts_json_record(self):
        record = ai.parse_reminder({
            "titulo": "Consulta",
            "data": "08/11/2026",
            "hora": "20:00",
            "aviso_minutos": 30,
        })
        self.assertEqual(record["titulo"], "Consulta")
        self.assertEqual(record["aviso_minutos"], 30)

    def test_parse_rejects_missing_title(self):
        self.assertIsNone(ai.parse_reminder("Sem titulo aqui"))
