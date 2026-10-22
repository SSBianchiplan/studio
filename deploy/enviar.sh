#!/usr/bin/env bash
# Publica o GPlanSiS|Studio num servidor Linux com Caddy (via SSH).
#   HOST=meu-servidor bash deploy/enviar.sh   gera o build, envia e ativa
# Idempotente: no primeiro envio cria usuário, venv, serviço e bloco do Caddy;
# nos seguintes só troca os arquivos e reinicia o serviço. A versão anterior
# dos estáticos fica em /opt/gplansis-studio/web.antigo (reverter: ver LEIA-ME).
set -euo pipefail
cd "$(dirname "$0")/.."
HOST=${HOST:?defina HOST=<servidor ssh>}
DEST=/opt/gplansis-studio
PORTA=8972

python3 build.py

echo "› conferindo a porta $PORTA em $HOST"
ssh "$HOST" "systemctl is-active --quiet gplansis-studio || ! ss -ltn | grep -q '127.0.0.1:$PORTA '" \
  || { echo "ERRO: a porta $PORTA está ocupada por outro serviço em $HOST"; exit 1; }

echo "› enviando arquivos"
ssh "$HOST" "mkdir -p $DEST/server $DEST/web.novo"
rsync -az --delete dist/web/ "$HOST:$DEST/web.novo/"
rsync -az server/app.py server/ai.py server/requirements.txt "$HOST:$DEST/server/"
rsync -az deploy/gplansis-studio.service deploy/studio.caddy deploy/env.exemplo "$HOST:$DEST/deploy/"

echo "› instalando"
ssh "$HOST" DEST="$DEST" PORTA="$PORTA" bash -s <<'REMOTO'
set -euo pipefail
cd "$DEST"
id studio >/dev/null 2>&1 || useradd --system --home-dir "$DEST" --no-create-home --shell /usr/sbin/nologin studio
install -d -o studio -g studio -m 700 dados
if [ ! -f .env ]; then grep -v '^#' deploy/env.exemplo | sed '/^$/d' > .env; chmod 600 .env; fi
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/pip install -q --disable-pip-version-check -r server/requirements.txt
rm -rf web.antigo; [ -d web ] && mv web web.antigo; mv web.novo web
chown -R root:root web server; chmod -R a+rX web server

cp deploy/gplansis-studio.service /etc/systemd/system/gplansis-studio.service
systemctl daemon-reload
systemctl enable --quiet gplansis-studio
systemctl restart gplansis-studio
for i in $(seq 1 30); do curl -fsS "http://127.0.0.1:$PORTA/healthz" >/dev/null 2>&1 && break; sleep 1; done
curl -fsS "http://127.0.0.1:$PORTA/healthz" >/dev/null || { journalctl -u gplansis-studio -n 40 --no-pager; exit 1; }
echo "  serviço no ar"

if ! cmp -s deploy/studio.caddy /etc/caddy/studio.caddy || ! grep -q 'import /etc/caddy/studio.caddy' /etc/caddy/Caddyfile; then
  CARIMBO=$(date +%Y%m%d-%H%M%S)
  cp /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.bak-studio-$CARIMBO"
  [ -f /etc/caddy/studio.caddy ] && cp /etc/caddy/studio.caddy "/etc/caddy/studio.caddy.bak-$CARIMBO"
  cp deploy/studio.caddy /etc/caddy/studio.caddy
  # o caddy validate não abre arquivo de log: sem isso o reload falha com permission denied
  [ -f /var/log/caddy/studio.log ] || install -o caddy -g caddy -m 600 /dev/null /var/log/caddy/studio.log
  grep -q 'import /etc/caddy/studio.caddy' /etc/caddy/Caddyfile || printf '\n# GPlanSiS|Studio — editor de imagem (deploy em /opt/gplansis-studio)\nimport /etc/caddy/studio.caddy\n' >> /etc/caddy/Caddyfile
  if caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/tmp/studio-caddy.log 2>&1; then
    systemctl reload caddy
    echo "  Caddy recarregado (backup: Caddyfile.bak-studio-$CARIMBO)"
  else
    cat /tmp/studio-caddy.log | tail -20
    cp "/etc/caddy/Caddyfile.bak-studio-$CARIMBO" /etc/caddy/Caddyfile
    rm -f /etc/caddy/studio.caddy
    echo "ERRO: configuração do Caddy inválida; Caddyfile restaurado"; exit 1
  fi
fi
if [ -f dados/senha-inicial-master.txt ]; then echo "  senha inicial do master em $DEST/dados/senha-inicial-master.txt"; fi
REMOTO

echo "› conferindo pela internet"
for i in $(seq 1 20); do
  c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 https://studio.gplansis.com/login || true)
  [ "$c" = 200 ] && break; sleep 3
done
echo "  https://studio.gplansis.com/login → HTTP $c"
[ "$c" = 200 ]
