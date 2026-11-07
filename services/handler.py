"""Lógica de negócio do bot.

Fase 3 — Fluxo com IA local (Ollama) + caminho legado.

Roteamento de mensagens (entrada: objeto `message` do Telegram):
  * Mensagem de grupo ou de outro usuário      -> descartada.
  * Comando legado (/start, /ajuda, /novo,     -> caminho LEGADO, inalterado.
    /confirmar, /abandonar, /agenda, /cancelar)
  * Texto livre (sem "/")                      -> caminho DA IA (Opção A):
      texto -> services.ai.interpret() ->
      salva no banco de dados AGORA -> confirma ao usuário.

Regra central (Opção A):
  * A IA salva o lembrete diretamente.
  * Só pergunta (esclarecimento) se a IA estiver em dúvida sobre dados essenciais.
  * Se a IA estiver OFF ou não extrair título/data, o bot entra no MODO LEGADO
    (/novo | dd/mm/aaaa HH:MM | antecedência) — o /novo só é usado nessa falha.

Banco de dados: sem alterações estruturais. O salvo direto insere na tabela
agenda (mesma coluna `estado='pendente'` usada pelo caminho legado). O rascunho
da IA é convertido para horário do banco imediatamente.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from api.client import ApiError, OWNER, TOKEN, api, send
from db.connection import connect, set_config_value
from services import ai
from services.ai import OllamaError, OllamaTimeout, OllamaUnavailable

import os
import tempfile
import urllib.request

logger = logging.getLogger(__name__)

TZ = ZoneInfo("America/Sao_Paulo")

# ---------------------------------------------------------------------------
# Ajuda (texto exibido nos comandos /start e /ajuda)
# ---------------------------------------------------------------------------
HELP = """Olá, Renato! Sou o iAmigo.

Duas formas de cadastrar compromissos:

1) MODO DIRETO (recomendado): escreva o compromisso normalmente e a IA
   salva sozinho. Ex.:
     Consulta com o dentista | 05/11/2026 14:00 | aviso de 60 minutos
   Se a IA não tiver certeza, ela pergunta antes de salvar.

2) MODO LEGADO (se a IA estiver fora do ar ou não entender):
     /novo Título | dd/mm/aaaa HH:MM | antecedência em minutos
   Ex.: /novo Consulta | 05/11/2026 14:00 | 60

Comandos legados (sempre disponíveis):
  /novo — começar um cadastro manual
  /confirmar — salvar o cadastro aguardando
  /abandonar — descartar o cadastro
  /agenda — próximos compromissos
  /cancelar 3 — cancelar o compromisso de número 3
  /ajuda — esta mensagem

