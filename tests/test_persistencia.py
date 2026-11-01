# coding: utf-8
import pytest

import main
import persistencia


@pytest.fixture
def banco_temporario(tmp_path):
    anterior = persistencia.caminho_db()
    caminho = str(tmp_path / 'deciframe.db')
    persistencia.init_db(caminho)
    yield caminho
    persistencia.init_db(anterior)


def test_seed_idempotente(banco_temporario):
    primeiro = persistencia.seed_catalog(main._matches_das_seeds())
    segundo = persistencia.seed_catalog(main._matches_das_seeds())

    assert primeiro['seeds'] == 6
    assert primeiro['matches'] > 0
    assert segundo == {'seeds': 0, 'matches': 0}
    assert persistencia.contar_sequencias() == 6

    sequencias = persistencia.listar_sequencias()
    assert [s['id'] for s in sequencias] == list(range(6))
    assert all(s['origem'] == 'seed' for s in sequencias)
    assert sequencias[1]['acordes'] == ['C', 'G', 'Am', 'F']


def test_criar_e_buscar(banco_temporario):
    persistencia.seed_catalog(main._matches_das_seeds())
    criada = persistencia.criar_sequencia(['Dm', 'G', 'C'], ['a_1', 'b_2'])

    assert criada['id'] >= 6
    assert criada['origem'] == 'usuario'
    assert criada['total_musicas'] == 2

    seq_id = persistencia.buscar_por_assinatura('Dm,G,C')
    assert seq_id == criada['id']
    assert persistencia.matches_de(seq_id) == {'a_1', 'b_2'}
    assert persistencia.buscar_por_assinatura('C,G,Am,F') == 1


def test_duplicata_por_ordem_exata(banco_temporario):
    criada = persistencia.criar_sequencia(['Dm', 'G', 'C'], [])

    with pytest.raises(persistencia.SequenciaDuplicada) as erro:
        persistencia.criar_sequencia(['Dm', 'G', 'C'], [])

    assert erro.value.seq_id == criada['id']
    # ordem diferente é outra sequência
    outra = persistencia.criar_sequencia(['G', 'Dm', 'C'], [])
    assert outra['id'] != criada['id']


def test_persistencia_apos_reabrir(banco_temporario):
    criada = persistencia.criar_sequencia(['Dm', 'G', 'C'], ['a_1'])
    persistencia.init_db(banco_temporario)  # simula reinício do processo

    assert persistencia.buscar_por_assinatura('Dm,G,C') == criada['id']
    assert persistencia.matches_de(criada['id']) == {'a_1'}


@pytest.mark.parametrize('entrada,mensagem', [
    (['C'], 'ao menos 2'),
    (['C'] * 17, 'no máximo 16'),
    (['C', 'G Am'], 'inválido'),
    (['C', ''], 'vazio'),
    (['C', 'G;Am'], 'inválido'),
    ('C,G', 'lista'),
    ([1, 2], 'string'),
])
def test_normalizacao_rejeita_entrada_invalida(entrada, mensagem):
    with pytest.raises(persistencia.ErroDeValidacao) as erro:
        persistencia.normalizar_acordes(entrada)
    assert mensagem in str(erro.value)


def test_normalizacao_aceita_tokens_do_dataset():
    acordes = persistencia.normalizar_acordes([' C ', 'F#/Bb', 'Bb7M/5-', 'C7M'])
    assert acordes == ['C', 'F#/Bb', 'Bb7M/5-', 'C7M']
