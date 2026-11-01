# Relatório de testes — Sequências de Acordes Customizadas

## Cobertura

Suíte em `tests/`, 38 testes, todos verdes com `PYTHONHASHSEED=0`.

| Arquivo | O que verifica |
|---|---|
| `tests/test_matching.py` (11) | `contem_subsequencia`: match exato, no meio da cifra, ordem, contiguidade (sem lacunas), sequência maior que a cifra, repetição sobreposta (`A,A` em `A,A,A`), case-sensitive (`Am` ≠ `am`), cifra vazia, sequência vazia |
| `tests/test_api.py` (15) | regressão contra a fixture (54 casos), catálogo com as 6 seeds, `POST` válido (`201` + `total_musicas`), duplicata (`409` com `id`), 6 entradas inválidas (`400`), corpo não-JSON (`400`), busca por sequência nova (ordem e paginação), busca com `generos` + página 2, sequência desconhecida (`[]`), `Content-Type: text/html` do `json.dumps` |
| `tests/test_persistencia.py` (12) | seed idempotente (6 seeds, 0 na segunda chamada), criação + lookup por assinatura + matches, duplicata por ordem exata (e ordem diferente = outra sequência), persistência após reabrir o banco, validação de entrada (7 casos), tokens reais do dataset (`F#/Bb`, `Bb7M/5-`) |

Fluxo de browser verificado manualmente com Chromium headless via CDP, contra o
servidor real (`python main.py`, banco em `/tmp`):

1. `#/porsequencia` renderiza as 6 seeds vindas de `GET /sequencias` (20 hexes + navbar).
2. Digitar `Dm`, `G`, `C` + "Adicionar" monta a prévia na ordem certa.
3. "Cadastrar e buscar" → `201`, catálogo recarrega com 7 sequências, a nova fica
   selecionada e a busca devolve 100 músicas (`esfigeSpeech = "Encontrei essas músicas"`).
4. Repetir o cadastro → `409` e mensagem "Essa sequência já está no catálogo." sem
   duplicar no catálogo.
5. Reiniciar o processo com o mesmo `DECIFRAME_DB` → as sequências criadas continuam
   lá (`ids` 6 e 7, `origem=usuario`).

## Teste de regressão obrigatório

As 6 sequências originais (`main.py`, linhas 40-45) precisam continuar retornando os
mesmos resultados de antes da migração para o banco de dados.

**Como foi verificado:** antes de qualquer alteração no código, capturei a resposta de
`GET /similares` para as 6 sequências em 54 casos — 6 sequências × 3 filtros de gênero
(sem filtro, `MPB`, `Rock,Sertanejo`) × 3 páginas — em
`tests/fixtures/baseline_sequencias.json`. O teste
`test_regressao_igualdade_com_fixture` compara a resposta atual byte a byte com a
fixture, inclusive ordem e paginação.

**Resultado: 54/54 casos idênticos.**

Duas descobertas durante essa verificação, ambas registradas por honestidade:

1. **A ordem depende de `set()`.** `apply_filtro` (`main.py:266-272`) itera o `set` de
   gêneros e `musica.acordes` vem de `list(set(cifra))` (`musica.py:17`). Sem filtro de
   gênero, a ordem das músicas e a ordem dos acordes de cada música variam entre
   processos (hash randomization). Não é regressão da mudança — é comportamento
   pré-existente. A fixture e a suíte rodam com `PYTHONHASHSEED=0`; sem essa variável o
   teste de regressão **falha** com uma mensagem pedindo o comando correto (em vez de
   ser skipado silenciosamente).
2. **A tag `SEQ_FAMOSA` não é a janela deslizante.** A pesquisa (§1.2) afirmava
   igualdade; na prática a tag é um subconjunto estrito (199 vs. 866 músicas para
   `Bm,G,D,A`, etc.). Por isso as 6 seeds são semeadas com o snapshot da tag (paridade
   byte a byte) e só as sequências novas usam o matching em tempo real. A dívida está
   documentada na ADR 0002.

## Cobertura de código

