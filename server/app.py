"""GPlanSiS|Studio — servidor de acesso.

Entrega o editor só para quem tem sessão válida, guarda usuários, permissões,
avatar, preferências e projetos na nuvem. O editor continua rodando inteiro no
navegador; o servidor não processa imagem.

Variáveis (arquivo .env):
  STUDIO_DATA            pasta de dados (banco SQLite e projetos)   [./dados]
  STUDIO_WEB             pasta dos estáticos gerados pelo build      [../dist/web]
  STUDIO_MASTER_EMAIL    e-mail do administrador master              [contato@gplansis.com]
  STUDIO_MASTER_PASSWORD senha inicial do master (só no primeiro arranque;
                         sem ela, uma senha aleatória é gravada em
                         STUDIO_DATA/senha-inicial-master.txt)
  STUDIO_COOKIE_SECURE   1 em produção (HTTPS), 0 em teste local       [1]
  STUDIO_ANTHROPIC_API_KEY  chave da Anthropic para as funções de IA (server/ai.py).
                         Opcional: o admin também pode gravá-la em Configurações › IA.
                         Sem chave, a IA fica desligada e o resto funciona normalmente.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("STUDIO_DATA", BASE / "dados")).resolve()
WEB = Path(os.environ.get("STUDIO_WEB", BASE.parent / "dist" / "web")).resolve()
MASTER_EMAIL = os.environ.get("STUDIO_MASTER_EMAIL", "contato@gplansis.com").strip().lower()
COOKIE = "gps_studio"
COOKIE_SECURE = os.environ.get("STUDIO_COOKIE_SECURE", "1") == "1"
SESSION_DAYS = 30
MAX_PROJECT = 200 * 1024 * 1024
MAX_AVATAR = 400 * 1024
PROJECTS = DATA / "projetos"

MODULES = ["pixel", "vetor", "foto", "ponte"]
# Permissões granulares. O papel dá o padrão; o admin pode ajustar por pessoa.
PERMS = MODULES + ["exportar", "nuvem", "ia", "usuarios", "auditoria"]
ROLE_DEFAULTS = {
    "master": {p: True for p in PERMS},
    "admin": {p: True for p in PERMS},
    "editor": {**{p: True for p in MODULES}, "exportar": True, "nuvem": True, "ia": True, "usuarios": False, "auditoria": False},
    "visualizador": {**{p: True for p in MODULES}, "exportar": False, "nuvem": False, "ia": False, "usuarios": False, "auditoria": False},
}
ROLES = ["admin", "editor", "visualizador"]  # o master não é atribuível
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

DATA.mkdir(parents=True, exist_ok=True)
PROJECTS.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA / "studio.db"
_lock = threading.Lock()


# ---------------------------------------------------------------- banco
def _connect() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


@contextmanager
def db():
    c = _connect()
    try:
        yield c
    finally:
        c.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  pw TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('master','admin','editor','visualizador')),
  perms TEXT NOT NULL DEFAULT '{}',
  prefs TEXT NOT NULL DEFAULT '{}',
  avatar BLOB,
  avatar_type TEXT,
  avatar_v INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1,
  must_change INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL,
  last_login REAL
);
-- só pode existir um master, e ele não pode ser desativado
CREATE UNIQUE INDEX IF NOT EXISTS one_master ON users(role) WHERE role='master';
CREATE TABLE IF NOT EXISTS sessions(
  token TEXT PRIMARY KEY,           -- sha256 do token; o token em si só existe no cookie
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at REAL NOT NULL,
  seen_at REAL NOT NULL,
  expires_at REAL NOT NULL,
  ua TEXT, ip TEXT
);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY,
  ts REAL NOT NULL,
  actor INTEGER, actor_email TEXT,
  action TEXT NOT NULL,
  target TEXT, detail TEXT, ip TEXT
);
CREATE TABLE IF NOT EXISTS projects(
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  size INTEGER NOT NULL,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  UNIQUE(user_id, name)
);
"""


