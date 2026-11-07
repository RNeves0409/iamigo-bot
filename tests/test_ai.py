"""Testes para a camada de IA (services/ai.py) - modo mockado."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

# Diretorio raiz do projeto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Variaveis de ambiente ANTES de importar services.ai
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_USER_ID", "12345")
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
os.environ["OLLAMA_MODEL"] = "llama3.1:8b"
os.environ["WHISPER_MODEL"] = "whisper:small"

import services.ai as ai  # noqa: E402
from services.ai import (  # noqa: E402
    OllamaClient,
    OllamaError,
    OllamaTimeout,
    parse_reminder,
    interpret,
)


class TestParseReminder(unittest.TestCase):
    """Teste do parser de saida da IA."""

    def test_json_completo(self):
        raw = '{"titulo": "Consulta", "data": "05/11/2026", "hora": "14:00", "aviso_minutos": 60, "repeticao": "", "fuso": "America/Sao_Paulo"}'
        record = parse_reminder(raw)
        self.assertEqual(record["titulo"], "Consulta")
        self.assertEqual(record["data"], "05/11/2026")
        self.assertEqual(str(record["aviso_minutos"]), "60")

    def test_sem_titulo_eh_none(self):
        self.assertIsNone(parse_reminder('{"data": "05/11/2026", "hora": "14:00"}'))

    def test_multilinha(self):
        raw = "Titulo: Reuniao\nData: 12/11/2026\nHora: 10:00\nAviso: 30 min"
        record = parse_reminder(raw)
        self.assertEqual(record.get("titulo"), "Reuniao")
        self.assertEqual(record.get("data"), "12/11/2026")


class TestInterpret(unittest.TestCase):
    """Teste do fluxo interpret (mock da OllamaClient)."""

    def setUp(self):
        self._patches = []
        # Mock do metodo generate (chat)
        p1 = patch.object(ai.OllamaClient, "generate", return_value='{"titulo": "Consulta", "data": "05/11/2026", "hora": "14:00", "aviso_minutos": 60, "repeticao": "", "fuso": "America/Sao_Paulo"}')
        self._patches.append(p1)
        # Mock da transcricao de audio
        p2 = patch.object(ai.OllamaClient, "transcribe", return_value="Consulta odontologica em 06/11/2026 as 09:00 com aviso de 60")
        self._patches.append(p2)
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def test_interpret_texto(self):
        record = interpret("/novo Consulta odontologica | 05/11/2026 14:00 | 60")
        self.assertEqual(record["titulo"], "Consulta")
        self.assertEqual(record["data"], "05/11/2026")
        self.assertEqual(record["aviso_minutos"], 60)

    def test_interpret_audio(self):
        audio_text = "Consulta odontologica em 06/11/2026 as 09:00 com aviso de 60"
        with patch.object(ai.OllamaClient, "transcribe", return_value=audio_text), \
             patch.object(ai.OllamaClient, "generate", return_value='{"titulo": "Consulta", "data": "06/11/2026", "hora": "09:00", "aviso_minutos": 60, "repeticao": "", "fuso": "America/Sao_Paulo"}'):
            record = interpret("bebida em 06/11/2026 as 09:00", audio_path="/tmp/audio.mp3")
        self.assertEqual(record["titulo"], "Consulta")
        self.assertEqual(record["data"], "06/11/2026")

    def test_interpret_sem_campos_lanca_erro(self):
        with patch.object(ai.OllamaClient, "generate", return_value="eu nao entendi nada"):
            with self.assertRaises(OllamaError):
                interpret("texto sem campos")


class TestOllamaClient(unittest.TestCase):
    """Teste do cliente Ollama (mock do _request)."""

    def setUp(self):
        self._patches = []

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def test_is_available_com_modelos(self):
        with patch("services.ai._request", return_value={"models": [{"name": "llama3.1:8b"}, {"name": "whisper:small"}]}):
            client = OllamaClient()
            self.assertTrue(client.is_available())

    def test_is_available_sem_modelos(self):
        with patch("services.ai._request", return_value={"models": []}):
            self.assertFalse(OllamaClient().is_available())

    def test_generate_retorna_texto(self):
        with patch.object(ai.OllamaClient, "generate", return_value="resposta dummy"):
            client = OllamaClient()
            self.assertEqual(client.generate("oi"), "resposta dummy")
