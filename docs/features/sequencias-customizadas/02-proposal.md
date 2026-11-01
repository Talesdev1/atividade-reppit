# Proposta — Sequências de Acordes Customizadas

## Contexto

- **Pedido:** permitir que qualquer visitante cadastre uma sequência de acordes e busque
  músicas por ela, com o mesmo comportamento das 6 sequências de hoje; catálogo de
  sequências persistido em banco, catálogo de músicas/gêneros continuando no CSV em
  memória (`00-enunciado.md`, seções "O que você vai construir" e "O que está fixo").
- **Fonte de pesquisa:** `01-research.md`, seções 1.1 (matching por subsequência
  contígua sobre `musica.cifra`), 1.2 (validação contra o dataset), 1.3 (SQLite +
  volume), 1.4 (frontend `#/porsequencia`) e seção 2 (trade-offs já decididos).

### Achado que corrige a pesquisa (medido, não suposto)

A seção 1.2 afirma que a janela deslizante "reproduziu exatamente os mesmos conjuntos"
das tags `SEQ_FAMOSA`. **Isso não se reproduz neste dataset.** Rodei a regra da seção
1.1 sobre as 67.585 músicas e comparei com a coluna `SEQ_FAMOSA` usada hoje
(`main.py:203-223`):

| Seq | Acordes | Resultado hoje (tag) | Janela contígua | Tag ⊆ scan? | Músicas a mais |
| :-- | :-- | --: | --: | :-: | --: |
| 0 | `Bm,G,D,A` | 199 | 866 | sim | +667 |
| 1 | `C,G,Am,F` | 296 | 1.216 | sim | +920 |
| 2 | `Em,G` | 4 | 3.110 | sim | +3.106 |
| 3 | `C,A7,Dm,G7` | 5 | 96 | sim | +91 |
| 4 | `Gm,F` | 7 | 1.039 | sim | +1.032 |
| 5 | `C,C7,F,Fm` | 3 | 132 | sim | +129 |

Ou seja: a seção 1.2 está correta como **recall** (nenhuma música taggeada se perde) e
errada como **igualdade**. A coluna `SEQ_FAMOSA` é uma curadoria do dataset, não a
função "contém a progressão". Reprodução (no venv do projeto, que é o que importa
`main.py` no boot):

```python
base = {m.id_unico_musica for m in main.musicas.values() if '1' in m.seqs_famosas}
scan = {m.id_unico_musica for m in main.musicas.values() if contem(m.cifra, ['C','G','Am','F'])}
assert base <= scan and base != scan
```

Consequência direta: o requisito fixo "as 6 sequências continuam produzindo os mesmos
resultados" **não pode** ser atendido por matching em tempo real puro. Isso divide o
espaço de soluções e é o eixo das duas propostas abaixo.

## Propostas de solução (comparativo)

### Proposta 1 — Matching materializado, com snapshot congelado das 6 seeds (escolhida)

- **Overview:** o SQLite guarda o catálogo *e* o conjunto de músicas de cada sequência
  (`sequencia_matches`). As 6 seeds recebem, no bootstrap, o snapshot exato da coluna
  `SEQ_FAMOSA`; sequências novas têm seus matches calculados uma única vez, no `POST`,
  pela janela deslizante da seção 1.1. A busca vira lookup, não varredura.
- **Key Changes:** `main.py` (bootstrap e ramo `sequencia` de `/similares`), novo
  `persistencia.py`, `Dockerfile` + volume, `sequencia.js`/`sequencia.html`.
- **Trade-offs:**
  - *Prós:* paridade byte a byte com hoje (teste de regressão obrigatório passa sem
    reinterpretação); leitura O(1) no banco; um único caminho de consulta para seeds e
    sequências novas; nenhuma dependência nova.
  - *Contras:* dado derivado e persistido — o snapshot das seeds fica **intencionalmente
    defasado** em relação ao que a janela deslizante encontraria; mudanças no CSV exigem
    re-seed (`INSERT OR IGNORE` protege contra duplicação, mas não atualiza); schema maior
    (2 tabelas) e custo de escrita no `POST` (~0,5 s com scan ingênuo).
