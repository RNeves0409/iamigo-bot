"""Lógica de negócio do bot."""

import json
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from api.client import OWNER, send, api
from db.connection import connect, get_config_value, set_config_value

TZ = ZoneInfo("America/Sao_Paulo")


HELP = """Olá, Renato! Sou o iAmigo.

Criar compromisso:
/novo Dentista | 05/11/2026 14:00 | 60

O último número é a antecedência do aviso em minutos.
Antes de salvar, vou pedir confirmação.

/confirmar — salvar o cadastro apresentado
/abandonar — descartar o cadastro
/agenda — próximos compromissos
/cancelar 3 — cancelar o compromisso de número 3
/ajuda — mostrar estas instruções

Horário: America/Sao_Paulo.
"""


def format_date(timestamp):
    return datetime.fromtimestamp(timestamp, TZ).strftime("%d/%m/%Y às %H:%M")


def handle(message):
    """Processa uma mensagem do Telegram (única entrada de comandos)."""
    if message.get("from", {}).get("id") != OWNER:
        return
    if message.get("chat", {}).get("type") != "private":
        return
    text = message.get("text", "").strip()
    if not text:
        return

    parts = text.split(maxsplit=1)
    command = parts[0].split("@")[0].lower()
    argument = parts[1] if len(parts) > 1 else ""

    if command in ("/start", "/ajuda"):
        send(HELP)

    elif command == "/novo":
        try:
            title, date, minutes = [p.strip() for p in argument.split("|")]
            when = datetime.strptime(date, "%d/%m/%Y %H:%M").replace(tzinfo=TZ)
            advance = int(minutes)
            notice = when - timedelta(minutes=advance)
            if not title or len(title) > 200 or advance < 0:
                raise ValueError()
            if notice.timestamp() <= time.time():
                send("O horário do aviso precisa estar no futuro. Ajuste a data ou a antecedência.")
                return
        except (ValueError, OverflowError):
            send("Use: /novo Dentista | 05/11/2026 14:00 | 60")
            return

        draft = json.dumps({
            "titulo": title, "evento": when.timestamp(),
            "aviso": notice.timestamp(),
        })
        db = connect()
        try:
            set_config_value("rascunho", draft)
            db.commit()
        finally:
            db.close()

        send(
            f"Confirma este compromisso?\n\n{title}\n"
            f"Compromisso: {format_date(when.timestamp())}\n"
            f"Aviso: {format_date(notice.timestamp())}\n"
            "Fuso: America/Sao_Paulo\n\n"
            "/confirmar para salvar ou /abandonar para descartar."
        )

    elif command == "/confirmar":
        db = connect()
        try:
            row = db.execute("SELECT valor FROM config WHERE chave='rascunho'").fetchone()
            if not row:
                send("Não há cadastro aguardando confirmação.")
                return
            draft = json.loads(row[0])
            if draft["aviso"] <= time.time():
                send("O horário do aviso já passou. Faça um novo cadastro.")
                return
            cursor = db.execute(
                "INSERT INTO agenda (titulo, evento, aviso) VALUES (?, ?, ?)",
                (draft["titulo"], draft["evento"], draft["aviso"]),
            )
            db.execute("DELETE FROM config WHERE chave='rascunho'")
            db.commit()
        finally:
            db.close()
        send(f"Compromisso #{cursor.lastrowid} salvo!")

    elif command == "/abandonar":
        db = connect()
        try:
            db.execute("DELETE FROM config WHERE chave='rascunho'")
            db.commit()
        finally:
            db.close()
        send("Cadastro descartado.")

    elif command == "/agenda":
        db = connect()
        try:
            rows = db.execute(
                "SELECT id, titulo, evento, estado FROM agenda "
                "WHERE estado!='cancelado' AND evento>? ORDER BY evento LIMIT 30",
                (time.time(),),
            ).fetchall()
        finally:
            db.close()
        send("\n\n".join(
            f"#{r[0]} — {r[1]}\n{format_date(r[2])}\nAviso: {r[3]}"
            for r in rows
        ) or "Nenhum compromisso futuro cadastrado.")

    elif command == "/cancelar":
        if not argument.isdigit():
            send("Use /cancelar seguido do número. Exemplo: /cancelar 3")
            return
        db = connect()
        try:
            cursor = db.execute(
                "UPDATE agenda SET estado='cancelado' "
                "WHERE id=? AND estado!='cancelado'", (int(argument),)
            )
            db.commit()
        finally:
            db.close()
        send("Compromisso cancelado." if cursor.rowcount else "Compromisso não encontrado.")

    else:
        send("Comando não reconhecido. Use /ajuda.")


def notifications():
    """Verifica e envia lembretes que devem ser enviados agora."""
    db = connect()
    try:
        rows = db.execute(
            "SELECT id, titulo, evento, aviso, tentativas FROM agenda "
            "WHERE estado='pendente' AND aviso<=? AND proxima<=? "
            "ORDER BY aviso LIMIT 5", (time.time(), time.time())
        ).fetchall()
    finally:
        db.close()

    for ident, title, event, notice, attempts in rows:
        late = "\n⚠️ Aviso atrasado." if time.time() - notice > 60 else ""
        try:
            send(f"🔔 Lembrete #{ident}: {title}\n{format_date(event)}{late}")
        except api.client.ApiError as error:
            delay = max(error.retry_after, min(3600, 15 * 2 ** min(attempts, 8)))
            db = connect()
            try:
                db.execute(
                    "UPDATE agenda SET tentativas=tentativas+1, proxima=? WHERE id=?",
                    (time.time() + delay, ident),
                )
                db.commit()
            finally:
                db.close()
            logging.warning("Falha no aviso %s; codigo=%s", ident, error.code)
        else:
            db = connect()
            try:
                db.execute("UPDATE agenda SET estado='enviado' WHERE id=?", (ident,))
                db.commit()
            finally:
                db.close()
