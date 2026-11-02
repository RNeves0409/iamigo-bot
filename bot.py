import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OWNER = int(os.environ["TELEGRAM_USER_ID"])
TZ = ZoneInfo("America/Sao_Paulo")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

db = sqlite3.connect("/var/lib/iamigo/agenda.db")
db.execute("PRAGMA journal_mode=WAL")
db.executescript("""
CREATE TABLE IF NOT EXISTS agenda (
    id INTEGER PRIMARY KEY,
    titulo TEXT NOT NULL,
    evento REAL NOT NULL,
    aviso REAL NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pendente',
    tentativas INTEGER NOT NULL DEFAULT 0,
    proxima REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS config (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
""")
db.commit()

class ApiError(Exception):
    def __init__(self, code=0, retry_after=0):
        self.code = code
        self.retry_after = retry_after

def api(method, **params):
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
    return api("sendMessage", chat_id=OWNER, text=text)

def format_date(timestamp):
    return datetime.fromtimestamp(timestamp, TZ).strftime("%d/%m/%Y às %H:%M")

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

def handle(message):
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
        with db:
            db.execute(
                "INSERT OR REPLACE INTO config VALUES ('rascunho', ?)", (draft,)
            )
        send(
            f"Confirma este compromisso?\n\n{title}\n"
            f"Compromisso: {format_date(when.timestamp())}\n"
            f"Aviso: {format_date(notice.timestamp())}\n"
            "Fuso: America/Sao_Paulo\n\n"
            "/confirmar para salvar ou /abandonar para descartar."
        )

    elif command == "/confirmar":
        row = db.execute(
            "SELECT valor FROM config WHERE chave='rascunho'"
        ).fetchone()
        if not row:
            send("Não há cadastro aguardando confirmação.")
            return
        draft = json.loads(row[0])
        if draft["aviso"] <= time.time():
            send("O horário do aviso já passou. Faça um novo cadastro.")
            return
        with db:
            cursor = db.execute(
                "INSERT INTO agenda (titulo, evento, aviso) VALUES (?, ?, ?)",
                (draft["titulo"], draft["evento"], draft["aviso"]),
            )
            db.execute("DELETE FROM config WHERE chave='rascunho'")
        send(f"Compromisso #{cursor.lastrowid} salvo!")

    elif command == "/abandonar":
        with db:
            db.execute("DELETE FROM config WHERE chave='rascunho'")
        send("Cadastro descartado.")

    elif command == "/agenda":
        rows = db.execute(
            "SELECT id, titulo, evento, estado FROM agenda "
            "WHERE estado!='cancelado' AND evento>=? ORDER BY evento LIMIT 30",
            (time.time(),),
        ).fetchall()
        send("\n\n".join(
            f"#{r[0]} — {r[1]}\n{format_date(r[2])}\nAviso: {r[3]}"
            for r in rows
        ) or "Nenhum compromisso futuro cadastrado.")

    elif command == "/cancelar":
        if not argument.isdigit():
            send("Use /cancelar seguido do número. Exemplo: /cancelar 3")
            return
        with db:
            cursor = db.execute(
                "UPDATE agenda SET estado='cancelado' "
                "WHERE id=? AND estado!='cancelado'", (int(argument),)
            )
        send("Compromisso cancelado." if cursor.rowcount else "Compromisso não encontrado.")

    else:
        send("Comando não reconhecido. Use /ajuda.")

def notifications():
    now = time.time()
    rows = db.execute(
        "SELECT id, titulo, evento, aviso, tentativas FROM agenda "
        "WHERE estado='pendente' AND aviso<=? AND proxima<=? "
        "ORDER BY aviso LIMIT 5", (now, now),
    ).fetchall()
    for ident, title, event, notice, attempts in rows:
        late = "\n⚠️ Aviso atrasado." if now - notice > 60 else ""
        try:
            send(f"🔔 Lembrete #{ident}: {title}\n{format_date(event)}{late}")
        except ApiError as error:
            delay = max(error.retry_after, min(3600, 15 * 2 ** min(attempts, 8)))
            with db:
                db.execute(
                    "UPDATE agenda SET tentativas=tentativas+1, proxima=? WHERE id=?",
                    (time.time() + delay, ident),
                )
            logging.warning("Falha no aviso %s; codigo=%s", ident, error.code)
        else:
            with db:
                db.execute("UPDATE agenda SET estado='enviado' WHERE id=?", (ident,))

row = db.execute("SELECT valor FROM config WHERE chave='offset'").fetchone()
offset = int(row[0]) if row else 0
logging.info("iAmigo iniciado")

while True:
    try:
        notifications()
        updates = api(
            "getUpdates", offset=offset, timeout=10,
            allowed_updates=json.dumps(["message"]),
        )
        for update in updates:
            # A resposta pode falhar depois de o compromisso já ter sido salvo.
            # Registramos o update para não repetir a alteração no banco.
            try:
                handle(update.get("message", {}))
            except ApiError as error:
                logging.warning("Falha na resposta; codigo=%s", error.code)
            offset = update["update_id"] + 1
            with db:
                db.execute(
                    "INSERT OR REPLACE INTO config VALUES ('offset', ?)",
                    (str(offset),),
                )
    except ApiError as error:
        logging.warning("Falha na API; codigo=%s", error.code)
        time.sleep(max(5, error.retry_after))
    except Exception as error:
        logging.error("Falha interna: %s", type(error).__name__)
        time.sleep(5)
