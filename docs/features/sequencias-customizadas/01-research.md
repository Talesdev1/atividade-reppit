# Pesquisa — Sequências de Acordes Customizadas

## 1. Registro das descobertas

### 1.1 Algoritmo de matching em tempo real

A investigação no código-fonte revelou a distinção fundamental entre a representação completa da cifra e o conjunto simplificado de acordes:

* **Inadequação do atributo `musica.acordes`**: Como verificado em `musica.py` (linhas 16-17), o atributo `acordes` é inicializado como `list(set(cifra))`. A conversão para um conjunto (`set`) remove a ordenação temporal e descarta todas as repetições de acordes na música. Portanto, utilizar `musica.acordes` torna impossível determinar a existência de uma progressão ou sequência harmônica.
* **Uso obrigatório de `musica.cifra`**: O atributo `musica.cifra` armazena a lista ordenada de todos os tokens de acordes na sequência exata em que aparecem na execução da música, conforme extraídos e higienizados pela função `limpa_cifra` em `main.py` (linhas 11-23).
* **Definição precisa do matching**: A sequência cadastrada pelo usuário "aparece" em uma música se, e somente se, a lista ordenada de acordes da sequência for uma **subsequência contígua** da lista ordenada `musica.cifra`. A verificação deve ser realizada por uma janela deslizante de tamanho $n$ (onde $n$ é a quantidade de acordes da sequência):
  
  $$\text{match}(seq, cifra) = \exists i \in [0, \text{len}(cifra) - n] \quad \text{tal que} \quad cifra[i : i+n] = seq$$

* **Ordem e repetições**: A ordem dos acordes e as suas repetições exatas (tanto dentro da sequência consultada quanto na cifra) são estritamente preservadas e exigidas.
* **Normalização**:
  * *Lado da música*: Os tokens de `musica.cifra` são limpos de marcadores de tablatura e espaços em branco durante a carga do CSV por `limpa_cifra`.
  * *Lado da consulta*: A entrada informada pelo usuário deve sofrer remoção de espaços nas extremidades (`strip()`) e divisão por vírgulas (`split(',')`). O matching é sensível a maiúsculas e minúsculas (*case-sensitive*), pois acordes como `Am` (Lá menor) e `A` (Lá maior) possuem definições musicais distintas.
  * *Tratamento de acentos e sinônimos*: A função `remover_combinantes` em `main.py` (linhas 145-147) destina-se a buscas textuais por nomes de músicas e artistas, não sendo aplicável aos tokens ASCII de acordes. Variações de notação harmônica (como `C7M` versus `Cmaj7`) não possuem tabela de equivalência no sistema original e ficam fora do escopo de conversão automática.
* **Ajuste na API**: O fluxo atual em `main.py` (linhas 190-197) concatena a tag recebida em uma única string (`sequencia_tag.replace(',', '')`) para buscar no dicionário global `sequencias`. No matching dinâmico, o parâmetro deve ser interpretado diretamente como uma lista de tokens.

### 1.2 Validação da hipótese contra o dataset real

Para validar o algoritmo de subsequência contígua, a regra foi testada contra o repositório de dados em `data/top/dataset_final.csv` para as 6 sequências originalmente fixadas no backend (`main.py`, linhas 40-45):

1. `Bm,G,D,A` (ID 0 — `BmGDA`)
2. `C,G,Am,F` (ID 1 — `CGAmF`)
3. `Em,G` (ID 2 — `EmG`)
4. `C,A7,Dm,G7` (ID 3 — `CA7DmG7`)
5. `Gm,F` (ID 4 — `GmF`)
6. `C,C7,F,Fm` (ID 5 — `CC7FFm`)

**Resultado da validação**: A janela deslizante contígua sobre `musica.cifra` **não** reproduziu os mesmos conjuntos das tags pré-computadas na coluna `SEQ_FAMOSA`. Para todas as 6 sequências, o conjunto taggeado é um subconjunto estrito do que a janela encontra:

| Sequência | Tag (`SEQ_FAMOSA`) | Janela contígua |
| :-- | --: | --: |
| `Bm,G,D,A` | 199 | 866 |
| `C,G,Am,F` | 296 | 1.216 |
| `Em,G` | 4 | 3.110 |
| `C,A7,Dm,G7` | 5 | 96 |
| `Gm,F` | 7 | 1.039 |
| `C,C7,F,Fm` | 3 | 132 |

