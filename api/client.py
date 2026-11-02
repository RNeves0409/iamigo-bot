"""Cliente de comunicação com a API do Telegram."""

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OWNER = int(os.environ["TELEGRAM_USER_ID"])
TZ = ZoneInfo("America/Sao_Paulo")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


class ApiError(Exception):
    """Falha na comunicação com a API do Telegram."""

    def __init__(self, code=0, retry_after=0):
        self.code = code
        self.retry_after = retry_after
        super().__init__(f"APIError [{code}] retry_after={retry_after}")


def api(method, **params):
    """Envia uma requisição HTTP à API do Telegram."""
    encoded = urllib.parse.urlencode(params).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/{method}", data=encoded
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        try:
            data = json.loads(error.read())
        except Exception:
            raise ApiError(error.code) from None
    except Exception:
        raise ApiError() from None
    if not data.get("ok"):
        raise ApiError(
            data.get("error_code", 0),
            data.get("parameters", {}).get("retry_after", 0),
        )
    return data["result"]


def send(text):
    """Envia uma mensagem de texto ao usuário dono do bot."""
    return api("sendMessage", chat_id=OWNER, text=text)
