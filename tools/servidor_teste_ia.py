#!/usr/bin/env python3
"""Servidor de TESTE com o Claude simulado: as rotas, cotas, permissões, custos e o
editor funcionam de verdade; só a chamada à Anthropic devolve respostas prontas.
Nunca use em produção.

    cd studio/server && STUDIO_DATA=/tmp/x STUDIO_COOKIE_SECURE=0 STUDIO_MASTER_PASSWORD='Teste-Master-2026' \
        python ../tools/servidor_teste_ia.py 8973
"""
import json
import sys
from types import SimpleNamespace as NS

import uvicorn

sys.path.insert(0, ".")
import app as studio  # noqa: E402
import ai  # noqa: E402

CANNED = {
    "edit": {"summary": "Mais quente e contrastado.", "ops": [
        {"fx": "whitebal", "params": [{"k": "t", "v": "25"}], "reason": "esquentar"},
        {"fx": "bc", "params": [{"k": "c", "v": "30"}, {"k": "b", "v": "999"}], "reason": "contraste (brilho fora da faixa é recortado)"},
        {"fx": "naoexiste", "params": [], "reason": "deve ser ignorado"}]},
    "enhance": {"summary": "Foto escura e fria.", "issues": ["subexposta"],
                "settings": {"exp": 0.6, "con": 10, "hi": -20, "sh": 25, "wh": 0, "bl": 0, "temp": 12, "tint": 0, "vib": 15,
                             "sat": 0, "cla": 10, "dhz": 5, "tex": 0}},
    "catalog": {"title": "Pátio industrial ao entardecer", "caption": "Galpões e chaminés.", "alt_text": "Pátio industrial com chaminés",
                "keywords": ["indústria", "pátio", "chaminé"], "rating": 4, "label": "green", "issues": []},
    "svg": {"title": "Válvula", "svg": '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 200 100"><script>alert(1)</script>'
            '<rect id="corpo" x="20" y="30" width="160" height="40" rx="8" fill="#3a86d9" onclick="x()"/>'
            '<a href="javascript:alert(1)"><circle cx="100" cy="50" r="18" fill="#f6a709"/></a>'
            '<a xlink:href="&#106;avascript:alert(1)"><use href="#corpo"/></a><foreignObject><div>x</div></foreignObject></svg>', "notes": "ok"},
    "redraw": {"title": "Logo", "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="40" fill="#3faa6b"/></svg>', "notes": ""},
    "ocr": {"language": "pt", "full_text": "PERIGO\nALTA TENSÃO", "blocks": [{"text": "PERIGO", "x": .1, "y": .1, "w": .3, "h": .1}]},
    "crop": {"subject": {"label": "chaminé", "x": .3, "y": .2, "w": .2, "h": .5},
             "crops": [{"aspect": "1:1", "reason": "assunto nos terços", "x": .2, "y": .1, "w": .5, "h": .75}]},
    "select": {"objects": [{"label": "sol", "confidence": .9, "x": .55, "y": .45, "w": .2, "h": .25}]},
    "palette": {"colors": [{"hex": "#1d2c55", "name": "azul noite", "role": "fundo"}, {"hex": "#f2b46b", "name": "pêssego", "role": "destaque"}],
                "harmony": "complementar", "suggestions": ["aumente o contraste do texto"]},
    "critique": {"score": 7, "summary": "Boa base.", "strengths": ["cores"], "issues": [{"problem": "horizonte torto", "fix": "Endireitar no Foto"}]},
    "ask": {"answer": "É um pôr do sol na serra."},
}
CALLS = []


async def fake_run(cfg, feature, content, extra_system, effort, max_tokens, schema):
    CALLS.append({"feature": feature, "effort": effort, "model": cfg["model"], "has_image": any(c["type"] == "image" for c in content),
                  "catalog": bool(extra_system), "text": content[-1]["text"][-300:]})
    if "RECUSAR" in content[-1]["text"]:
        return NS(model=cfg["model"], stop_reason="refusal", content=[], usage=NS(input_tokens=500, output_tokens=0,
                  cache_read_input_tokens=0, cache_creation_input_tokens=0))
    return NS(model=cfg["model"], stop_reason="end_turn", content=[NS(type="text", text=json.dumps(CANNED[feature]))],
              usage=NS(input_tokens=1600, output_tokens=400, cache_read_input_tokens=0, cache_creation_input_tokens=0))


ai.run_claude = fake_run


@studio.app.get("/__teste/calls")
async def calls():
    return CALLS


if __name__ == "__main__":
    uvicorn.run(studio.app, host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8973, log_level="warning")
