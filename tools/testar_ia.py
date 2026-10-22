#!/usr/bin/env python3
"""Prova das rotas de IA contra o servidor de teste (tools/servidor_teste_ia.py, Claude simulado).

    python3 tools/testar_ia.py http://127.0.0.1:8973 Teste-Master-2026

O e-mail do master é o de STUDIO_MASTER_EMAIL (padrão contato@gplansis.com), o mesmo do servidor de teste.
"""
import base64
import json
import os
import sys

import http.cookiejar
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8973"
falhas = 0


class C:
    def __init__(self):
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def req(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(BASE + path, data=data, method=method, headers={"X-Studio": "1", "Content-Type": "application/json"})
        try:
            with self.op.open(r) as resp:
                return resp.status, json.loads(resp.read() or b"null")
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

PW = sys.argv[2] if len(sys.argv) > 2 else "Teste-Master-2026"
# JPEG mínimo válido para o formato data URL (o servidor só confere o formato; o Claude é simulado)
IMG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 2000).decode()

MASTER = os.environ.get("STUDIO_MASTER_EMAIL", "contato@gplansis.com")
m = C()
s, r = m.req("POST", "/api/auth/login", {"email": MASTER, "password": PW})
ok(s == 200, "master entra")
m.req("POST", "/api/me/password", {"current": PW, "new": "Nova-Senha-Master-2026"})
s, st = m.req("GET", "/api/ai/status")
ok(s == 200 and st["configured"] is False and st["allowed"] is True, "IA começa desconfigurada; master tem a permissão")
s, r = m.req("POST", "/api/ai/run", {"feature": "ask", "image": IMG, "text": "oi"})
ok(s == 503, "sem chave: 503 com orientação")
s, r = m.req("PUT", "/api/ai/config", {"key": "chave-errada"})
ok(s == 400, "chave com formato errado recusada")
KEY = "sk-ant-api03-" + "x" * 40 + "WXYZ"
s, r = m.req("PUT", "/api/ai/config", {"key": KEY, "model": "claude-opus-5-5", "quota_usd": 1})
ok(s == 200 and r["key_hint"] == "…WXYZ" and "key" not in r, "chave salva e nunca devolvida (só os 4 últimos)")
s, raw = m.req("GET", "/api/ai/config")
ok(KEY not in json.dumps(raw), "GET da configuração não vaza a chave")
s, r = m.req("PUT", "/api/ai/config", {"model": "gpt-5"})
ok(s == 400, "modelo desconhecido recusado")

for feat in ["edit", "enhance", "catalog", "svg", "redraw", "ocr", "crop", "select", "palette", "critique", "ask"]:
    body = {"feature": feat, "image": IMG, "text": "teste", "context": {"w": 800, "h": 600}}
    if feat == "edit":
        body["catalog"] = [{"id": "bc", "nome": "Brilho", "params": []}]
    s, r = m.req("POST", "/api/ai/run", body)
    ok(s == 200 and r["feature"] == feat and r["usage"]["cost_usd"] > 0, f"função {feat}: {s} custo US$ {r.get('usage', {}).get('cost_usd') if s == 200 else r}")
    if feat == "svg":
        svg = r["result"]["svg"]
        ok("<script" not in svg and "onclick" not in svg and "javascript:" not in svg and "&#106;" not in svg
           and "<foreignObject" not in svg and "<rect" in svg and 'href="#corpo"' in svg, "SVG gerado é limpo (sem script, on*, javascript:, entidades, foreignObject; #id interno mantido)")

s, r = m.req("POST", "/api/ai/run", {"feature": "edit", "image": IMG, "text": "x"})
ok(s == 400, "editar sem catálogo recusado")
s, r = m.req("POST", "/api/ai/run", {"feature": "rm -rf", "image": IMG})
ok(s == 400, "função desconhecida recusada")
s, r = m.req("POST", "/api/ai/run", {"feature": "ask", "image": "data:text/html;base64,PGh0bWw+", "text": "x"})
ok(s == 400, "imagem que não é imagem recusada")
s, r = m.req("POST", "/api/ai/run", {"feature": "ask", "image": "data:image/png;base64," + "A" * (5 * 1024 * 1024 + 4), "text": "x"})
ok(s == 413, "imagem acima de 5 MB em base64 recusada (413)")
try:
    s, r = m.req("POST", "/api/ai/run", {"feature": "ask", "image": IMG, "text": "x", "lixo": "A" * (7 * 1024 * 1024)})
except urllib.error.URLError:
    s = "conexão encerrada"  # o servidor responde 413 pelo Content-Length e fecha antes de receber tudo
