# Plano — Sequências de Acordes Customizadas (backend + recorte de frontend)

## Contexto atual

- `main.py` carrega `data/top/dataset_final.csv` uma vez no import: 67.585 músicas,
  52 gêneros, 6.653 acordes únicos; a busca por sequência usa a coluna `SEQ_FAMOSA`
  (`main.py:203-223`), não a cifra.
- As 6 sequências vivem num dict hardcoded (`main.py:40-45`) e o ramo `sequencia` de
  `/similares` concatena a query numa string única (`main.py:190-197`).
- Não há banco. Estado = CSV em memória; qualquer sequência nova exigiria deploy.
- Medição da fase de pesquisa: a tag é subconjunto estrito da janela deslizante
  (ex.: 199 vs. 866 músicas para `Bm,G,D,A`), ou seja, é curadoria, não a definição de
  "contém a progressão" — daí o snapshot de compatibilidade das 6 seeds.
- Frontend `#/porsequencia` tem 4 sequências hardcoded em `sequencia.js:2-37`, envia
  `GET /similares?sequencia=C,G,Am,F` (`sequencia.js:63-90`) e não tem formulário de
  cadastro. O contrato da URL precisa continuar válido.
- Restrição de prazo: entrega hoje 23:59, então o frontend entra como **recorte mínimo
  demonstrável** (catálogo dinâmico + cadastro + busca), sem redesenho de tela.

## Requisitos

### Funcionais (backend)

- Catálogo de sequências persistido em banco, aberto e anônimo (sem login).
- `GET /sequencias` lista o catálogo (6 seeds + novas), ordenado por `id`.
- `POST /sequencias` cria uma sequência e já devolve `total_musicas`.
- `GET /similares?sequencia=...` passa a resolver pelo catálogo, mantendo
  `json.dumps`, paginação (`pagina`), filtro `generos` e o shape de cada música.
- As 6 sequências originais devolvem **exatamente** os mesmos resultados; sequência
  desconhecida continua devolvendo `[]`.
- Dados sobrevivem a `docker restart` e a rebuild da imagem.

### Funcionais (recorte de frontend)

- `#/porsequencia` renderiza o catálogo real de `GET /sequencias` (as 6 seeds e as
  criadas por visitantes), sem lista hardcoded.
- Formulário mínimo para montar uma sequência (adicionar/remover acorde na ordem,
  prévia em `df-hex`) e cadastrar; sucesso recarrega o catálogo e já busca.
- Busca pela sequência nova usa o mesmo botão/fluxo das antigas; erros `400`/`409`
  aparecem em `vm.esfigeSpeech`.
- Nenhum arquivo do frontend fora de `sequencia.js` e `sequencia.html` muda.

### Não-funcionais

- Zero dependências novas em runtime (`sqlite3` é stdlib); sem serviço externo.
- Container único e local-only (ADR 0001); volume dedicado para o banco.
- `POST` completa em < 1 s (scan ingênuo medido em 450–480 ms sobre o catálogo inteiro).
- Leitura de `/similares` não pode ficar mais lenta que hoje (ordem ~10² ms).
- Segurança: entrada validada e SQL parametrizado; sem autenticação é decisão de produto.

## Decisões de design

1. **SQLite** (`sqlite3`) com arquivo em `DECIFRAME_DB` (default `var/deciframe.db`;
   no container resolve para `/app/var/deciframe.db`), `journal_mode=WAL` e
   `busy_timeout=5000`, conexão por request. Motivo: stdlib, transações reais sob
   gunicorn, aderência à ADR 0001. Alternativas descartadas na proposta (DuckDB, JSON).
2. **Matching por subsequência contígua** de `musica.cifra`, case-sensitive, sem
   sinônimos/transposição. Motivo: preserva ordem e repetições (seção 1.1 da pesquisa);
   `musica.acordes` é `set` e não serve (`musica.py:17`).