- **Validation:** regressão por igualdade de JSON (não por continência) para as 6 seeds,
  com e sem `generos`, páginas 1–3; teste unitário da janela (vazio, maior que a cifra,
  repetições sobrepostas, case-sensitive); persistência após `docker restart` e após
  rebuild; dedup/limites via `POST`; falha explícita se o banco estiver inacessível.
- **Open Questions:** aceitar o snapshot congelado como dívida permanente ou abrir ADR
  futura para migrar as seeds ao matching real (mudança visível de resultados)? Recalcular
  matches quando o CSV mudar, ou documentar "reinicie e re-seede"? Custo de escrita
  aceitável sem índice?

### Proposta 2 — Matching em tempo real uniforme, sem tabela de matches

- **Overview:** o SQLite guarda só o catálogo (listas ordenadas de acordes). Toda busca,
  inclusive as 6 originais, roda a janela deslizante sobre `musica.cifra` em memória, com
  um índice de string com sentinela construído no boot (~100 ms) para derrubar o custo.
- **Key Changes:** `main.py` (predicado + índice em memória + ramo `sequencia`), novo
  `persistencia.py` só para o catálogo, frontend igual à Proposta 1.
- **Trade-offs:**
  - *Prós:* uma única fonte de verdade (a cifra); sem dado derivado, sem staleness, schema
    mínimo (1 tabela); sequência nova fica buscável sem escrever nada além do catálogo;
    ~20 ms por busca medida (vs. 450–480 ms com `cifra[i:i+n]` ingênuo).
  - *Contras:* **quebra a igualdade da regressão** — as 6 seeds passam a devolver supersets
    (+91 a +3.106 músicas, tabela acima), o que exige aprovação explícita de mudança de
    comportamento; ~20 MB extras de índice em memória; custo cresce com o catálogo.
- **Validation:** regressão por **continência** (`hoje ⊆ novo`) + spot-check musical de
  amostras dos novos hits; benchmark por requisição; teste do predicado; teste de que o
  índice não altera resultados vs. scan ingênuo.
- **Open Questions:** o dono do produto aceita superset nas 6? Se sim, isso vira ADR de
  mudança de contrato (e o teste de regressão do enunciado precisa ser reescrito).

**Por que a Proposta 1 vence:** o critério de regressão é requisito *fixo* do enunciado
("não é decisão sua"), e a Proposta 2 só o atende renegociando o requisito. A Proposta 1
custa uma tabela derivada e um snapshot documentado; a Proposta 2 custa reescrever o
critério de aceitação. Fico com a primeira e registro a dívida na ADR 0002.

## Abordagem escolhida

### Algoritmo de matching

Uma sequência `S = [s0..s(n-1)]` "aparece" na música `m` se, e somente se, `S` for uma
**subsequência contígua** de `m.cifra` (lista ordenada de tokens, `musica.py:16`):

```
match(S, m) = ∃ i ∈ [0, len(m.cifra) - n] : m.cifra[i : i+n] == S
```

- `n == 0` ou `n > len(m.cifra)` ⇒ falso; `n == 1` é rejeitado na entrada (busca de acorde
  único já existe em `/similares?acordes=`).
- Fonte é `m.cifra`, **nunca** `m.acordes` (`musica.py:17` faz `list(set(...))` e perde
  ordem/repetição).
- Normalização da consulta: `split(',')` → `strip()` em cada token → descarta vazios.
  Comparação *case-sensitive* (`Am` ≠ `A`), sem remoção de combinantes (aquilo é para
  busca textual, `main.py:145-147`) e sem tabela de sinônimos (`C7M` ≠ `Cmaj7`).
- Chave canônica da sequência: `','.join(tokens)` — o mesmo texto que o frontend já envia
  hoje (`sequencia.js:55-61`), o que mantém a URL legada válida.
- Limites de entrada: 2 a 16 acordes, cada token com 1–12 caracteres do vocabulário
  observado no dataset (`E/B`, `F#/Bb`, `C#m7`, `Bb7M/5-`); catálogo limitado a 1.000
  sequências (catálogo é aberto e anônimo).

### Banco de dados