Medida com `coverage` (branch coverage) sobre a suíte inteira, restrita ao código de
produção:

```
pip install coverage                     # ainda não está no requirements-dev.txt
PYTHONHASHSEED=0 python -m coverage run --branch \
  --source=main,persistencia,musica -m pytest -q
python -m coverage report -m
```

| Arquivo | Stmts | Cobertos | Branches parciais | Cobertura |
| :-- | --: | --: | --: | --: |
| `main.py` | 189 | 145 | 5 | 75% |
| `persistencia.py` | 120 | 115 | 3 | 95% |
| `musica.py` | 16 | 15 | 0 | 94% |
| **Total** | **325** | **275** | **8** | **83%** |

O número agregado de `main.py` é puxado por código **legado** que nenhum teste cobre
(`/search`, `/musicas`, `/generos`, `/acordes`, `/musica/<id>/` e os ramos
`?acordes=`/`?id_unico_musica=` de `/similares`, `main.py:207-212` e `:221-223`).
Isolando só o **código novo** (linhas adicionadas no diff + `persistencia.py` inteiro):
**153/162 = 94%** (`main.py` 38/42, `persistencia.py` 115/120).

O que segue sem cobertura **no código novo**:

| Linha | O que é |
| :-- | :-- |
| `persistencia.py:186` | `raise CatalogoCheio()` |
| `main.py:248-249` | resposta `429` do `POST` (mesma causa) |
| `persistencia.py:198-203` | fallback de `IntegrityError` na corrida entre POSTs iguais |
| `main.py:117-118` | falha ao abrir/criar o banco no boot |
| `persistencia.py:91` | `if _caminho is None: init_db()` dentro de `get_conn` (inalcançável no fluxo normal, já que o import chama `init_db`) |

O caminho `429` é o mais relevante dos cinco: é a única proteção do catálogo aberto e
não é exercitada. O risco maior, porém, está nos ramos legados de `/similares`: eles
ficam na função que a feature reescreveu e alimentam `#/poracordes` e `#/pormusica`, mas
nenhum teste falha se a ordem do `if/elif` ou o fall-through quebrar.

Frontend continua em **0% automatizado** — nem JS nem CSS (ver "O que ficou de fora").

## Como rodar

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
PYTHONHASHSEED=0 python -m pytest
```

Para o fluxo manual:

```
python main.py                # :5000, banco em var/deciframe.db
# ou
docker build -t ciframe . && docker run -p 8080:8080 -v deciframe-data:/app/var ciframe
```

## O que ficou de fora

- **Docker não verificado**: o daemon não está disponível neste ambiente
  (`/var/run/docker.sock` ausente). O requisito de persistência foi provado reiniciando
  o processo `python main.py` com o mesmo `DECIFRAME_DB`, não com `docker restart` /
  rebuild. A imagem foi alterada (`VOLUME /app/var` + `ENV DECIFRAME_DB`), mas não
  exercitada.
- **Sem teste automatizado de JavaScript**: o projeto não tem infra de teste de
  frontend; o fluxo foi validado manualmente no Chromium (5 passos acima), o que cobre o
  caminho feliz e o `409`, mas não regressões visuais.
- **Sem rate limiting**: catálogo aberto e anônimo; só há teto de 1.000 sequências e
  validação de formato. Abuso por volume de requisições não é contido.
- **Seeds não recalculam**: se o CSV mudar, as 6 seeds continuam com o snapshot antigo
  (`INSERT OR IGNORE`); recomputar exigiria decisão registrada em ADR.
- **`coverage` não é dependência de dev**: a medição acima exige `pip install coverage`
  manual; não está em `requirements-dev.txt` nem há `.coveragerc` versionado, então os
  números dependem do comando colado aqui.
- **Sem sinônimos/transposição**: `C7M` ≠ `Cmaj7`, como decidido na pesquisa; nenhum
  teste cobre equivalência que não existe.
- **`vm.temAcorde`**: o bug de comparação foi corrigido no controller, mas não há teste
  automatizado para ele (só verificação visual do destaque dos hexes).
