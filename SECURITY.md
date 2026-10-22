# Política de segurança

## Versões cobertas

| Versão | Suporte |
|---|---|
| 2.x (a que está no ar em studio.gplansis.com) | sim |
| 1.x (editor estático, sem login) | não |

## Como relatar uma vulnerabilidade

**Não abra issue pública.** Escreva para **contato@gplansis.com** com o assunto `[segurança] Studio` e inclua:

- descrição do problema e o impacto que você enxerga;
- passos para reproduzir (de preferência numa instância local — ver README);
- versão (`STUDIO_VERSION` no console do navegador, ou `dist/web/VERSION`) e navegador.

Respondemos confirmando o recebimento e mantemos você informado até a correção. Pedimos que a divulgação pública espere a correção estar no ar; damos o crédito a quem relatou, se quiser.

## Escopo

Interessam especialmente: autenticação e sessão, permissões e escalada de papel, CSRF, acesso a projetos de outra pessoa, injeção (HTML/SVG/arquivos importados), negação de serviço por upload, vazamento de dados do IndexedDB entre usuários.

Não teste contra a produção (studio.gplansis.com) de forma que afete outras pessoas: nada de força bruta, carga ou acesso a contas que não são suas.