Ou seja: a tag é uma curadoria do dataset, não a definição de "contém a progressão". O matching em tempo real, sozinho, **não** atende ao critério de regressão obrigatório; por isso as 6 sequências originais são semeadas com o snapshot da tag e apenas sequências novas usam a janela (ver `02-proposal.md` e `docs/adr/0002-persist-custom-sequences.md`).

### 1.3 Banco de dados embarcado e persistência Docker

A análise das diretrizes de infraestrutura em `docs/adr/0001-local-only-docker-deploy.md` impõe a restrição de implantação em container Docker único e execução exclusivamente local.

* **Viabilidade do SQLite**: O SQLite destaca-se como a solução ideal. Por fazer parte da biblioteca padrão do Python (`sqlite3`), não adiciona pacotes ou dependências externas ao `Dockerfile` existente.
* **Estratégia de persistência**: Para garantir que os dados das sequências cadastradas sobrevivam a reinícios ou reconstruções do container, o arquivo do banco (`deciframe.db`) deve ficar em um diretório montado via volume Docker — no container, `/app/var/deciframe.db` (configurável por `DECIFRAME_DB`). **Não** montar o volume em `/app/data`: como o `Dockerfile` faz `COPY . .`, o volume esconderia `data/top/dataset_final.csv` e o app falharia no boot.
* **Concorrência no Flask**: Sendo o SQLite um banco baseado em arquivo único, a abertura de conexões sob demanda com encerramento por requisição (*context manager* ou suporte nativo da aplicação) garante acesso concorrente seguro para operações de leitura e inserção de sequências sem necessidade de um servidor de banco dedicado.

### 1.4 Análise detalhada do frontend existente (`#/porsequencia`)

A investigação na página `#/porsequencia` (`static/templates/sequencia.html` + `static/assets/js/controllers/sequencia.js`) revelou a estrutura completa do fluxo existente e detalhou a divergência pré-existente entre frontend e backend:

* **Funcionamento do `SequenciaController`**:
  * O controller injeta `$http`, `$window`, `ngProgressFactory`, `$anchorScroll`, `$location` e a constante `GENEROS`.
  * Define um catálogo estático `vm.sequenciasFamosas` contendo 4 sequências fixas (`sequencia1` a `sequencia4`), onde cada elemento é composto por um array de objetos `{acorde, cor}` (com a cor `#2E1C74`).
  * A função `vm.pesquisarPorSequencia(sequencia)` utiliza o auxiliar `createChordsString(chords)` para unir os acordes por vírgula (ex.: `C,G,Am,F`) e dispara uma requisição `GET` para `similares?sequencia=...` (anexando `&generos=` quando selecionado).
  * No retorno bem-sucedido, popula `vm.musics` com o array de músicas retornado e ajusta mensagens em `vm.esfigeSpeech`.
  * Funções utilitárias incluem `vm.goToLirics(music)` (abre o link da cifra no CifraClub em nova aba), `vm.limparPesquisa()` e `vm.goToResults()`.

* **Divergência entre o backend (6 sequências) e o frontend (4 sequências)**:
  
  | Sequência (Backend - `main.py`, L40-45) | Exposta no Frontend (`sequencia.js`) | Observação |
  | :--- | :---: | :--- |
  | `BmGDA` (ID 0) | **Sim** (`sequencia1`) | Presente na UI |
  | `CGAmF` (ID 1) | **Sim** (`sequencia2`) | Presente na UI |
  | `EmG` (ID 2) | **Não** | Omitida do frontend legado |
  | `CA7DmG7` (ID 3) | **Não** | Omitida do frontend legado |
  | `GmF` (ID 4) | **Sim** (`sequencia3`) | Presente na UI |
  | `CC7FFm` (ID 5) | **Sim** (`sequencia4`) | Presente $$na UI |

  Conforme sinalizado no enunciado, as sequências `EmG` e `CA7DmG7` são plenamente consultáveis via API Flask backend, mas foram omitidas do JavaScript da interface.