3. **Matches materializados** em `sequencia_matches` no write, com as 6 seeds recebendo
   no bootstrap o snapshot da tag `SEQ_FAMOSA` (paridade byte a byte). Leitura vira
   pertinência de conjunto, não varredura.
4. **Assinatura canônica** `','.join(tokens)` como chave única: é o mesmo texto que o
   frontend já envia, então a URL legada continua válida; duplicata → `409`.
5. **Limites de entrada**: 2–16 acordes, token 1–12 caracteres sem vírgula/espaço
   interno, catálogo limitado a 1.000 sequências.
6. **Frontend mínimo, sem tocar no stack**: `GET /sequencias` no load do controller e
   `POST /sequencias` no formulário; a busca continua chamando
   `/similares?sequencia=<csv>` (mesma função e mesmo formato de resposta), e o
   catálogo é normalizado para o shape `{acorde, cor}` que o `df-hex` já consome.
   Motivo: menor diff possível em AngularJS legado, sem build step e sem mexer em
   `routes.js`/`app.js`. Alternativa descartada: novo controller/view (mais código,
   mais risco, zero ganho para a demo).

## Esquema (alto nível)

```sql
CREATE TABLE sequencias (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  assinatura TEXT NOT NULL UNIQUE,          -- "C,G,Am,F"
  acordes TEXT NOT NULL,                    -- JSON array ordenado
  origem TEXT NOT NULL CHECK (origem IN ('seed','usuario')),
  criada_em TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE sequencia_matches (
  sequencia_id INTEGER NOT NULL REFERENCES sequencias(id) ON DELETE CASCADE,
  id_unico_musica TEXT NOT NULL,
  PRIMARY KEY (sequencia_id, id_unico_musica)
);
```

Seeds entram com ids fixos 0–5 (`INSERT OR IGNORE`), preservando o significado dos ids
antigos e o resultado da regressão. Ordenação dos resultados continua vindo de
`musicas.values()` (popularidade desc), reproduzindo a ordem de hoje.

## API

| Rota | Método | Entrada | Saída |
|---|---|---|---|
| `/sequencias` | GET | — | `[{id, acordes, origem, criada_em}]` |
| `/sequencias` | POST | `{"acordes": ["C","G","Am","F"]}` | `201 {id, acordes, origem, criada_em, total_musicas}`; `400 {erro}`; `409 {erro, id}` |
| `/similares` | GET | `sequencia` (csv), `generos`, `pagina` | igual a hoje; `[]` se a assinatura não existe |

Todas as respostas seguem `json.dumps(...)` (string, `Content-Type: text/html`).

## Passos

Horário de início deste plano: **hoje, 17:15**. Fim de linha: **23:59**, sem folga real.
Se um passo furar, aplicar as linhas de corte abaixo em vez de estourar o prazo.

1. **17:15–17:30 — Capturar a linha de base antes de tocar no código** (15 min)
   - Script descartável gera `tests/fixtures/baseline_sequencias.json` com o JSON de
     `/similares?sequencia=<csv>` para as 6 seeds, com e sem `generos`, páginas 1–3.
   - Commit da fixture (é o oráculo do teste de regressão).
2. **17:30–18:50 — Criar `persistencia.py`** (1 h 20)
   - `init_db()`, `get_conn()` (contextmanager), `SEQUENCIAS_SEED` (ids 0–5, acordes da
     pesquisa §1.2), `seed_catalog()`, `listar_sequencias()`, `buscar_por_assinatura()`,
     `criar_sequencia()`, `contar_sequencias()`, `matches_de()`.
   - DDL idempotente + `PRAGMA` de concorrência.
3. **18:50–19:25 — Bootstrap em `main.py`** (35 min)
   - Chamar `init_db()` após o carregamento do CSV; semear catálogo e, só na primeira
     vez, `sequencia_matches` das seeds a partir de `musica.seqs_famosas`.
   - Falhar rápido (mensagem clara) se o banco não puder ser criado/aberto.