def hash_pw(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$16384$8$1$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(h).decode()


def check_pw(pw: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, h = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(got, base64.b64decode(h))
    except (ValueError, binascii.Error):
        return False


# Hash fixo para comparar quando o e-mail não existe: o tempo de resposta não
# revela quais e-mails têm conta.
_DUMMY = hash_pw(secrets.token_urlsafe(12))


def init_db() -> None:
    with db() as c:
        c.executescript(SCHEMA)
        row = c.execute("SELECT id, email FROM users WHERE role='master'").fetchone()
        if row is None:
            existing = c.execute("SELECT id FROM users WHERE email=?", (MASTER_EMAIL,)).fetchone()
            pw = os.environ.get("STUDIO_MASTER_PASSWORD") or ""
            note = None
            if not pw:
                pw = secrets.token_urlsafe(12)
                note = DATA / "senha-inicial-master.txt"
            if existing:
                c.execute("UPDATE users SET role='master', active=1 WHERE id=?", (existing["id"],))
            else:
                c.execute(
                    "INSERT INTO users(email,name,pw,role,must_change,created_at) VALUES(?,?,?,?,1,?)",
                    (MASTER_EMAIL, "Administrador", hash_pw(pw), "master", time.time()),
                )
                if note:
                    note.write_text(
                        f"Login: {MASTER_EMAIL}\nSenha inicial: {pw}\n"
                        "Troque no primeiro acesso (o sistema exige) e apague este arquivo.\n"
                    )
                    os.chmod(note, 0o600)
            audit(c, None, "sistema.master_criado", MASTER_EMAIL)
        elif row["email"] != MASTER_EMAIL:
            # O master é definido pelo .env; trocar o e-mail lá transfere o posto.
            c.execute("UPDATE users SET role='admin' WHERE id=?", (row["id"],))
            ex = c.execute("SELECT id FROM users WHERE email=?", (MASTER_EMAIL,)).fetchone()
            if ex:
                c.execute("UPDATE users SET role='master', active=1 WHERE id=?", (ex["id"],))
                audit(c, None, "sistema.master_transferido", MASTER_EMAIL)
            else:
                c.execute("UPDATE users SET role='master' WHERE id=?", (row["id"],))
        c.execute("DELETE FROM sessions WHERE expires_at<?", (time.time(),))


def audit(c: sqlite3.Connection, user: dict | None, action: str, target: str = "", detail: Any = None, ip: str = "") -> None:
    c.execute(
        "INSERT INTO audit(ts,actor,actor_email,action,target,detail,ip) VALUES(?,?,?,?,?,?,?)",
        (time.time(), user and user["id"], user and user["email"], action, target,
         json.dumps(detail, ensure_ascii=False) if detail is not None else None, ip),
    )


def eff_perms(u: sqlite3.Row | dict) -> dict:
    base = dict(ROLE_DEFAULTS[u["role"]])
    if u["role"] != "master":
        try:
            over = json.loads(u["perms"] or "{}")
        except ValueError:
            over = {}
        for k, v in over.items():
            if k in base:
                base[k] = bool(v)
    return base


def public_user(u: sqlite3.Row, full: bool = False) -> dict:
    d = {
        "id": u["id"], "email": u["email"], "name": u["name"], "role": u["role"],
        "perms": eff_perms(u), "avatar": f"/api/avatar/{u['id']}?v={u['avatar_v']}" if u["avatar"] else None,
        "active": bool(u["active"]), "must_change": bool(u["must_change"]),
        "created_at": u["created_at"], "last_login": u["last_login"],
        "ai_quota": u["ai_quota"] if "ai_quota" in u.keys() else None,
    }
    if full:
        try:
            d["prefs"] = json.loads(u["prefs"] or "{}")
        except ValueError:
            d["prefs"] = {}
        try:
            d["overrides"] = json.loads(u["perms"] or "{}")
        except ValueError:
            d["overrides"] = {}
    return d


# ---------------------------------------------------------------- tentativa de login
_fails: dict[str, list[float]] = {}
FAIL_WINDOW, FAIL_MAX = 15 * 60, 8


def _throttled(key: str) -> bool:
    now = time.time()
    lst = [t for t in _fails.get(key, []) if now - t < FAIL_WINDOW]
    _fails[key] = lst
    return len(lst) >= FAIL_MAX


def _fail(key: str) -> None:
    _fails.setdefault(key, []).append(time.time())


# ---------------------------------------------------------------- app
# 'wasm-unsafe-eval': decodificador JPEG XL em WebAssembly; blob: em worker-src: libheif.
# O Caddy (embed_os) reescreve o frame-ancestors para liberar o os.gplansis.com.
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; worker-src 'self' blob:; "
       "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; "
       "connect-src 'self' data: blob:; object-src 'none'; base-uri 'none'; form-action 'self'; "
       "frame-ancestors 'self' https://os.gplansis.com")
app = FastAPI(title="GPlanSiS|Studio", docs_url=None, redoc_url=None, openapi_url=None)
init_db()


def client_ip(req: Request) -> str:
    return (req.headers.get("x-forwarded-for") or (req.client.host if req.client else "")).split(",")[0].strip()


def current(req: Request) -> dict | None:
    tok = req.cookies.get(COOKIE)
    if not tok:
        return None
    th = hashlib.sha256(tok.encode()).hexdigest()
    now = time.time()
    with db() as c:
        row = c.execute(
            "SELECT u.*, s.token AS sid, s.seen_at FROM sessions s JOIN users u ON u.id=s.user_id "
            "WHERE s.token=? AND s.expires_at>? AND u.active=1", (th, now)).fetchone()
        if not row:
            return None
        if now - row["seen_at"] > 300:
            c.execute("UPDATE sessions SET seen_at=? WHERE token=?", (now, th))
    return dict(row)


def need(req: Request, perm: str | None = None) -> dict:
    u = current(req)
    if not u:
        raise HTTPException(401, "Sessão expirada. Entre novamente.")
    if perm and not eff_perms(u).get(perm):
        raise HTTPException(403, "Seu usuário não tem permissão para isso.")
    return u


@app.middleware("http")
async def guard(req: Request, call_next):
    # CSRF: o cookie é SameSite=Lax e toda escrita na API exige o cabeçalho
    # próprio, que um formulário de outro site não consegue mandar.
    if req.url.path.startswith("/api/") and req.method not in ("GET", "HEAD", "OPTIONS"):
        if req.headers.get("x-studio") != "1":
            return JSONResponse({"detail": "Requisição recusada."}, status_code=403)
    resp = await call_next(req)
    if req.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    elif resp.headers.get("content-type", "").startswith("text/html"):
        resp.headers["Content-Security-Policy"] = CSP
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return resp


async def body_json(req: Request) -> dict:
    try:
        d = await req.json()
    except ValueError:
        raise HTTPException(400, "JSON inválido")
    if not isinstance(d, dict):
        raise HTTPException(400, "JSON inválido")
    return d


def set_session(resp: Response, c: sqlite3.Connection, user_id: int, req: Request) -> None:
    tok = secrets.token_urlsafe(32)
    now = time.time()
    c.execute(
        "INSERT INTO sessions(token,user_id,created_at,seen_at,expires_at,ua,ip) VALUES(?,?,?,?,?,?,?)",
        (hashlib.sha256(tok.encode()).hexdigest(), user_id, now, now, now + SESSION_DAYS * 86400,
         (req.headers.get("user-agent") or "")[:300], client_ip(req)),
    )
    resp.set_cookie(COOKIE, tok, max_age=SESSION_DAYS * 86400, httponly=True, secure=COOKIE_SECURE,
                    samesite="lax", path="/")


# ---------------------------------------------------------------- autenticação
@app.post("/api/auth/login")
async def login(req: Request):
    d = await body_json(req)
    email = str(d.get("email", "")).strip().lower()
    pw = str(d.get("password", ""))
    ip = client_ip(req)
    if _throttled(ip) or _throttled(email):
        raise HTTPException(429, "Muitas tentativas. Aguarde 15 minutos.")
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        ok = check_pw(pw, u["pw"] if u else _DUMMY) and u is not None
        if not ok or not u["active"]:
            _fail(ip), _fail(email)
            audit(c, None, "login.falha", email, None, ip)
            raise HTTPException(401, "E-mail ou senha incorretos." if not ok else "Usuário desativado.")
        _fails.pop(email, None)
        c.execute("UPDATE users SET last_login=? WHERE id=?", (time.time(), u["id"]))
        resp = JSONResponse({"ok": True, "must_change": bool(u["must_change"])})
        set_session(resp, c, u["id"], req)
        audit(c, dict(u), "login", email, None, ip)
    return resp


@app.post("/api/auth/logout")
async def logout(req: Request):
    tok = req.cookies.get(COOKIE)
    if tok:
        with db() as c:
            c.execute("DELETE FROM sessions WHERE token=?", (hashlib.sha256(tok.encode()).hexdigest(),))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp


# ---------------------------------------------------------------- conta
@app.get("/api/me")
async def me(req: Request):
    u = need(req)
    return {**public_user(u, True), "roles": ROLES, "perm_keys": PERMS, "role_defaults": ROLE_DEFAULTS}


@app.patch("/api/me")
async def me_update(req: Request):
    u = need(req)
    d = await body_json(req)
    with db() as c:
        if "name" in d:
            name = str(d["name"]).strip()[:80]
            if not name:
                raise HTTPException(400, "Informe o nome.")
            c.execute("UPDATE users SET name=? WHERE id=?", (name, u["id"]))
        if "prefs" in d and isinstance(d["prefs"], dict):
            raw = json.dumps(d["prefs"], ensure_ascii=False)
            if len(raw) > 20000:
                raise HTTPException(400, "Preferências grandes demais.")
            c.execute("UPDATE users SET prefs=? WHERE id=?", (raw, u["id"]))
        row = c.execute("SELECT * FROM users WHERE id=?", (u["id"],)).fetchone()
    return public_user(row, True)


@app.post("/api/me/password")
async def me_password(req: Request):
    u = need(req)
    d = await body_json(req)
    cur, new = str(d.get("current", "")), str(d.get("new", ""))
    if not check_pw(cur, u["pw"]):
        raise HTTPException(400, "Senha atual incorreta.")
    validate_pw(new, u["email"])
    with db() as c:
        c.execute("UPDATE users SET pw=?, must_change=0 WHERE id=?", (hash_pw(new), u["id"]))
        # encerra as outras sessões: quem tinha a senha antiga perde o acesso
        c.execute("DELETE FROM sessions WHERE user_id=? AND token<>?", (u["id"], u["sid"]))
        audit(c, u, "senha.alterada", u["email"], None, client_ip(req))
    return {"ok": True}


def validate_pw(pw: str, email: str) -> None:
    if len(pw) < 10:
        raise HTTPException(400, "A senha precisa ter pelo menos 10 caracteres.")
    if pw.lower() == email or pw.lower() in email:
        raise HTTPException(400, "A senha não pode ser o próprio e-mail.")
    if len(set(pw)) < 5:
        raise HTTPException(400, "Senha muito repetitiva.")


AVATAR_RE = re.compile(r"^data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)$")


@app.put("/api/me/avatar")
async def me_avatar(req: Request):
    u = need(req)
    d = await body_json(req)
    m = AVATAR_RE.match(str(d.get("data", "")))
    if not m:
        raise HTTPException(400, "Imagem inválida.")
    blob = base64.b64decode(m.group(2))
    if len(blob) > MAX_AVATAR:
        raise HTTPException(400, "Avatar grande demais (máx. 400 KB).")
    sig = {"image/png": b"\x89PNG", "image/jpeg": b"\xff\xd8", "image/webp": b"RIFF"}[m.group(1)]
    if not blob.startswith(sig):
        raise HTTPException(400, "Imagem inválida.")
    with db() as c:
        c.execute("UPDATE users SET avatar=?, avatar_type=?, avatar_v=avatar_v+1 WHERE id=?", (blob, m.group(1), u["id"]))
        row = c.execute("SELECT * FROM users WHERE id=?", (u["id"],)).fetchone()
    return public_user(row, True)


@app.delete("/api/me/avatar")
async def me_avatar_del(req: Request):
    u = need(req)
    with db() as c:
        c.execute("UPDATE users SET avatar=NULL, avatar_type=NULL, avatar_v=avatar_v+1 WHERE id=?", (u["id"],))
        row = c.execute("SELECT * FROM users WHERE id=?", (u["id"],)).fetchone()
    return public_user(row, True)


@app.get("/api/avatar/{uid}")
async def avatar(uid: int, req: Request):
    need(req)
    with db() as c:
        row = c.execute("SELECT avatar, avatar_type FROM users WHERE id=?", (uid,)).fetchone()
    if not row or not row["avatar"]:
        raise HTTPException(404)
    return Response(row["avatar"], media_type=row["avatar_type"],
                    headers={"Cache-Control": "private, max-age=31536000, immutable"})


@app.get("/api/me/sessions")
async def my_sessions(req: Request):
    u = need(req)
    with db() as c:
        rows = c.execute("SELECT token, created_at, seen_at, ua, ip FROM sessions WHERE user_id=? AND expires_at>? "
                         "ORDER BY seen_at DESC", (u["id"], time.time())).fetchall()
    return [{"id": r["token"][:16], "created_at": r["created_at"], "seen_at": r["seen_at"], "ua": r["ua"],
             "ip": r["ip"], "current": r["token"] == u["sid"]} for r in rows]


@app.delete("/api/me/sessions/{sid}")
async def my_session_del(sid: str, req: Request):
    u = need(req)
    if not re.fullmatch(r"[0-9a-f]{16}", sid):
        raise HTTPException(400)
    with db() as c:
        c.execute("DELETE FROM sessions WHERE user_id=? AND substr(token,1,16)=? AND token<>?", (u["id"], sid, u["sid"]))
    return {"ok": True}


# ---------------------------------------------------------------- usuários (admin)
def _target(c: sqlite3.Connection, uid: int) -> sqlite3.Row:
    t = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not t:
        raise HTTPException(404, "Usuário não encontrado.")
    return t


def _guard_target(actor: dict, t: sqlite3.Row) -> None:
    if t["role"] == "master" and actor["role"] != "master":
        raise HTTPException(403, "O administrador master só pode ser alterado por ele mesmo.")
    if t["role"] == "admin" and actor["role"] not in ("master", "admin"):
        raise HTTPException(403, "Sem permissão sobre administradores.")


@app.get("/api/users")
async def users_list(req: Request):
    need(req, "usuarios")
    with db() as c:
        rows = c.execute("SELECT * FROM users ORDER BY role='master' DESC, name COLLATE NOCASE").fetchall()
    return [public_user(r, True) | {"prefs": None} for r in rows]


@app.post("/api/users")
async def users_create(req: Request):
    actor = need(req, "usuarios")
    d = await body_json(req)
    email = str(d.get("email", "")).strip().lower()
    name = str(d.get("name", "")).strip()[:80] or email.split("@")[0]
    role = d.get("role", "editor")
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "E-mail inválido.")
    if role not in ROLES:
        raise HTTPException(400, "Papel inválido.")
    if role == "admin" and actor["role"] not in ("master", "admin"):
        raise HTTPException(403, "Só administradores criam administradores.")
    pw = str(d.get("password") or "") or secrets.token_urlsafe(9)
    validate_pw(pw, email)
    overrides = _clean_perms(d.get("overrides"))
    with db() as c:
        if c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            raise HTTPException(409, "Já existe um usuário com esse e-mail.")
        cur = c.execute("INSERT INTO users(email,name,pw,role,perms,must_change,created_at) VALUES(?,?,?,?,?,1,?)",
                        (email, name, hash_pw(pw), role, json.dumps(overrides), time.time()))
        audit(c, actor, "usuario.criado", email, {"role": role, "overrides": overrides}, client_ip(req))
        row = c.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    return {"user": public_user(row, True), "password": pw}