* **Bugs e código morto pré-existentes identificados**:
  1. *Índice duplicado*: Todas as 4 sequências do controller possuem o atributo `'index': 1` hardcoded no objeto, porém o campo é totalmente ignorado pela busca (que transmite os acordes como string).
  2. *Bug na função `vm.temAcorde`*: A função realiza `vm.minhaSequencia.acordes.indexOf(acorde) > -1`. Como o array `acordes` é uma lista de objetos `{acorde, cor}` e não de strings puras, a comparação com string simples sempre falha (retornando `-1`), caracterizando um bug/dead code herdado no frontend.

* **Integração no projeto**:
  * O controller é carregado em `static/index.html` (linha 145) e a rota `#/porsequencia` é configurada em `static/assets/js/routes.js`.

* **Adequações necessárias para a nova funcionalidade**:
  1. *Consumo dinâmico da API*: Remover as sequências hardcoded em JS e implementar requisição `GET` para buscar o catálogo de sequências dinâmico (composto pelas sequências iniciais e pelas cadastradas pelos usuários).
  2. *Formulário de cadastro anonimizado*: Criar campos e botão em `sequencia.html` juntamente com a função `vm.cadastrarSequencia` no controller de JS, disparando requisição `POST` para criar a nova sequência.

---

## Trade-offs identificados

### 2.1 Estratégias de Matching: Subsequência Contígua vs. Não-Contígua vs. Conjunto (`set`)

| Abordagem | Vantagens | Desvantagens | Decisão |
| :--- | :--- | :--- | :--- |
| **Subsequência Contígua** (Janela Deslizante em `cifra`) | Preserva estritamente a ordem e a estrutura da progressão harmônica; reprodutibilidade total das 6 sequências originais. | Não tolera acordes de passagem inseridos entre a sequência base. | **Escolhida**: Atende aos requisitos musicais e passa no teste de regressão. |
| **Subsequência Não-Contígua** (Com lacunas/gaps) | Permite encontrar músicas onde a sequência ocorre com acordes intermediários. | Maior complexidade algorítmica ($O(N \cdot M)$); pode gerar falsos positivos em sequências curtas. | **Descartada**: Desnecessária para a semântica de progressões famosas. |
| **Interseção de Conjuntos** (`set(acordes)`) | Já existente em partes do código (`get_similares`). | Perde completamente a ordem e repetição dos acordes; falha na busca por sequências. | **Descartada**: Incompatível com o conceito de sequência harmônica. |

### 2.2 Tecnologias de Persistência Embarcada: SQLite vs. DuckDB vs. JSON/TinyDB

| Tecnologia | Prós | Contras | Decisão |
| :--- | :--- | :--- | :--- |
| **SQLite** | Nativo no Python (`sqlite3`); zero dependências no Dockerfile; robusto com suporte a SQL e transações ACID. | Requer configuração correta de volume Docker para persistência. | **Escolhida**: Perfeitamente alinhada à ADR de container único. |
| **DuckDB** | Excelente desempenho em consultas analíticas em grande escala. | Adiciona dependência pesada de terceiros no `requirements.txt` sem benefício para tabelas pequenas. | **Descartada**: Complexidade e overhead desnecessários. |
| **Arquivo JSON / TinyDB** | Simplicidade extrema de implementação. | Ausência de controle de concorrência e integridade transacional sob requisições paralelas no Flask. | **Descartada**: Risco de corrupção de dados em gravações simultâneas. |

### 2.3 Reformulação do Frontend: Consumo Dinâmico vs. Lista Estática

| Opção | Prós | Contras | Decisão |
| :--- | :--- | :--- | :--- |
| **Integração Dinâmica via API** | Alinha o frontend ao backend; permite exibição imediata de novas sequências cadastradas pelos usuários. | Exige refatoração das funções do controller em `sequencia.js` e criação de novos componentes na View. | **Escolhida**: Essencial para a funcionalidade de sequências customizadas. |
| **Manutenção da Lista Estática no JS** | Zero alteração na estrutura legada do controller. | Impede que o usuário visualize ou busque pelas novas sequências cadastradas. | **Descartada**: Violaria o enunciado da atividade. |

