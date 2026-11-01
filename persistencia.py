# coding: utf-8
"""Persistência do catálogo de sequências de acordes customizadas.

Só o catálogo de sequências (e os matches derivados) vive aqui: o catálogo de
músicas/gêneros continua vindo do CSV carregado em memória por ``main.py``.
O banco é um único arquivo SQLite (stdlib), apontado por ``DECIFRAME_DB``.
"""
import json
import os
import re
import sqlite3
from contextlib import contextmanager

DEFAULT_DB_PATH = os.environ.get('DECIFRAME_DB', os.path.join('var', 'deciframe.db'))

# ids fixos preservam o significado das tags antigas (main.py, linhas 40-45).
SEQUENCIAS_SEED = (
    (0, ['Bm', 'G', 'D', 'A']),
    (1, ['C', 'G', 'Am', 'F']),
    (2, ['Em', 'G']),
    (3, ['C', 'A7', 'Dm', 'G7']),
    (4, ['Gm', 'F']),
    (5, ['C', 'C7', 'F', 'Fm']),
)

MIN_ACORDES = 2
MAX_ACORDES = 16
MAX_CARACTERES_TOKEN = 12
LIMITE_SEQUENCIAS = 1000

# token de acorde: sem espaço, vírgula ou ponto e vírgula (separadores da API).
_TOKEN_VALIDO = re.compile(r'^[^\s,;]{1,%d}$' % MAX_CARACTERES_TOKEN)

SCHEMA = """
CREATE TABLE IF NOT EXISTS sequencias (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  assinatura TEXT NOT NULL UNIQUE,
  acordes TEXT NOT NULL,
  origem TEXT NOT NULL CHECK (origem IN ('seed', 'usuario')),
  criada_em TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sequencia_matches (
  sequencia_id INTEGER NOT NULL REFERENCES sequencias(id) ON DELETE CASCADE,
  id_unico_musica TEXT NOT NULL,
  PRIMARY KEY (sequencia_id, id_unico_musica)
);

CREATE INDEX IF NOT EXISTS idx_matches_musica
  ON sequencia_matches (id_unico_musica);
"""

_caminho = None


class ErroDeValidacao(ValueError):
    """Entrada de sequência inválida (vira 400 na API)."""


class SequenciaDuplicada(Exception):
    """Já existe uma sequência com a mesma ordem exata de acordes (409)."""

    def __init__(self, seq_id):
        super(SequenciaDuplicada, self).__init__('sequência já cadastrada')
        self.seq_id = seq_id


class CatalogoCheio(Exception):
    """Catálogo atingiu LIMITE_SEQUENCIAS (503/429 na API)."""


def init_db(caminho=None):
    """Cria/abre o banco e garante o schema. Devolve o caminho usado."""
    global _caminho
    _caminho = caminho or DEFAULT_DB_PATH
    diretorio = os.path.dirname(os.path.abspath(_caminho))
    os.makedirs(diretorio, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)
    return _caminho


def caminho_db():
    return _caminho or DEFAULT_DB_PATH