4. **19:25–20:20 — Matching e alteração de `/similares`** (55 min)
   - `contem_subsequencia(cifra, seq)` (retorna `bool`), sem materialização no read.
   - Ramo `sequencia`: parsear tokens → `buscar_por_assinatura` → `[]` se ausente →
     `matches_de` → filtrar `apply_filtro(...)` por pertinência, preservando ordem.
5. **20:20–21:10 — Novas rotas `/sequencias`** (50 min)
   - GET e POST, validação (limites, charset, JSON inválido), dedup `409`, teto de
     catálogo, cálculo dos matches no write e `total_musicas`.
6. **21:10–22:30 — Frontend (recorte mínimo)** (1 h 20)
   - `sequencia.js`: remover `sequencia1..4`; `carregarSequencias()` via
     `GET /sequencias` normalizando para `{acorde, cor:'#2E1C74'}`; estado do formulário
     (`vm.novaSequencia`, `vm.adicionarAcorde`, `vm.removerAcorde`),
     `vm.cadastrarSequencia()` com `POST` + tratamento de `400`/`409`, e reuso de
     `vm.pesquisarPorSequencia` após o `201`.
   - `sequencia.html`: bloco de cadastro (input + adicionar + prévia `df-hex` +
     "Cadastrar e buscar") e guarda `ng-show` para `minhaSequencia.acordes` indefinido.
   - Teste manual no browser antes de seguir: cadastrar → aparece no catálogo → buscar.
7. **22:30–23:10 — Testes automatizados do backend** (40 min, regressão primeiro)
   - `tests/test_api.py` (contrato + regressão por igualdade) primeiro;
     `tests/test_matching.py` e `tests/test_persistencia.py` depois.
8. **23:10–23:35 — Verificação final e Docker** (25 min)
   - Suíte + smoke pelo browser + roteiro Docker (fresh, restart, rebuild, se der tempo).
9. **23:35–23:55 — Encerramento** (20 min)
   - Preencher `04-test-report.md` com o que rodou de verdade; commit final; 4 min de
     margem para o envio.

## Prazo e cortes

- **Prazo duro:** hoje, 23:59. Capacidade: ~6 h 40 de 17:15 a 23:55. Nada de escopo novo
  durante a execução.
- **P0 — mínimo para submeter:** fixture de regressão, `persistencia.py`, bootstrap,
  `/similares` por lookup, `GET/POST /sequencias`, catálogo dinâmico + cadastro no
  browser, teste de regressão verde.
- **P1 — cortar primeiro se atrasar:** validação completa de limites, testes unitários do
  predicado, `VOLUME`/`DECIFRAME_DB` e verificação de persistência no Docker.
- **P2 — abandonar sem culpa:** logs de boot, benchmark, `datalist` de acordes via
  `GET /acordes`, correção do bug de `vm.temAcorde`, qualquer otimização de `POST`.
- **Regra de corte 1 (21:10):** se as rotas `/sequencias` não estiverem prontas, cortar o
  formulário e entregar só o catálogo dinâmico no frontend — a busca pelas 6 continua
  demonstrável.
- **Regra de corte 2 (22:30):** se o frontend não estiver funcionando no browser, parar
  de mexer nele, deixar o legado intacto (a URL antiga continua funcionando) e ir para
  os testes do backend; registrar no relatório como "não entregue".
- **Persistência sem Docker:** se o tempo acabar, validar reiniciando `python main.py`
  com o mesmo `var/deciframe.db` — prova o requisito de sobreviver a restart sem
  depender da imagem.

## Arquivos afetados