Horário: America/Sao_Paulo.
"""

# ---------------------------------------------------------------------------
# Aidas de conversão e persistência
# ---------------------------------------------------------------------------


def format_date(timestamp):
    return datetime.fromtimestamp(timestamp, TZ).strftime("%d/%m/%Y às %H:%M")


def _parse_datetime(data, hora):
    """Converte 'dd/mm/aaaa' + 'HH:MM' em um datetime (America/Sao_Paulo)."""
    return datetime.strptime(f"{data} {hora}", "%d/%m/%Y %H:%M").replace(
        tzinfo=TZ
    )


def _to_epoch(timestamp_dt):
    return timestamp_dt.timestamp()


def _reminder_event_epoch(record):
    """evento = data + hora convertidos para timestamp (epoch)."""
    return _to_epoch(_parse_datetime(record["data"], record["hora"]))


def _event_dt(record):
    """Converte 'dd/mm/aaaa' + 'HH:MM' em datetime (America/Sao_Paulo)."""
    return datetime.strptime(f"{record['data']} {record['hora']}", "%d/%m/%Y %H:%M").replace(
        tzinfo=TZ
    )


def _save_reminder(record):
    """Insere o lembrete retornado pela IA na tabela agenda.

    Retorna o id do registro inserido.
    """
    evento = _event_dt(record)
    aviso = evento - timedelta(minutes=record.get("aviso_minutos", 0))
    db = connect()
    try:
        cursor = db.execute(
            "INSERT INTO agenda (titulo, evento, aviso, estado) VALUES (?, ?, ?, ?)",
            (record["titulo"], _to_epoch(evento), _to_epoch(aviso), "pendente"),
        )
        db.commit()
        return cursor.lastrowid
    finally:
        db.close()


def _confirmation_text(record):
    """Mensagem de confirmação enviada ao usuário depois do salvamento."""
    evento = _event_dt(record)
    aviso = evento - timedelta(minutes=record.get("aviso_minutos", 0))
    evento_str = format_date(_to_epoch(evento))
    aviso_str = format_date(_to_epoch(aviso))
    lines = [
        "✅ Lembrete salvo",
        f"📌 Título: {record['titulo']}",
        f"📅 Compromisso: {evento_str}",
        f"⚠️ Aviso: {aviso_str}",
    ]
    if record.get("repeticao"):
        lines.append(f"🔁 Repetição: {record['repeticao']}")
    if record.get("fuso") and record["fuso"] != "America/Sao_Paulo":
        lines.append(f"🌐 Fuso: {record['fuso']}")
    return "\n".join(lines)


def _fallback_legacy(text):
    """Mensagem de transição para o modo legado quando a IA não entende."""
    first = text.split(maxsplit=1)
    example = first[1][:40] if len(first) > 1 else ""
    return (
        "Não entendi (ou a IA está indisponível). Pode usar o modo legado\n"
        "do iAmigo para continuar:\n\n"
        "/novo Título | dd/mm/aaaa HH:MM | antecedência em minutos\n"
        f"Exemplo: /novo {example}\n\n"
        "Use /ajuda para os demais comandos."
    )


# ---------------------------------------------------------------------------
# Roteamento
# ---------------------------------------------------------------------------


def _route_legacy(text):
    """Comando legado: mesmo comportamento do bot anterior (Fase 2)."""
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
                send(
                    "O horário do aviso precisa estar no futuro. "
                    "Ajuste a data ou a antecedência."
                )
                return
        except (ValueError, OverflowError):
            send("Use: /novo Dentista | 05/11/2026 14:00 | 60")
            return

        draft = json.dumps(
            {"titulo": title, "evento": when.timestamp(), "aviso": notice.timestamp()}
        )
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
                "WHERE id=? AND estado!='cancelado'",
                (int(argument),),
            )
            db.commit()
        finally:
            db.close()
        send("Compromisso cancelado." if cursor.rowcount else "Compromisso não encontrado.")

    else:
        send("Comando não reconhecido. Use /ajuda.")


def _run_ai_flow(text):
    """Executa o caminho da IA: interpreta, salva e confirma (Opção A).

    Retorna True se o lembrete foi salvo; False se entrou no modo legado.
    """
    try:
        record = ai.interpret(text)
    except (OllamaUnavailable, OllamaTimeout, OllamaError) as error:
        # IA fora do ar / sem modelo / extraiu nada essencial → modo legado
        logger.warning("Caminho da IA não pode prosseguir: %s", error)
        return False
    except Exception:  # segurança: não travar o loop de getUpdates
        logger.exception("Erro inesperado ao interpretar o texto")
        return False

    try:
        _save_reminder(record)
    except Exception:
        logger.exception("Falha ao salvar o lembrete interpretado pela IA")
        return False

    send(_confirmation_text(record))
    return True


def _route_direct(text):
    """Texto livre: a IA interpreta e salva (opção A); se não, modo legado."""
    if not _run_ai_flow(text):
        send(_fallback_legacy(text))


# ---------------------------------------------------------------------------
# Caminho de áudio: voz/audio/documentos → STT (Whisper) → IA → salva
# ---------------------------------------------------------------------------


def _extract_file_id(message):
    """Recupera o file_id de voz/audio/documento de áudio de uma mensagem."""
    for key in ("voice", "audio"):
        value = message.get(key)
        if value and "file_id" in value:
            return value["file_id"]
    document = message.get("document")
    if document and "file_id" in document:
        return document["file_id"]
    return None


def _download_file(file_path):
    """Baixa um arquivo de áudio do Telegram e retorna os bytes."""
    url = "https://api.telegram.org/file/bot%s/%s" % (TOKEN, file_path)
    with urllib.request.urlopen(url, timeout=25) as response:
        return response.read()


def _route_audio(message):
    """Caminho de áudio: voz/audio/documentos → STT (Whisper) → IA → salva."""
    file_id = _extract_file_id(message)
    if not file_id:
        return

    try:
        info = api("getFile", file_id=file_id)
    except ApiError as error:
        logger.warning("Falha no getFile do áudio: %s", error)
        send(_fallback_legacy("[som] Não consegui acessar o áudio. Use /novo ..."))
        return

    file_path = info.get("file_path")
    if not file_path:
        logger.warning("getFile retornou sem file_path")
        send(_fallback_legacy("[som] Arquivo não encontrado. Use /novo ..."))
        return

    try:
        raw = _download_file(file_path)
    except Exception:
        logger.exception("Falha ao baixar áudio do Telegram")
        send(_fallback_legacy("[som] Não consegui baixar o áudio. Use /novo ..."))
        return

    audio_path = os.path.join(
        tempfile.gettempdir(), "iamigo_audio_%d.ogg" % time.time_ns()
    )
    try:
        with open(audio_path, "wb") as handle:
            handle.write(raw)
        try:
            client = ai.OllamaClient()
            text = client.transcribe(audio_path)
        except (OllamaTimeout, OllamaError) as error:
            logger.warning("Transcrição de áudio falhou: %s", error)
            send(_fallback_legacy("[som] Não consegui transcrever o áudio. Use /novo ..."))
            return
        if not _run_ai_flow(text):
            return
    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass


def handle(message):
    """Processa uma mensagem do Telegram (única entrada de comandos)."""
    if message.get("from", {}).get("id") != OWNER:
        return
    if message.get("chat", {}).get("type") != "private":
        return
    text = message.get("text", "").strip()

    # Áudio/voz/documento: STT → IA (mesmo roteiro do texto livre)
    if message.get("voice") or message.get("audio") or message.get("document"):
        _route_audio(message)
    elif text:
        # Comando legado ou texto livre interpretado pela IA
        if text.startswith("/"):
            _route_legacy(text)
        else:
            _route_direct(text)


def notifications():
    """Verifica e envia lembretes que devem ser enviados agora.

    Fluído legado (Fase 2): avisos atrasados e retentativas com backoff.
    Mantido intocado — não é parte do fluxo com IA do Novo.
    """
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
        except ApiError as error:
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



