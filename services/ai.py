"""Camada de integração com a IA local (Ollama).

Responsabilidade unica: falar com a IA. O bot nao Decide; ele chama o
metodo de interpretacao, valida o resultado e guarda na agenda.

Configuracao (variaveis de ambiente, padroes):
  OLLAMA_BASE_URL  http://ollama:11434       (rede compose)
  OLLAMA_MODEL     llama3.1:8b               (LLM para interpretacao)
  WHISPER_MODEL    whisper:small             (transcricao de audio)
  OLLAMA_TIMEOUT   120s                       (timeout de cada chamada)
  AI_CONFIDENCE_THRESHOLD  0.7               (minimo para salvar sem perguntar)
"""

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "whisper:small")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "120"))
AI_CONFIDENCE_THRESHOLD = float(os.environ.get("AI_CONFIDENCE_THRESHOLD", "0.7"))


class OllamaError(Exception):
    """Falha general de comunicacao com a IA."""


class OllamaUnavailable(OllamaError):
    """A IA nao responde (servico fora do ar, sobrecarga, modelo nao carregado)."""


class OllamaTimeout(OllamaError):
    """Chamada excedeu o timeout."""


def _request(url, payload=None, timeout=OLLAMA_TIMEOUT):
    """Envia requisicao HTTP para a Ollama e retorna o JSON da resposta."""
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    method = "POST" if payload is not None else "GET"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        body = error.read() if error.fp else b""
        raise OllamaError("HTTP %s: %s" % (error.code, body.decode(errors="replace")[:300]))
    except (urllib.error.URLError, TimeoutError) as error:
        raise OllamaTimeout(str(error)) from error
    except Exception as error:
        raise OllamaTimeout(str(error)) from error
    if not raw:
        raise OllamaError("resposta vazia do servidor")
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise OllamaError("resposta invalida: %r" % raw[:200]) from error


class OllamaClient:
    """Cliente sincrono para a API de chat/geracao da Ollama."""

    def __init__(self, base_url=None, timeout=None):
        self.base_url = (base_url or OLLAMA_BASE_URL).rstrip("/")
        self.timeout = timeout or OLLAMA_TIMEOUT

    def _url(self, path):
        return "%s%s" % (self.base_url, path)

    def is_available(self):
        """Verifica se a Ollama responde e tem modelos carregados."""
        try:
            result = _request(self._url("/api/tags"), timeout=self.timeout)
            models = [m.get("name") for m in result.get("models", [])]
            return bool(result.get("models")) and bool(models)
        except OllamaUnavailable as error:
            logger.warning("IA indisponivel: %s", error)
            return False
        except OllamaError as error:
            logger.warning("IA indisponivel: %s", error)
            return False

    def generate(self, prompt, system=None, model=None, timeout=None):
        """Gera texto com o modelo indicado (chat-completion sincrono)."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {"model": model or OLLAMA_MODEL, "messages": messages, "stream": False}
        url = self._url("/api/chat")
        try:
            response = _request(url, payload=payload, timeout=timeout or self.timeout)
        except OllamaTimeout as error:
            logger.warning("IA demorou demais (timeout %ss): %s", timeout or self.timeout, error)
            raise OllamaTimeout from error
        except OllamaError as error:
            logger.warning("IA falhou na geracao: %s", error)
            raise OllamaUnavailable from error
        message = response.get("message", {}) or {}
        return message.get("content", "")

    def transcribe(self, audio_path, model=None, timeout=None):
        """Transcreve um arquivo de audio (Whisper). Retorna o texto."""
        audio = str(Path(audio_path).resolve())
        url = self._url("/api/generate")
        boundary = "----iaboundary123"
        body = b""
        body += b"--" + boundary.encode() + b"\r\n"
        body += b'Content-Disposition: form-data; name="model"\r\n\r\n' + WHISPER_MODEL.encode() + b"\r\n"
        body += b'Content-Disposition: form-data; name="audio"; filename="input.mp3"\r\nContent-Type: audio/mpeg\r\n\r\n'
        body += Path(audio).read_bytes() + b"\r\n"
        body += b"--" + boundary.encode() + b"--\r\n"
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            raise OllamaError("HTTP %s na transcricao: %r" % (error.code, error.read()[:200]))
        except (urllib.error.URLError, TimeoutError) as error:
            raise OllamaTimeout(str(error)) from error
        try:
            result = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise OllamaError("resposta invalida do Whisper: %r" % raw[:200]) from error
        return str(result.get("content", result.get("text", ""))).strip()


def parse_reminder(raw_text):
    """Transforma o texto/JSON retornado pela IA em dict estruturado.

    Aceita:
      * JSON: {"titulo": ..., "data": ..., "hora": ..., "aviso_minutos": ...,
               "repeticao": ..., "fuso": ...}
      * Texto chave/valor: "Título: X", "Data: dd/mm/aaaa", "Hora: HH:MM", ...
    Retorna None se faltar titulo ou data/hora.
    """
    if not raw_text:
        return None
    if isinstance(raw_text, (dict, list)):
        record = dict(raw_text) if isinstance(raw_text, dict) else {}
    else:
        # Tentar interpretar como JSON puro
        try:
            parsed = json.loads(raw_text)
        except (json.JSONDecodeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            record = parsed
        else:
            record = {}
            low = raw_text.lower()
            for marker, key in (
                ("titulo:", "titulo"), ("data:", "data"), ("hora:", "hora"),
                ("aviso:", "aviso"), ("repeticao:", "repeticao"),
                ("fuso:", "fuso"),
            ):
                idx = low.find(marker)
                if idx != -1:
                    value = raw_text[idx + len(marker):].strip()
                    value = value.split("\n", 1)[0].strip()
                    record[key] = value
    if not record.get("titulo") or not record.get("data"):
        return None
    return record


def interpret(mensagem, audio_path=None):
    """Entrada do usuario -> dicionario de lembrete (ou lanca excecao)."""
    text = mensagem.strip()
    if audio_path:
        client = OllamaClient()
        text = client.transcribe(audio_path)
        logger.info("Audio transcrito: %r", text)
    if not text:
        raise OllamaError("nenhum texto/audio fornecido")
    # A IA devolve JSON com os campos estruturados
    client = OllamaClient()
    try:
        raw = client.generate(
            prompt="Extraia dos campos de um compromisso "
                   "em pt-br: titulo, data (dd/mm/aaaa), hora (HH:MM), "
                   "aviso_minutos, repeticao, fuso. Retorne APENAS JSON.\nTexto: %s"
            % text[:1500],
        )
        record = json.loads(raw)
    except json.JSONDecodeError:
        record = parse_reminder(raw)
    if not record or not record.get("titulo") or not record.get("data"):
        raise OllamaError("IA nao extraiu titulo/data essenciais")
    record.setdefault("aviso_minutos", 0)
    record.setdefault("repeticao", "")
    record.setdefault("fuso", "America/Sao_Paulo")
    if isinstance(record.get("aviso_minutos"), str) and record["aviso_minutos"].isdigit():
        record["aviso_minutos"] = int(record["aviso_minutos"])
    return record

