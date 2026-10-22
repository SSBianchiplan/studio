# Histórico de versões

Formato inspirado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/). A versão completa (com data e hora do build) fica em `dist/web/VERSION` e na variável `STUDIO_VERSION` do editor.

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
