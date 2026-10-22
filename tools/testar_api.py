#!/usr/bin/env python3
"""Prova da API de acesso. Roda contra um servidor de teste (banco descartável).

    STUDIO_DATA=/tmp/x STUDIO_COOKIE_SECURE=0 STUDIO_MASTER_PASSWORD='Teste-Master-2026' uvicorn app:app --port 8972
    python3 tools/testar_api.py http://127.0.0.1:8972 Teste-Master-2026
"""
import base64
import http.cookiejar
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8972"
MASTER_PW = sys.argv[2] if len(sys.argv) > 2 else "Teste-Master-2026"
MASTER = "contato@gplansis.com"
falhas = 0


class C:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def req(self, method, path, body=None, raw=None, csrf=True):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        r = urllib.request.Request(BASE + path, data=data, method=method)
        if data is not None:
            r.add_header("Content-Type", "application/json")
        if csrf:
            r.add_header("X-Studio", "1")
        try:
            with self.op.open(r) as resp:
                t = resp.read()
                return resp.status, (json.loads(t) if resp.headers.get("content-type", "").startswith("application/json") else t)
        except urllib.error.HTTPError as e:
            t = e.read()
            try:
                return e.code, json.loads(t)
            except ValueError:
                return e.code, t


def ok(cond, msg):
    global falhas
    print(("  ok   " if cond else "  FALHA ") + msg)
    if not cond:
        falhas += 1


m = C()
s, _ = m.req("POST", "/api/auth/login", {"email": MASTER, "password": "errada"})
ok(s == 401, "senha errada recusada")
s, _ = m.req("POST", "/api/auth/login", {"email": MASTER, "password": MASTER_PW}, csrf=False)
ok(s == 403, "escrita sem cabeçalho X-Studio recusada (CSRF)")
s, r = m.req("POST", "/api/auth/login", {"email": MASTER.upper(), "password": MASTER_PW})
ok(s == 200 and r["must_change"], "master entra (e-mail sem diferenciar maiúsculas) e precisa trocar a senha")
s, me = m.req("GET", "/api/me")
ok(s == 200 and me["role"] == "master" and all(me["perms"].values()), "master tem todas as permissões")
s, _ = m.req("POST", "/api/me/password", {"current": MASTER_PW, "new": "curta"})
ok(s == 400, "senha curta recusada")
NEW = "Nova-Senha-Master-2026"
s, _ = m.req("POST", "/api/me/password", {"current": MASTER_PW, "new": NEW})
ok(s == 200, "master troca a senha")
s, me = m.req("GET", "/api/me")
ok(not me["must_change"], "troca obrigatória cumprida")

s, r = m.req("PATCH", f"/api/users/{me['id']}", {"active": False})
ok(s == 400, "master não pode ser desativado")
s, r = m.req("DELETE", f"/api/users/{me['id']}")
ok(s == 400, "master não pode ser excluído")
s, r = m.req("PATCH", f"/api/users/{me['id']}", {"role": "editor"})
ok(s == 200 and r["role"] == "master", "papel do master não muda")

s, r = m.req("POST", "/api/users", {"email": "editor@teste.com", "name": "Editora", "role": "editor"})
ok(s == 200 and r["password"], "master cria editor com senha gerada")
ed_pw, ed_id = r["password"], r["user"]["id"]
s, r = m.req("POST", "/api/users", {"email": "editor@teste.com", "role": "editor"})
ok(s == 409, "e-mail duplicado recusado")
s, r = m.req("POST", "/api/users", {"email": "adm@teste.com", "name": "Adm", "role": "admin", "password": "Senha-do-Admin-1"})
ok(s == 200, "master cria admin")
adm_id = r["user"]["id"]
s, r = m.req("POST", "/api/users", {"email": "x@teste.com", "role": "master"})
ok(s == 400, "ninguém cria outro master")

s, r = m.req("PATCH", f"/api/users/{ed_id}", {"overrides": {"foto": False, "exportar": False}})
ok(s == 200 and r["perms"]["foto"] is False and r["perms"]["exportar"] is False and r["perms"]["pixel"], "permissões por pessoa")