def _clean_perms(o: Any) -> dict:
    if not isinstance(o, dict):
        return {}
    return {k: bool(v) for k, v in o.items() if k in PERMS}


@app.patch("/api/users/{uid}")
async def users_update(uid: int, req: Request):
    actor = need(req, "usuarios")
    d = await body_json(req)
    with db() as c:
        t = _target(c, uid)
        _guard_target(actor, t)
        changes = {}
        if "name" in d:
            changes["name"] = str(d["name"]).strip()[:80] or t["name"]
        if "role" in d and t["role"] != "master":
            if d["role"] not in ROLES:
                raise HTTPException(400, "Papel inválido.")
            if d["role"] == "admin" and actor["role"] not in ("master", "admin"):
                raise HTTPException(403, "Só administradores promovem a administrador.")
            changes["role"] = d["role"]
        if "overrides" in d and t["role"] != "master":
            changes["perms"] = json.dumps(_clean_perms(d["overrides"]))
        if "active" in d:
            if t["role"] == "master":
                raise HTTPException(400, "O master não pode ser desativado.")
            if t["id"] == actor["id"]:
                raise HTTPException(400, "Você não pode desativar a si mesmo.")
            changes["active"] = 1 if d["active"] else 0
        if "ai_quota" in d:
            # cota mensal de IA (US$) da pessoa; null = padrão global. Só administradores mexem em custo.
            if actor["role"] not in ("master", "admin"):
                raise HTTPException(403, "Só administradores alteram a cota de IA.")
            q = d["ai_quota"]
            if q is not None:
                try:
                    q = float(q)
                except (TypeError, ValueError):
                    raise HTTPException(400, "Cota de IA inválida.")
                if not 0 <= q <= 10000:
                    raise HTTPException(400, "Cota de IA fora da faixa (0 a 10.000).")
            changes["ai_quota"] = q
        if changes:
            c.execute(f"UPDATE users SET {', '.join(k + '=?' for k in changes)} WHERE id=?", (*changes.values(), uid))
            if changes.get("active") == 0:
                c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
            audit(c, actor, "usuario.alterado", t["email"],
                  {k: (json.loads(v) if k == "perms" else v) for k, v in changes.items()}, client_ip(req))
        row = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return public_user(row, True)