**SQLite** (`sqlite3`, stdlib), arquivo em `DECIFRAME_DB` (default
`/app/var/deciframe.db`), por três razões da pesquisa §1.3: zero dependências no
`Dockerfile`, transações ACID sob concorrência do gunicorn e aderência à ADR 0001
(container único, local-only). Conexão por request (`contextmanager`), `PRAGMA
journal_mode=WAL` e `busy_timeout=5000`.

Ponto de atenção que a pesquisa não cobriu: **não montar volume em `/app/data`** — o
`Dockerfile:7` faz `COPY . .`, e um volume ali esconderia `data/top/dataset_final.csv`,
derrubando o boot. Por isso o diretório separado `/app/var` (com `VOLUME /app/var`).

O CSV continua sendo a fonte de músicas/gêneros; o banco guarda só o catálogo de
sequências e os matches derivados (Proposta 1).

### Esquema de dados (alto nível)

```sql
CREATE TABLE sequencias (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  assinatura  TEXT NOT NULL UNIQUE,        -- "C,G,Am,F"
  acordes     TEXT NOT NULL,               -- JSON array ordenado: ["C","G","Am","F"]
  origem      TEXT NOT NULL CHECK (origem IN ('seed','usuario')),
  criada_em   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE sequencia_matches (
  sequencia_id    INTEGER NOT NULL REFERENCES sequencias(id) ON DELETE CASCADE,
  id_unico_musica TEXT NOT NULL,           -- casa com Musica.id_unico_musica (musica.py:20)
  PRIMARY KEY (sequencia_id, id_unico_musica)
);
```

Bootstrap idempotente: `INSERT OR IGNORE` das 6 seeds com ids fixos 0–5 (preserva o
significado dos ids antigos), acordes transcritos da pesquisa §1.2, e — só na primeira
vez — `sequencia_matches` preenchida a partir de `musica.seqs_famosas`. O dicionário
global `sequencias` (`main.py:40-45`) deixa de existir no caminho de busca; a coluna
`SEQ_FAMOSA` continua sendo lida do CSV apenas como fonte do snapshot (e no teste de
regressão). Ordenação dos resultados continua vindo de `musicas.values()` (popularidade
desc, `main.py:88-89`), o que reproduz exatamente a ordem de hoje.

### API

Tudo continua saindo como `json.dumps(...)` (string, `Content-Type: text/html`), conforme
o requisito fixo.

- `GET /sequencias` → `[{id, acordes, origem, criada_em}]`, ordenado por `id`.
- `POST /sequencias` — corpo `{"acordes": ["C","G","Am","F"]}`.
  - `201` → `{id, acordes, origem, criada_em, total_musicas}` (matches já calculados).
  - `400` → `{erro}` para lista vazia/1 acorde/>16, token inválido, corpo não-JSON.
  - `409` → `{erro, id}` quando `assinatura` já existe (mesma ordem exata; ordem diferente
    é sequência diferente).
  - `507`/`429` → catálogo cheio (limite de 1.000).
- `GET /similares` (alterado só no ramo `sequencia`): parseia os tokens, busca a
  `assinatura`; se não existir, responde `[]` — **igual ao comportamento de hoje** para
  tag desconhecida (`main.py:190-197`); se existir, lê `sequencia_matches` para um `set`
  de ids e filtra `apply_filtro(musicas.values(), generos_key)` por pertinência,
  preservando ordem e paginação atuais. Campos por música idênticos aos de
  `get_similares_por_sequencia` (`main.py:210-220`), para o card do template não mudar.

### Frontend

Em `static/assets/js/controllers/sequencia.js`:

- Remover `sequencia1..4` e popular `vm.sequenciasFamosas` com `GET /sequencias`,
  normalizando para o shape que o `df-hex` já consome (`{acorde, cor:'#2E1C74'}`).
- Corrigir o bug de `vm.temAcorde` (`sequencia.js:47-53`): comparar `acordeon.acorde`, não
  o objeto; remover o campo morto `'index'` (`sequencia.js:3`).
- `vm.cadastrarSequencia()`: monta a lista a partir da seleção/entrada, faz `POST`,
  trata `400`/`409` em `vm.esfigeSpeech`, recarrega o catálogo e — se `201` — chama
  `vm.pesquisarPorSequencia` com a sequência recém-criada.