e = C()
s, r = e.req("POST", "/api/auth/login", {"email": "editor@teste.com", "password": ed_pw})
ok(s == 200 and r["must_change"], "editor entra com a senha gerada")
s, _ = e.req("GET", "/api/users")
ok(s == 403, "editor não lista usuários")
s, _ = e.req("PATCH", f"/api/users/{me['id']}", {"name": "x"})
ok(s == 403, "editor não altera o master")
s, r = e.req("GET", "/api/me")
ok(r["perms"]["foto"] is False and r["perms"]["nuvem"] is True, "editor vê as próprias permissões")

png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 100).decode()
s, r = e.req("PUT", "/api/me/avatar", {"data": "data:image/png;base64," + png})
ok(s == 200 and r["avatar"], "avatar gravado")
s, r = e.req("PUT", "/api/me/avatar", {"data": "data:image/png;base64," + base64.b64encode(b"<svg/>").decode()})
ok(s == 400, "avatar com conteúdo falso recusado")
s, body = e.req("GET", r"/api/avatar/%d" % ed_id)
ok(s == 200 and body.startswith(b"\x89PNG"), "avatar servido")
s, r = e.req("PATCH", "/api/me", {"prefs": {"theme": "dark", "maxEdge": 8000}})
ok(s == 200 and r["prefs"]["theme"] == "dark", "preferências gravadas")

proj = json.dumps({"app": "GPlanSiS|Studio", "v": 1, "px": []}).encode()
s, r = e.req("PUT", "/api/projects?name=Meu%20projeto", raw=proj)
ok(s == 200, "projeto salvo na nuvem")
pid = r["id"]
s, r = e.req("PUT", "/api/projects?name=Meu%20projeto", raw=proj)
ok(s == 200 and r["id"] == pid, "salvar de novo sobrescreve o mesmo projeto")
s, r = e.req("PUT", "/api/projects?name=x", raw=b'{"nada":1}')
ok(s == 400, "conteúdo que não é projeto recusado")
s, r = e.req("GET", "/api/projects")
ok(s == 200 and len(r) == 1, "lista de projetos do usuário")
s, r = m.req("GET", f"/api/projects/{pid}")
ok(s == 404, "um usuário não abre projeto de outro")
s, r = e.req("GET", f"/api/projects/{pid}")
ok(s == 200, "dono abre o próprio projeto")

s, r = m.req("PATCH", f"/api/users/{ed_id}", {"active": False})
ok(s == 200, "master desativa o editor")
s, _ = e.req("GET", "/api/me")
ok(s == 401, "sessão do desativado cai na hora")
s, _ = e.req("POST", "/api/auth/login", {"email": "editor@teste.com", "password": ed_pw})
ok(s == 401, "desativado não entra")

a = C()
a.req("POST", "/api/auth/login", {"email": "adm@teste.com", "password": "Senha-do-Admin-1"})
s, _ = a.req("PATCH", f"/api/users/{me['id']}", {"name": "Outro"})
ok(s == 403, "admin não altera o master")
s, _ = a.req("POST", f"/api/users/{me['id']}/reset-password")
ok(s == 403, "admin não redefine a senha do master")
s, r = a.req("GET", "/api/audit")
ok(s == 200 and any(x["action"] == "login.falha" for x in r), "auditoria registra falhas de login")
s, _ = m.req("DELETE", f"/api/users/{adm_id}")
ok(s == 200, "master exclui admin")

anon = C()
s, _ = anon.req("GET", "/api/me")
ok(s == 401, "sem sessão: 401")
s, b = anon.req("GET", "/login")
ok(s == 200 and b"Entrar" in b, "página de login pública")
s, b = anon.req("GET", "/manifest.webmanifest")
ok(s == 200, "manifest público")
print("\n" + ("TUDO CERTO" if not falhas else f"{falhas} FALHA(S)"))
sys.exit(1 if falhas else 0)
