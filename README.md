# Teste Vocacional - Alfabits

App web (PWA, funciona como aplicativo no celular) de teste vocacional adaptativo,
com página de resultado detalhada gerada por IA.

## Como funciona

1. **Cadastro:** nome, WhatsApp, nascimento, cidade, escola, série (opcional),
   autorização LGPD (obrigatória) e autorização de contato (opcional).
2. **12 perguntas gerais** (2 por perfil RIASEC: Realista, Investigativo, Artístico, Social,
   Empreendedor, Convencional).
3. **12 perguntas focadas** nos 3 perfis mais fortes (é aqui que o teste se adapta).
4. **2 perguntas abertas** (tempo livre, curso que já pensou), que a IA lê.
5. **Página de resultado** (`/r/<link secreto>`), que abre na hora e se completa sozinha:
   - perfil em 2 frases + aviso discreto de que o conteúdo é gerado com IA;
   - 3 abas, uma por curso: por que combina, duração, dia a dia, onde trabalha, dicas,
     curiosidades e onde estudar perto (públicas e privadas, com botão "Ver curso");
   - "Quero conversar com a Alfabits" (curso de interesse, período, falar com o aluno ou responsável);
   - compartilhar (geral ou para um número de WhatsApp) e salvar em PDF.

Nada é enviado pelo número da Alfabits: compartilhar e "Chamar a Alfabits no WhatsApp" abrem o
WhatsApp **da própria pessoa**. Sem risco de ban. (O código antigo do WAHA está em `extras/`.)

### Geração em segundo plano
1. IA escolhe os 3 cursos + "por que combina" (rápido) → as abas já aparecem.
2. IA gera os detalhes dos 3 cursos em paralelo → cada aba se completa quando fica pronta.
3. Tudo fica salvo no banco: reabrir a página não gasta crédito de novo.
Se a IA falhar, entra um conteúdo padrão escrito por nós (e o admin pode reprocessar depois).

## Rodar localmente (Windows)

1. Instale o uv (uma vez), no PowerShell:
   `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
2. `uv sync` e depois `uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` → http://127.0.0.1:8000
   (celular no mesmo Wi-Fi: http://IP-DO-PC:8000, veja o IP com `ipconfig`).
3. A configuração vem de variáveis de ambiente (ou de um arquivo `.env` local, fora do Git; veja a lista em Deploy).
   Sem `LLM_API_KEY`, a página usa o conteúdo padrão. `LLM_MOCK=1` simula a IA sem gastar crédito.

## Testes

`uv run pytest -q`. Principais arquivos:

- **test_teste_vocacional.py**: valida o teste em si (12 personas caem na área certa, robustez a
  respostas "distraídas", perfis mistos, nenhuma área favorecida, monotonicidade).
- **test_resultado.py**: página e geração (2 etapas, página se completando aos poucos, falha de 1 curso,
  fallback, reprocessar, fila sobrevive a reinício, 40 ao mesmo tempo), privacidade (a página não expõe
  telefone/sobrenome/nascimento), eventos, "quero conversar", planilha de leads por temperatura, admin.
- **test_llm.py**: validação do JSON da IA, links inventados removidos, retry, 401 sem insistir.
- **test_api.py**: cadastro/LGPD, validações, idempotência.

Teste de carga (400 pessoas, IA simulada):
```
terminal 1:  set LLM_MOCK=1&& set LLM_MOCK_DELAY=3&& uv run uvicorn app.main:app --port 8000
terminal 2:  uv run python scripts/load_test.py --users 400 --ramp 600
```

## Painel admin: `/admin`

Login com as variáveis `ADMIN_USER` e `ADMIN_PASSWORD`. Senha errada bloqueia por 3 min; cada novo erro multiplica
a espera por 3 (9, 27, 81 min... até 24 h). O painel mostra números gerais, filtros (cidade, escola, idade, série,
autorizou contato, temperatura, pediu para conversar, compartilhou), tudo de cada aluno (clique na linha) e
baixa a planilha do filtro atual. Reiniciar o servidor desloga e zera os bloqueios.

## Admin por URL (scripts; usa a variável ADMIN_TOKEN)

- `GET /api/admin/stats?token=...`: contagem por status, quantos querem conversar
- `GET /api/admin/leads.csv?token=...`: planilha do lead mais quente para o mais frio
- `GET /api/admin/export.csv?token=...`: mesma planilha, por ordem de cadastro
- `POST /api/admin/reprocessar?token=...`: gera de novo os detalhes que caíram no conteúdo padrão

**Temperatura do lead** (pontos): pediu para conversar +100 · compartilhou +15 (até 30) ·
família/amigos abriram o link +15 · salvou PDF +10 · clicou em instituição +5 (até 20) ·
abriu outra aba de curso +3 · voltou à página +5. Quente ≥ 100, morno ≥ 20, frio < 20.
A planilha também traz: curso de interesse, melhor período, responsável e telefone, cursos abertos,
instituições clicadas, respostas abertas e o link do resultado.

## Deploy (Railway), próxima etapa

1. Railway: New Project → Deploy from GitHub (o `uv.lock` é detectado; start no `railway.json`).
2. Variables (cadastradas no painel do Railway, nunca no Git):
   - IA: `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_REASONING_EFFORT` (opcionais: `LLM_WORKERS`,
     `LLM_MAX_CONCURRENCY`, `LLM_TIMEOUT`, `LLM_JSON_MODE`)
   - Organização: `ORG_NAME`, `ORG_WHATSAPP`, `ORG_REGIAO`, `PUBLIC_URL` (domínio gerado pelo Railway)
   - Admin: `ADMIN_USER`, `ADMIN_PASSWORD`, `ADMIN_TOKEN`
3. Nomes, valores padrão e explicação de cada variável: `app/config.py`.
4. **Volume** montado em `/data` + `DATABASE_PATH=/data/teste_vocacional.db`.
5. **1 processo só** (não use `--workers`): a fila fica em memória + SQLite.

## Estrutura

```
app/main.py        API, página de resultado, eventos, interesse, admin/leads
app/questions.py   perguntas, áreas, cursos e conteúdo padrão (edite aqui)
app/scoring.py     cálculo do perfil e opções padrão
app/llm.py         IA: escolha dos 3 cursos + detalhes de cada curso
app/worker.py      fila em segundo plano
app/db.py          SQLite
app/static/        PWA: teste (index.html/app.js) e resultado (resultado.html/js/css)
scripts/           load_test.py (pico de 400)
extras/            código antigo do WAHA (não usado)
tests/             pytest
```