@contextmanager
def get_conn():
    """Conexão curta por request, com commit/rollback automáticos."""
    if _caminho is None:
        init_db()
    conn = sqlite3.connect(_caminho, timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=5000')
        conn.execute('PRAGMA foreign_keys=ON')
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def assinatura_de(acordes):
    """Chave canônica: o mesmo texto CSV que o frontend já envia hoje."""
    return ','.join(acordes)


def normalizar_acordes(entrada):
    """Valida e normaliza a lista ordenada de acordes recebida pela API."""
    if not isinstance(entrada, (list, tuple)):
        raise ErroDeValidacao('acordes deve ser uma lista')
    acordes = []
    for token in entrada:
        if not isinstance(token, str):
            raise ErroDeValidacao('cada acorde deve ser uma string')
        token = token.strip()
        if not token:
            raise ErroDeValidacao('acorde vazio')
        if not _TOKEN_VALIDO.match(token):
            raise ErroDeValidacao(
                'acorde inválido: %r (máx. %d caracteres, sem espaço, vírgula ou ;)'
                % (token, MAX_CARACTERES_TOKEN))
        acordes.append(token)
    if len(acordes) < MIN_ACORDES:
        raise ErroDeValidacao('sequência precisa de ao menos %d acordes' % MIN_ACORDES)
    if len(acordes) > MAX_ACORDES:
        raise ErroDeValidacao('sequência aceita no máximo %d acordes' % MAX_ACORDES)
    return acordes


def parsear_sequencia(texto):
    """Transforma 'C, G,Am' na lista ['C', 'G', 'Am'] (sem validar limites)."""
    return [token.strip() for token in (texto or '').split(',') if token.strip()]


def _serializar(row, total_musicas=None):
    sequencia = {
        'id': row['id'],
        'acordes': json.loads(row['acordes']),
        'origem': row['origem'],
        'criada_em': row['criada_em'],
    }
    if total_musicas is not None:
        sequencia['total_musicas'] = total_musicas
    return sequencia


def listar_sequencias():
    with get_conn() as conn:
        rows = conn.execute('SELECT * FROM sequencias ORDER BY id').fetchall()
    return [_serializar(row) for row in rows]


def buscar_por_assinatura(assinatura):
    with get_conn() as conn:
        row = conn.execute(
            'SELECT id FROM sequencias WHERE assinatura = ?', (assinatura,)
        ).fetchone()
    return row['id'] if row else None


def contar_sequencias():
    with get_conn() as conn:
        return conn.execute('SELECT COUNT(*) FROM sequencias').fetchone()[0]


def matches_de(seq_id):
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT id_unico_musica FROM sequencia_matches WHERE sequencia_id = ?',
            (seq_id,),
        ).fetchall()
    return {row['id_unico_musica'] for row in rows}


def criar_sequencia(acordes, matches):
    """Persiste a sequência e o conjunto de músicas já calculado (write-time)."""
    acordes = normalizar_acordes(acordes)
    assinatura = assinatura_de(acordes)
    with get_conn() as conn:
        if conn.execute('SELECT COUNT(*) FROM sequencias').fetchone()[0] >= LIMITE_SEQUENCIAS:
            raise CatalogoCheio()
        existente = conn.execute(
            'SELECT id FROM sequencias WHERE assinatura = ?', (assinatura,)
        ).fetchone()
        if existente:
            raise SequenciaDuplicada(existente['id'])
        try:
            cur = conn.execute(
                "INSERT INTO sequencias (assinatura, acordes, origem) "
                "VALUES (?, ?, 'usuario')",
                (assinatura, json.dumps(acordes)),
            )
        except sqlite3.IntegrityError:
            # corrida entre dois POSTs iguais: o UNIQUE decide, o perdedor vira 409.
            row = conn.execute(
                'SELECT id FROM sequencias WHERE assinatura = ?', (assinatura,)
            ).fetchone()
            raise SequenciaDuplicada(row['id'] if row else None)
        seq_id = cur.lastrowid
        conn.executemany(
            'INSERT OR IGNORE INTO sequencia_matches (sequencia_id, id_unico_musica) '
            'VALUES (?, ?)',
            [(seq_id, musica_id) for musica_id in matches],
        )
        row = conn.execute('SELECT * FROM sequencias WHERE id = ?', (seq_id,)).fetchone()
    return _serializar(row, total_musicas=len(matches))


def seed_catalog(matches_por_seq_id=None):
    """Insere as 6 seeds e, só na primeira vez, seus matches (snapshot da tag).

    Idempotente: INSERT OR IGNORE no catálogo e nos matches. Não recalcula
    seeds já existentes — é o snapshot de compatibilidade documentado na ADR 0002.
    """
    matches_por_seq_id = matches_por_seq_id or {}
    inseridas = 0
    matches_semeados = 0
    with get_conn() as conn:
        for seq_id, acordes in SEQUENCIAS_SEED:
            cur = conn.execute(
                "INSERT OR IGNORE INTO sequencias (id, assinatura, acordes, origem) "
                "VALUES (?, ?, ?, 'seed')",
                (seq_id, assinatura_de(acordes), json.dumps(acordes)),
            )
            inseridas += cur.rowcount
            if conn.execute(
                'SELECT COUNT(*) FROM sequencia_matches WHERE sequencia_id = ?',
                (seq_id,),
            ).fetchone()[0]:
                continue
            ids = matches_por_seq_id.get(seq_id) or []
            if ids:
                conn.executemany(
                    'INSERT OR IGNORE INTO sequencia_matches '
                    '(sequencia_id, id_unico_musica) VALUES (?, ?)',
                    [(seq_id, musica_id) for musica_id in ids],
                )
                matches_semeados += len(ids)
    return {'seeds': inseridas, 'matches': matches_semeados}
