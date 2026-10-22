# Como contribuir com o GPlanSiS|Studio

Obrigado pelo interesse! Toda ajuda conta: código, testes, amostras de formatos, revisão de texto, ideias.

## Antes de começar

- Leia o [código de conduta](CODE_OF_CONDUCT.md).
- Procure nas [issues](https://github.com/SSBianchiplan/studio/issues) se o assunto já está em discussão. Para mudanças grandes, abra uma issue antes do código, para combinarmos a abordagem.
- Falhas de segurança **não** vão em issue pública: veja [SECURITY.md](SECURITY.md).

## Ambiente

Siga [Como rodar localmente](README.md#como-rodar-localmente). Em resumo:

```bash
python3 build.py
python3 -m venv .venv && .venv/bin/pip install -r server/requirements.txt
cp .env.example .env && set -a && . ./.env && set +a
.venv/bin/uvicorn --app-dir server app:app --host 127.0.0.1 --port 8972
```

## Onde mexer

| Quero… | Arquivo |
|---|---|
| ler ou exportar um formato novo | `web/plus/formats.js` |
| criar um ajuste ou filtro | `web/plus/filters.js` |
| mexer em conta, configurações, usuários, nuvem (lado do navegador) | `web/plus/account.js`, `web/plus/plus.css` |
| mexer na API, sessão, permissões, banco | `server/app.py` |
| login, PWA, ícones | `web/login.html`, `web/sw.js`, `web/manifest.webmanifest`, `web/icons/` |
| integrar algo novo ao editor original | `build.py` (ponto de integração verificado) |

**Regra do editor original:** `editor/GPlanSiS-Studio.html` não é editado à mão. Mudanças no comportamento do editor entram como módulo em `web/plus/` ou como um ponto de integração em `build.py`, que precisa casar exatamente o número de vezes esperado — se não casar, o build para.

## Padrões

- Interface e mensagens em **português do Brasil**.
- Sem dependências novas de CDN (o editor original ainda carrega JSZip e polygon-clipping sob demanda; trazê-las para `web/vendor/` é uma boa contribuição): bibliotecas de terceiros ficam em `web/vendor/`, **com o texto da licença** (`LICENSE-*.txt`), e só com licença compatível.
- O processamento de imagem continua **no navegador**; o servidor não recebe imagem para processar.
- Toda rota de escrita exige sessão e o cabeçalho anti-CSRF `X-Studio`; permissões novas precisam ser validadas no servidor.
- Nada de segredo, dado real de usuário ou arquivo grande (> 5 MB) no repositório.

## Testes

Antes do pull request:

```bash
python3 build.py                                    # o build precisa passar
python3 tools/testar_api.py http://127.0.0.1:8972 <senha-do-master-de-teste>
```

Se a mudança é visual ou de formato, rode também `tools/prova_navegador.mjs` (ver o cabeçalho do arquivo) e anexe capturas no PR.

## Pull request

1. Faça um fork e crie uma branch a partir de `main` (`feat/filtro-x`, `fix/heic-safari`).
2. Commits pequenos e com mensagem clara, em português.
3. Preencha o modelo de PR: o que muda, como testou, capturas quando houver mudança de tela.
4. Um mantenedor revisa; ajustes pedidos na revisão entram na mesma branch.

## Licença das contribuições

O projeto é distribuído sob a [licença MIT](LICENSE). Ao enviar uma contribuição, você declara que o código é seu (ou que tem direito de enviá-lo) e concorda que ela seja distribuída sob a licença MIT.

Dúvidas: abra uma issue do tipo "Pergunta" ou escreva para contato@gplansis.com.
