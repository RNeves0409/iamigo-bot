"""Ponto de entrada do bot."""

import json
import logging
import time

from db import connect, get_config_value, set_config_value
from api import ApiError, api
from services import notifications, handle

# Garante que o banco de dados exista (esquema criado na primeira conexão)
connect()

# Recupera o offset salvo
offset_str = get_config_value("offset")
offset = int(offset_str) if offset_str else 0

logging.info("iAmigo iniciado")

while True:
    try:
        notifications()
        updates = api(
            "getUpdates", offset=offset, timeout=10,
            allowed_updates=json.dumps(["message"]),
        )
        for update in updates:
            try:
                handle(update.get("message", {}))
            except ApiError as error:
                logging.warning("Falha na resposta; codigo=%s", error.code)
            offset = update["update_id"] + 1
            set_config_value("offset", str(offset))
    except ApiError as error:
        logging.warning("Falha na API; codigo=%s", error.code)
        time.sleep(max(5, error.retry_after))
    except Exception as error:
        logging.error("Falha interna: %s", type(error).__name__)
        time.sleep(5)
