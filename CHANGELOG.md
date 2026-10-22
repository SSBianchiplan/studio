# Histórico de versões

Formato inspirado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/). A versão completa (com data e hora do build) fica em `dist/web/VERSION` e na variável `STUDIO_VERSION` do editor.

## [2.1.0] — 2026-10-22

### Adicionado
- **Funções de IA com o Claude (Anthropic)**, menu **IA** no Pixel, Vetor e Foto: editar por instrução (`Ctrl+K`, vira camada de ajuste desfazível), melhorar automaticamente, selecionar com IA, sugerir enquadramento, gerar ilustração e redesenhar como vetor (SVG), catalogar fotos (título, legenda, texto alternativo, palavras-chave), ler texto, analisar paleta, revisar composição e perguntar sobre a imagem.
- `server/ai.py` com as rotas `/api/ai/run`, `/api/ai/status`, `/api/ai/config` (+ `/test`) e `/api/ai/usage`; front em `web/plus/ai.js`; aba *Configurações › IA* com chave, modelo, nível, cota padrão e uso por pessoa.
- Permissão **`ia`** ("Usar IA"): ligada para administrador e editor, desligada para visualizador; ajustável por pessoa.
- **Cota mensal por pessoa** (`users.ai_quota`, padrão global de US$ 20), registro de tokens e custo em `ai_usage`, limite de 3 chamadas simultâneas e 30 por minuto por pessoa.
- Variável `STUDIO_ANTHROPIC_API_KEY` (opcional). Sem chave, a IA fica desligada de forma graciosa (503 com orientação) e o resto do Studio não muda.
- Legenda e texto alternativo das fotos passam a ser salvos no projeto (dois pontos de integração novos no `build.py`).
- Testes `tools/testar_ia.py`, `tools/servidor_teste_ia.py` (Claude simulado) e `tools/prova_ia.mjs` (Chrome).
- Dependência `anthropic==1.15.0`.

### Segurança
- A chave fica só no servidor e nunca é devolvida ao navegador (só os 4 últimos caracteres), nem gravada na auditoria ou em log.
- Corpo de `/api/ai/run` limitado a 6 MB (lido em blocos) e imagem a 5 MB em base64; dimensões e cotas inválidas viram 400 em vez de erro interno.
- Só administradores alteram cotas de IA (inclusive na rota de usuários).
- Limpeza do SVG gerado reforçada: remove `script`, `foreignObject`, `style`, `image`, animações que trocam `href`, eventos `on*`, `href` não internos (inclusive com entidades) e `url()` externo.

### Corrigido
- `deploy/enviar.sh` passa a enviar `server/ai.py`.

## [2.0.0] — 2026-10-19

Versão no ar em studio.gplansis.com (build `2.0.0-202610191725`).

### Adicionado
- Servidor de acesso (FastAPI + SQLite): login, sessão por cookie seguro, anti-CSRF, limite de tentativas, auditoria.
- Usuários, papéis (administrador, editor, visualizador) e permissões por pessoa; administrador master protegido.
- Configurações por conta: perfil com avatar (recorte, HEIC), segurança e sessões ativas, preferências sincronizadas, formatos, usuários e permissões, auditoria, sobre.
- Projetos na nuvem (`Ctrl+Shift+S`) e salvamento local separado por usuário.
- Leitura de HEIC/HEIF, JPEG XL, JPEG 2000, TIFF, PSD/PSB com camadas, RAW (prévia embutida), TGA, QOI, PNM/PFM, Radiance HDR, PCX e animações como camadas.
- Exportação PSD com camadas, TIFF, BMP, ICO multitamanho, QOI e AVIF (onde o navegador codifica).
- Ajustes e filtros novos não destrutivos (Exposição, Vibração, CLAHE, Remover névoa, LUT 3D, Correção de lente, Tilt-shift, Pintura a óleo e outros), Preenchimento inteligente e Histograma.
- PWA instalável (manifest, ícones, service worker) e layout para celular.
- `build.py` com pontos de integração verificados sobre o editor original; `deploy/enviar.sh` idempotente.

## [1.0.0]

- Editor original em arquivo único (`editor/GPlanSiS-Studio.html`) com os módulos Pixel, Vetor, Foto e Ponte, servido como página estática, sem login.