@app.post("/api/users/{uid}/reset-password")
async def users_reset(uid: int, req: Request):
    actor = need(req, "usuarios")
    with db() as c:
        t = _target(c, uid)
        _guard_target(actor, t)
        if t["role"] == "master" and actor["id"] != t["id"]:
            raise HTTPException(403)
        pw = secrets.token_urlsafe(9)
        c.execute("UPDATE users SET pw=?, must_change=1 WHERE id=?", (hash_pw(pw), uid))
        c.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        audit(c, actor, "usuario.senha_redefinida", t["email"], None, client_ip(req))
    return {"password": pw}


@app.delete("/api/users/{uid}")
async def users_delete(uid: int, req: Request):
    actor = need(req, "usuarios")
    with db() as c:
        t = _target(c, uid)
        _guard_target(actor, t)
        if t["role"] == "master":
            raise HTTPException(400, "O master não pode ser excluído.")
        if t["id"] == actor["id"]:
            raise HTTPException(400, "Você não pode excluir a si mesmo.")
        for p in c.execute("SELECT id FROM projects WHERE user_id=?", (uid,)).fetchall():
            (PROJECTS / f"{p['id']}.json").unlink(missing_ok=True)
        c.execute("DELETE FROM users WHERE id=?", (uid,))
        audit(c, actor, "usuario.excluido", t["email"], None, client_ip(req))
    return {"ok": True}