- Manter `createChordsString` como está: o texto gerado é exatamente a `assinatura`.

Em `static/templates/sequencia.html`:

- Bloco de cadastro (input de acorde + botão adicionar + prévia em `df-hex` + "Cadastrar
  e buscar"), com `datalist` alimentado por `GET /acordes` (6.653 tokens únicos já
  expostos por `main.py:162-164`).
- O `ng-repeat` do catálogo (linha 6) passa a refletir o backend sem mudança de markup;
  a divergência 4-vs-6 da pesquisa §1.4 desaparece por construção.
- Guardas para `Sequencia.minhaSequencia.acordes` indefinido (hoje `sequencia.html:19`
  assume que existe) e estado vazio/erro.

## Alternativas consideradas e descartadas

| Alternativa | Por que foi descartada |
| :-- | :-- |
| **Manter a tag `SEQ_FAMOSA` como motor de busca** | Só funciona para as 6 sequências do CSV; sequência nova não teria tag. Além disso, a tabela acima mostra que a tag não é a definição de "contém a progressão" — é curadoria. |
| **Dois motores (tag para seeds, scan para novas)** | Preserva a regressão sem materializar, mas cria duas semânticas para o mesmo botão da UI e mantém a coluna `SEQ_FAMOSA` como caminho de produção. A Proposta 1 tem o mesmo efeito de compatibilidade com um único caminho de leitura. |
| **Subsequência não-contígua / interseção de conjuntos** | Já descartadas na pesquisa §2.1: a primeira gera falsos positivos em sequências curtas; a segunda perde ordem e repetição. |
| **DuckDB ou JSON/TinyDB** | Já descartadas na pesquisa §2.2: dependência pesada sem ganho, ou ausência de concorrência/transação com o gunicorn. |
| **Lista estática no JS + cadastro só via API** | Já descartada na pesquisa §2.3: o usuário não veria nem buscaria as sequências novas. |
| **Tabela normalizada `sequencia_acordes(seq_id, posicao, acorde)`** | Ordem e integridade ficam garantidas pelo schema, mas exige 3–4× mais linhas, `JOIN` com agregação para reconstruir a lista e não traz benefício de consulta (o matching usa a lista inteira). O JSON ordenado em `sequencias.acordes` é suficiente e atômico. |
| **Normalizar sinônimos de cifra (`C7M`↔`Cmaj7`) e transposição** | Sem tabela de equivalência no sistema original (pesquisa §1.1) e sem dados para validar; muda o resultado das 6 seeds. Fora de escopo, candidato a pesquisa futura. |

## Escopo explícito

**Dentro do escopo:**

- Catálogo de sequências em SQLite (`sequencias` + `sequencia_matches`), com as 6 seeds
  migradas e snapshot de compatibilidade.
- `GET /sequencias`, `POST /sequencias` e ramo `sequencia` de `/similares` por lookup,
  preservando `json.dumps`, paginação, filtro por gênero e o shape dos cards.
- Validação de entrada anônima (2–16 acordes, charset, limite de catálogo, dedup 409).
- Frontend `#/porsequencia` dinâmico, com cadastro e busca pela sequência recém-criada.
- `VOLUME /app/var` + `DECIFRAME_DB` no `Dockerfile`/instruções de execução, ADR 0002.
- Testes automatizados do predicado, da regressão por igualdade e da persistência.

**Fora do escopo (e por quê):**

- Migrar músicas/gêneros para o banco — proibido pelo enunciado; o CSV segue em memória.
- Editar/apagar sequências existentes, moderação ou login — o catálogo é aberto e
  anônimo; qualquer fluxo de curadoria exigiria identidade, que não existe no app.
- Sinônimos de notação, transposição e matching não-contíguo — sem dados/regra validada e
  mudaria os resultados das 6 seeds.
- Reescrever o stack AngularJS ou o padrão `json.dumps` — congelados por ADR 0003 e pelo
  enunciado.
- Reescrever as 6 seeds para matching real — é a dívida registrada na ADR 0002; exige
  aprovação da mudança de resultados.
