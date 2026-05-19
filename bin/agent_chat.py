#!/usr/bin/env python3
"""Cross-session messaging over Redis for Claude Code sessions."""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

import click
import redis

REDIS_HOST = os.environ.get("CLAUDE_CHAT_REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("CLAUDE_CHAT_REDIS_PORT", "6380"))

REGISTRY_KEY = "agents:registry"
REQUESTS_KEY = "agent:{name}:requests"
REPLIES_KEY = "agent:{name}:replies:{rid}"
PENDING_KEY = "agent:{name}:pending"  # HASH rid -> JSON of the original ask

REPLY_TTL = 3600  # reply slot TTL — sized for late answers to long Q&A
PENDING_TTL = 86400  # pending-ask metadata TTL — 24h is plenty for catch-up
MAX_MSG_BYTES = 16 * 1024

# Identity is stored per-cwd so each session in a different project has its own name.
STATE_DIR = Path.home() / ".claude_chat"
STATE_DIR.mkdir(exist_ok=True)


def _state_file() -> Path:
    cwd_slug = str(Path.cwd()).replace("/", "_").lstrip("_")
    return STATE_DIR / f"{cwd_slug}.json"


def _load_identity() -> dict | None:
    f = _state_file()
    if not f.exists():
        return None
    return json.loads(f.read_text())


def _save_identity(name: str, description: str) -> None:
    _state_file().write_text(json.dumps({"name": name, "description": description}))


def _clear_identity() -> None:
    f = _state_file()
    if f.exists():
        f.unlink()


def _r() -> redis.Redis:
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


def _die_if_unreachable(r: redis.Redis) -> None:
    try:
        r.ping()
    except redis.ConnectionError:
        click.echo(
            f"error: cannot reach Redis at {REDIS_HOST}:{REDIS_PORT}.\n"
            "Start it from the claude-chat plugin directory:  docker compose up -d",
            err=True,
        )
        sys.exit(3)


def _check_size(text: str, label: str) -> None:
    if len(text.encode("utf-8")) > MAX_MSG_BYTES:
        click.echo(f"error: {label} exceeds {MAX_MSG_BYTES} bytes", err=True)
        sys.exit(2)


@click.group()
def cli() -> None:
    pass


@cli.command()
@click.argument("name", required=False)
@click.argument("description", required=False)
def register(name: str | None, description: str | None) -> None:
    """Register this session. NAME defaults to the cwd basename; DESCRIPTION to a placeholder."""
    if not name:
        name = Path.cwd().name or "agent"
        name = name.replace(" ", "_")
    if not description:
        description = f"agent in {Path.cwd()}"
    r = _r()
    _die_if_unreachable(r)
    existing = r.hget(REGISTRY_KEY, name)
    if existing:
        existing_data = json.loads(existing)
        if existing_data.get("project_dir") != str(Path.cwd()):
            click.echo(
                f"error: agent '{name}' already registered for {existing_data.get('project_dir')}. "
                f"Pick a different name or run unregister there first.",
                err=True,
            )
            sys.exit(2)

    entry = {
        "name": name,
        "description": description,
        "project_dir": str(Path.cwd()),
        "pid": os.getpid(),
        "registered_at": int(time.time()),
    }
    r.hset(REGISTRY_KEY, name, json.dumps(entry))
    _save_identity(name, description)
    click.echo(f"registered '{name}' ({description})")


@cli.command(name="list")
def list_agents() -> None:
    """List all registered agents."""
    r = _r()
    _die_if_unreachable(r)
    entries = r.hgetall(REGISTRY_KEY)
    if not entries:
        click.echo("(no agents registered)")
        return
    me = _load_identity()
    my_name = me["name"] if me else None
    for name, raw in sorted(entries.items()):
        data = json.loads(raw)
        marker = " (you)" if name == my_name else ""
        click.echo(f"  {name}{marker}: {data['description']}")
        click.echo(f"      dir: {data['project_dir']}")


def _send(target: str, body: str, kind: str) -> tuple[redis.Redis, str, str]:
    """Push a message to target's inbox. Returns (redis, request_id, me_name)."""
    _check_size(body, kind)
    r = _r()
    _die_if_unreachable(r)

    me = _load_identity()
    if not me:
        click.echo("error: not registered. Run `agent_chat.py register` first.", err=True)
        sys.exit(2)

    if not r.hexists(REGISTRY_KEY, target):
        click.echo(f"error: no agent named '{target}'. Run `list` to see registered agents.", err=True)
        sys.exit(2)

    rid = uuid.uuid4().hex
    msg = {
        "request_id": rid,
        "kind": kind,
        "from": me["name"],
        "from_dir": str(Path.cwd()),
        "body": body,
        "sent_at": int(time.time()),
    }
    r.rpush(REQUESTS_KEY.format(name=target), json.dumps(msg))
    r.expire(REQUESTS_KEY.format(name=target), REPLY_TTL)
    return r, rid, me["name"]


@cli.command()
@click.argument("target")
@click.argument("question")
def ask(target: str, question: str) -> None:
    """Ask TARGET a QUESTION. Blocks indefinitely until they answer.

    To cancel, interrupt the call (Esc in Claude Code). If TARGET answers after
    you cancel, the answer is queued and surfaces on your next `check`."""
    r, rid, me_name = _send(target, question, "question")
    reply_key = REPLIES_KEY.format(name=me_name, rid=rid)
    pending_key = PENDING_KEY.format(name=me_name)

    # Record the ask so a late answer (after cancel) can be matched in `check`.
    r.hset(pending_key, rid, json.dumps({"target": target, "question": question, "sent_at": int(time.time())}))
    r.expire(pending_key, PENDING_TTL)

    click.echo(f"asked '{target}', request_id={rid}, waiting (cancel with Esc)...", err=True)
    # BLPOP timeout=0 blocks indefinitely until something is pushed.
    result = r.blpop(reply_key, timeout=0)
    if result is None:
        # Shouldn't happen with timeout=0 unless connection drops mid-call.
        click.echo("error: connection ended without reply", err=True)
        sys.exit(1)

    _, payload = result
    reply = json.loads(payload)
    r.hdel(pending_key, rid)
    click.echo(reply["body"])


@cli.command()
@click.argument("target")
@click.argument("message")
def tell(target: str, message: str) -> None:
    """Tell TARGET a MESSAGE. Fire-and-forget: returns immediately, no reply expected."""
    _, rid, _ = _send(target, message, "tell")
    click.echo(f"told '{target}', request_id={rid}", err=True)


def _drain_late_answers(r: redis.Redis, me_name: str) -> list[dict]:
    """For each pending ask, see if an answer has landed on its reply slot. Drain and return."""
    pending_key = PENDING_KEY.format(name=me_name)
    pending = r.hgetall(pending_key)
    if not pending:
        return []
    drained = []
    for rid, raw_meta in pending.items():
        meta = json.loads(raw_meta)
        reply_key = REPLIES_KEY.format(name=me_name, rid=rid)
        # Non-blocking pop. If the slot has a reply, take it; otherwise leave the pending entry.
        payload = r.lpop(reply_key)
        if payload is None:
            continue
        reply = json.loads(payload)
        drained.append({
            "request_id": rid,
            "target": meta["target"],
            "question": meta["question"],
            "from": reply.get("from", meta["target"]),
            "answer": reply.get("body", ""),
            "sent_at": meta.get("sent_at"),
        })
        r.hdel(pending_key, rid)
    return drained


@cli.command()
def check() -> None:
    """Show pending inbox items and any late answers for this agent (does not block)."""
    me = _load_identity()
    if not me:
        click.echo("error: not registered.", err=True)
        sys.exit(2)
    r = _r()
    _die_if_unreachable(r)

    inbox_key = REQUESTS_KEY.format(name=me["name"])
    items = r.lrange(inbox_key, 0, -1)
    if items:
        r.delete(inbox_key)

    late_answers = _drain_late_answers(r, me["name"])

    if not items and not late_answers:
        click.echo("(inbox empty)")
        return

    for raw in items:
        msg = json.loads(raw)
        kind = msg.get("kind", "question")
        body = msg.get("body") or msg.get("question") or ""
        click.echo(f"--- {kind} request_id: {msg['request_id']}")
        click.echo(f"from: {msg['from']} ({msg.get('from_dir', '?')})")
        click.echo(f"{kind}: {body}")
        click.echo("")

    for la in late_answers:
        click.echo(f"--- late_answer request_id: {la['request_id']}")
        click.echo(f"from: {la['from']} (answer to a question you asked earlier)")
        click.echo(f"original question: {la['question']}")
        click.echo(f"answer: {la['answer']}")
        click.echo("")

    click.echo(
        "For each item:\n"
        "  - question     -> answer it now:  agent_chat.py answer <request_id> <from_agent> \"<answer>\"\n"
        "  - tell         -> nothing to send. Surface the message to the user; act only if they say so.\n"
        "  - late_answer  -> nothing to send. Use the answer to continue the original task,\n"
        "                    or surface it to the user if the original ask has already been abandoned.",
        err=True,
    )


@cli.command()
@click.argument("request_id")
@click.argument("from_agent")
@click.argument("answer")
def answer(request_id: str, from_agent: str, answer: str) -> None:
    """Send ANSWER for a question REQUEST_ID back to FROM_AGENT."""
    _check_size(answer, "answer")
    me = _load_identity()
    if not me:
        click.echo("error: not registered.", err=True)
        sys.exit(2)
    r = _r()
    _die_if_unreachable(r)
    reply_key = REPLIES_KEY.format(name=from_agent, rid=request_id)
    payload = {
        "request_id": request_id,
        "kind": "answer",
        "from": me["name"],
        "body": answer,
        "sent_at": int(time.time()),
    }
    r.rpush(reply_key, json.dumps(payload))
    r.expire(reply_key, REPLY_TTL)
    click.echo(f"sent answer for {request_id} -> {from_agent}")


@cli.command()
def unregister() -> None:
    """Unregister this session."""
    me = _load_identity()
    if not me:
        click.echo("(not registered)")
        return
    r = _r()
    _die_if_unreachable(r)
    r.hdel(REGISTRY_KEY, me["name"])
    r.delete(REQUESTS_KEY.format(name=me["name"]))
    r.delete(PENDING_KEY.format(name=me["name"]))
    _clear_identity()
    click.echo(f"unregistered '{me['name']}'")


@cli.command()
def whoami() -> None:
    """Print this session's registered identity."""
    me = _load_identity()
    if not me:
        click.echo("(not registered)")
        return
    click.echo(f"{me['name']}: {me['description']}")


if __name__ == "__main__":
    cli()