| Arquivo | Mudança |
|---|---|
| `main.py` | bootstrap do banco, predicado de matching, ramo `sequencia` de `/similares`, rotas `GET/POST /sequencias`; remover o dict global `sequencias` do caminho de busca |
| `persistencia.py` (novo) | schema, conexão, seed, queries do catálogo e dos matches |
| `static/assets/js/controllers/sequencia.js` | catálogo dinâmico via `GET /sequencias`, estado do formulário, `vm.cadastrarSequencia()` com `POST`, remoção das 4 sequências hardcoded |
| `static/templates/sequencia.html` | bloco de cadastro (input + adicionar + prévia `df-hex` + botão), guarda de `minhaSequencia.acordes` |
| `Dockerfile` | `VOLUME ["/app/var"]` e `ENV DECIFRAME_DB=/app/var/deciframe.db` (P1) |
| `.gitignore` | ignorar `var/` (arquivo do banco local) |
| `tests/test_matching.py` (novo) | testes do predicado de subsequência |
| `tests/test_persistencia.py` (novo) | seed idempotente, dedup, persistência após reabrir |
| `tests/test_api.py` (novo) | contrato das rotas, regressão por igualdade, validação |
| `tests/fixtures/baseline_sequencias.json` (novo) | oráculo capturado do comportamento atual |
| `requirements-dev.txt` (novo) | `pytest` (dev apenas; não entra na imagem) |

**Não afetados:** `musica.py` (a cifra já está exposta), o restante de `static/`
(`app.js`, `routes.js`, diretivas, demais controllers/templates), o CSV de dados e as
colunas lidas no import. O `df-hex` continua recebendo `{acorde, cor}` — só a origem dos
dados muda.

## Riscos e mitigação

| Risco | Sinal | Mitigação |
|---|---|---|
| Volume em `/app/data` esconder o CSV (`Dockerfile` faz `COPY . .`) | boot falha com `FileNotFoundError` no dataset | volume em `/app/var`, nunca em `/app/data` |
| Snapshot das seeds divergir do matching real | buscas novas e antigas com tamanhos muito diferentes | documentado na ADR 0002; teste de igualdade fixa o comportamento |
| Ordem dos resultados mudar (quebra paginação/regressão) | fixture difere | iterar `musicas.values()` como hoje; nunca ordenar por id do banco |
| Re-seed não atualizar seeds existentes | dados do CSV novo não aparecem | `INSERT OR IGNORE` é intencional; recompute exige ADR própria |
| `POST` lento com catálogo grande | > 1 s | limite de 1.000 sequências; índice de string é otimização futura, não necessária agora |
| Corrida de escrita sob gunicorn | `database is locked` | WAL + `busy_timeout`, conexão curta por request |
| Shape de `GET /sequencias` incompatível com `df-hex` | hexes vazios/erro no console do browser | normalizar `{id, acordes:[str]}` → `{acordes:[{acorde, cor}]}` no controller; conferir no browser antes de seguir |
| Duplo clique no cadastro gera `409` na demo | erro inesperado no `esfigeSpeech` | desabilitar o botão durante a request e tratar `409` com mensagem "sequência já existe" |
| `vm.temAcorde` compara objeto com string (bug herdado, `sequencia.js:47-53`) | nenhum acorde do catálogo aparece destacado | aceitável no recorte (só afeta destaque); corrigir só se sobrar tempo (P2) |
| Frontend quebrado perto do prazo | `#/porsequencia` em branco | manter a lista hardcoded como fallback até o `GET` responder; reverter o arquivo se o corte 2 disparar |

## Testes

- **Unitário:** `contem_subsequencia` — vazio, sequência maior que a cifra, repetição
  sobreposta (`A,A` em `A,A,A`), sem match, case-sensitive (`Am` ≠ `am`), cifra vazia
  (8.141 músicas não têm cifra e nunca casam).
- **Regressão (obrigatório):** para as 6 seeds, comparar resposta atual vs. fixture em
  igualdade de JSON (não continência), com `generos` e paginação. Deve ser capturado
  **antes** da mudança (passo 1).
- **Integração:** `POST` válido → 201 e aparece no `GET`; duplicata → 409; 1 acorde,
  17 acordes, token inválido, corpo não-JSON → 400; `sequencia` desconhecida → `[]`.
- **Persistência:** criar, fechar/reabrir conexão e reiniciar o processo → sequência
  continua; `seed_catalog()` rodando 3× não duplica linhas.