ok(s in (413, "conexão encerrada"), f"corpo acima de 6 MB recusado antes de interpretar ({s})")
s, r = m.req("POST", "/api/ai/run", {"feature": "svg", "text": "x", "context": {"w": "abc", "h": 1e300}})
ok(s == 200, "dimensões inválidas no contexto não derrubam a rota")
s, r = m.req("PUT", "/api/ai/config", {"quota_usd": "muito"})
ok(s == 400, "cota não numérica recusada (400)")
s, r = m.req("POST", "/api/ai/run", {"feature": "ask", "image": IMG, "text": "RECUSAR isto"})
ok(s == 422, "recusa do modelo vira mensagem clara (422)")
s, calls = m.req("GET", "/__teste/calls")
c_edit = next(c for c in calls if c["feature"] == "edit")
ok(c_edit["catalog"] and c_edit["has_image"] and "<pedido>teste</pedido>" in c_edit["text"], "pedido vai delimitado como dado e o catálogo vai no sistema")
ok(next(c for c in calls if c["feature"] == "svg")["effort"] == "high", "esforço por função (svg = high)")

s, r = m.req("PUT", "/api/ai/config", {"level": "economia"})
m.req("POST", "/api/ai/run", {"feature": "critique", "image": IMG})
s, calls = m.req("GET", "/__teste/calls")
ok(calls[-1]["effort"] == "low", "nível Economia força esforço baixo")

# cota: US$ 1 por mês; cada chamada simulada custa US$ 0,0144 no Opus 5.5
s, us = m.req("GET", "/api/ai/usage")
spent = sum(x["cost"] for x in us["by_user"])
ok(s == 200 and spent > 0 and any(f["feature"] == "svg" for f in us["by_feature"]), f"uso registrado: US$ {spent:.4f}")
s, r = m.req("PUT", "/api/ai/config", {"quota_usd": 0.05})
s, r = m.req("POST", "/api/ai/run", {"feature": "ask", "image": IMG, "text": "x"})
ok(s == 402, "cota mensal atingida bloqueia (402)")
m.req("PUT", "/api/ai/config", {"quota_usd": 20})

# permissão por pessoa
s, r = m.req("POST", "/api/users", {"email": "vis@teste.com", "name": "Visual", "role": "visualizador", "password": "Senha-Vis-12345"})
vid = r["user"]["id"]
v = C()
v.req("POST", "/api/auth/login", {"email": "vis@teste.com", "password": "Senha-Vis-12345"})
s, r = v.req("POST", "/api/ai/run", {"feature": "ask", "image": IMG, "text": "x"})
ok(s == 403, "visualizador não usa IA por padrão")
s, r = v.req("GET", "/api/ai/config")
ok(s == 403, "não-admin não vê a configuração")
s, r = m.req("PATCH", f"/api/users/{vid}", {"ai_quota": "x"})
ok(s == 400, "cota individual inválida recusada")
m.req("PATCH", f"/api/users/{vid}", {"overrides": {"ia": True}, "ai_quota": 0.02})
s, r = v.req("POST", "/api/ai/run", {"feature": "ask", "image": IMG, "text": "x"})
ok(s == 200, "liberar 'ia' para a pessoa funciona")
codes = [v.req("POST", "/api/ai/run", {"feature": "ask", "image": IMG, "text": "x"})[0] for _ in range(3)]
ok(codes == [200, 402, 402], f"cota própria da pessoa (US$ 0,02) vale acima da padrão: bloqueia ao atingir {codes}")
s, us = v.req("GET", "/api/ai/usage")
ok(s == 200 and len(us["by_user"]) == 1, "pessoa comum vê só o próprio uso")
# quem gerencia usuários mas não é admin não mexe em custo
s, r = m.req("POST", "/api/users", {"email": "ger@teste.com", "name": "Gerente", "role": "editor", "password": "Senha-Ger-12345"})
gid = r["user"]["id"]
m.req("PATCH", f"/api/users/{gid}", {"overrides": {"usuarios": True}})
g = C()
g.req("POST", "/api/auth/login", {"email": "ger@teste.com", "password": "Senha-Ger-12345"})
s, r = g.req("PATCH", f"/api/users/{gid}", {"ai_quota": 9999})
ok(s == 403, "não-admin com permissão de usuários não altera cota de IA (403)")
s, r = m.req("PUT", "/api/ai/config", {"key": ""})
s, st = m.req("GET", "/api/ai/status")
ok(st["configured"] is False, "remover a chave desliga a IA")
s, au = m.req("GET", "/api/audit")
ok(any(a["action"] == "ia.configurada" and "sk-ant" not in (a["detail"] or "") for a in au), "auditoria registra a configuração sem a chave")
ok(KEY not in json.dumps(au), "a chave não aparece em nenhum registro de auditoria")
print("\n" + ("TUDO CERTO" if not falhas else f"{falhas} FALHA(S)"))
sys.exit(1 if falhas else 0)