@app.get("/api/audit")
async def audit_list(req: Request, limit: int = 200):
    need(req, "auditoria")
    with db() as c:
        rows = c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (max(1, min(limit, 1000)),)).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- projetos na nuvem
NAME_RE = re.compile(r"^[\w\-. ()À-ÿ]{1,80}$")


@app.get("/api/projects")
async def projects_list(req: Request):
    u = need(req, "nuvem")
    with db() as c:
        rows = c.execute("SELECT id,name,size,created_at,updated_at FROM projects WHERE user_id=? ORDER BY updated_at DESC",
                         (u["id"],)).fetchall()
    return [dict(r) for r in rows]


@app.put("/api/projects")
async def projects_save(req: Request, name: str):
    u = need(req, "nuvem")
    name = name.strip()
    if not NAME_RE.match(name):
        raise HTTPException(400, "Nome de projeto inválido.")
    cl = int(req.headers.get("content-length") or 0)
    if cl > MAX_PROJECT:
        raise HTTPException(413, "Projeto grande demais (máx. 200 MB).")
    body = await req.body()
    if len(body) > MAX_PROJECT:
        raise HTTPException(413, "Projeto grande demais (máx. 200 MB).")
    if not body.startswith(b"{") or b'"GPlanSiS|Studio"' not in body[:400]:
        raise HTTPException(400, "Conteúdo não é um projeto GPlanSiS|Studio.")
    now = time.time()
    with _lock, db() as c:
        row = c.execute("SELECT id FROM projects WHERE user_id=? AND name=?", (u["id"], name)).fetchone()
        pid = row["id"] if row else secrets.token_hex(12)
        tmp = PROJECTS / f"{pid}.tmp"
        tmp.write_bytes(body)
        tmp.replace(PROJECTS / f"{pid}.json")
        if row:
            c.execute("UPDATE projects SET size=?, updated_at=? WHERE id=?", (len(body), now, pid))
        else:
            c.execute("INSERT INTO projects(id,user_id,name,size,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                      (pid, u["id"], name, len(body), now, now))
        audit(c, u, "projeto.salvo", name, {"bytes": len(body)}, client_ip(req))
    return {"id": pid, "name": name, "size": len(body), "updated_at": now}


@app.get("/api/projects/{pid}")
async def projects_get(pid: str, req: Request):
    u = need(req, "nuvem")
    with db() as c:
        row = c.execute("SELECT * FROM projects WHERE id=? AND user_id=?", (pid, u["id"])).fetchone()
    if not row:
        raise HTTPException(404, "Projeto não encontrado.")
    return FileResponse(PROJECTS / f"{pid}.json", media_type="application/json")


@app.delete("/api/projects/{pid}")
async def projects_del(pid: str, req: Request):
    u = need(req, "nuvem")
    with db() as c:
        row = c.execute("SELECT * FROM projects WHERE id=? AND user_id=?", (pid, u["id"])).fetchone()
        if not row:
            raise HTTPException(404, "Projeto não encontrado.")
        c.execute("DELETE FROM projects WHERE id=?", (pid,))
        audit(c, u, "projeto.excluido", row["name"], None, client_ip(req))
    (PROJECTS / f"{pid}.json").unlink(missing_ok=True)
    return {"ok": True}


# ---------------------------------------------------------------- páginas
@app.get("/healthz")
async def healthz():
    return {"ok": True}


def _page(name: str) -> FileResponse:
    return FileResponse(WEB / name, media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "no-cache, must-revalidate"})


@app.get("/")
async def index(req: Request):
    if not current(req):
        return RedirectResponse("/login", status_code=302)
    return _page("index.html")


@app.get("/login")
async def login_page(req: Request):
    if current(req):
        return RedirectResponse("/", status_code=302)
    return _page("login.html")


@app.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(WEB / "manifest.webmanifest", media_type="application/manifest+json; charset=utf-8",
                        headers={"Cache-Control": "no-cache"})


@app.get("/sw.js")
async def sw():
    # O service worker precisa revalidar sempre, senão uma versão nova demora a chegar.
    return FileResponse(WEB / "sw.js", media_type="text/javascript; charset=utf-8",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


@app.get("/favicon.ico")
async def favicon():
    return FileResponse(WEB / "icons" / "favicon.ico", media_type="image/x-icon",
                        headers={"Cache-Control": "public, max-age=604800"})


import ai  # noqa: E402  (precisa de db/need/audit definidos acima)

app.include_router(ai.router)
app.mount("/icons", StaticFiles(directory=WEB / "icons"), name="icons")
app.mount("/vendor", StaticFiles(directory=WEB / "vendor"), name="vendor")
app.mount("/plus", StaticFiles(directory=WEB / "plus"), name="plus")