- **Docker:** fresh run com volume nomeado, `docker restart`, rebuild + volume → dados
  preservados.
- **Frontend (manual, não há infra de teste JS no projeto):** abrir `#/porsequencia` com
  devtools abertos → catálogo mostra as 6 seeds (ids 0–5); cadastrar `C,G,Am,F` → `409`
  tratado; cadastrar `Dm,G,C` → aparece no catálogo → buscar → cards renderizam sem erro
  de console; recarregar a página → sequência continua listada.

## Observabilidade

- Logs de boot: caminho do banco, nº de seeds inseridas, nº de matches semeados, tempo de
  inicialização.
- Log em `POST` rejeitado (motivo e assinatura) e em erro de escrita no SQLite.
- Sem métricas/alertas: aplicação local single-container, não há coletor. Seção
  intencionalmente vazia.

## Rollout

1. Build da imagem e run com `-v deciframe-data:/app/var`.
2. Smoke: `curl /generos`, `curl /sequencias` (6 seeds), `curl "/similares?sequencia=C,G,Am,F"`.
3. Demo no browser: `#/porsequencia` lista o catálogo, cadastra uma sequência nova e busca.
4. Regressão: suíte completa + comparação com a fixture.
5. Persistência: criar sequência, `docker restart` (ou reiniciar `python main.py`),
   conferir no `GET` e no browser.
6. Rollback: voltar à imagem anterior (o arquivo do banco é inerte para o código antigo).

## Definição de pronto

Prazo é hoje 23:59: se a execução atrasar, o mínimo aceitável são os itens de P0
(catálogo persistido + `POST` + regressão das 6 seeds + busca de sequência nova) e a
suíte de regressão verde; o resto vira "documentado, não verificado" em
`04-test-report.md`.

- [x] `GET /sequencias` devolve as 6 seeds (ids 0–5, `origem=seed`).
- [x] `POST /sequencias` cria sequência, devolve `201` com `total_musicas > 0` e ela
      aparece no `GET`.
- [x] `GET /similares?sequencia=<csv>` das 6 seeds é idêntico à fixture (JSON, ordem,
      paginação, com e sem `generos`).
- [x] Sequência nova é buscável com o mesmo contrato e devolve músicas que realmente
      contêm a progressão em `cifra`.
- [x] Duplicata → 409; entradas inválidas → 400; desconhecida → `[]`.
- [x] `#/porsequencia` lista o catálogo vindo do backend e cadastra+busca uma sequência
      nova no browser; as 6 seeds continuam pesquisáveis pelo mesmo botão.
- [ ] Dados sobrevivem a `docker restart` (ou restart do processo) e a rebuild com volume.
      **Parcial:** restart do processo com o mesmo `DECIFRAME_DB` preservou os ids 6–7;
      build/run/rebuild da imagem **não verificado** (daemon Docker indisponível).
- [x] `pytest` verde; nenhum arquivo de `static/` além de `sequencia.js`/`sequencia.html`
      alterado.

## Dependências

- Runtime: nenhuma nova (`sqlite3`, `json` são stdlib). `requirements.txt` intocado.
- Dev: `pytest` em `requirements-dev.txt`.

## Segurança

- SQL sempre parametrizado; `acordes` sempre serializado como JSON, nunca concatenado.
- Validação de entrada no `POST` (limites, charset, JSON) e teto de catálogo para conter
  abuso em catálogo aberto.
- Sem autenticação por decisão do produto; rate limiting fica como lacuna conhecida
  (container local único não tem infraestrutura de limitação).

## Fora do escopo

- Redesenho visual de `#/porsequencia`, autocomplete de acordes (`datalist` via
  `GET /acordes`), correção do bug de `vm.temAcorde` e edição/exclusão de sequências.
- Migrar músicas/gêneros para o banco; sinônimos de cifra/transposição; endpoint de
  recompute dos matches.
- Qualquer arquivo de frontend além de `sequencia.js` e `sequencia.html` (`app.js`,
  `routes.js`, diretivas, `index.html`).
