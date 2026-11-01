# coding: utf-8
import json
import os

import pytest

import main

SEQS = ['Bm,G,D,A', 'C,G,Am,F', 'Em,G', 'C,A7,Dm,G7', 'Gm,F', 'C,C7,F,Fm']


def _json(resposta):
    return json.loads(resposta.get_data(as_text=True))


def test_regressao_igualdade_com_fixture(client, fixture_regressao):
    if os.environ.get('PYTHONHASHSEED') != '0':
        pytest.fail(
            'a regressão byte a byte exige PYTHONHASHSEED=0: a ordem de gêneros e de '
            'musica.acordes vem de set() no código legado e varia entre processos; '
            'rode com: PYTHONHASHSEED=0 python -m pytest'
        )
    for chave, esperado in sorted(fixture_regressao.items()):
        sequencia, generos, pagina = chave.split('|')
        params = {'sequencia': sequencia, 'pagina': pagina}
        if generos:
            params['generos'] = generos
        atual = client.get('/similares', query_string=params).get_data(as_text=True)
        assert atual == esperado, 'resposta diferente para %r' % chave


def test_catalogo_tem_as_seis_seeds(client):
    resposta = client.get('/sequencias')
    assert resposta.status_code == 200
    assert resposta.headers['Content-Type'].startswith('text/html')

    sequencias = _json(resposta)
    seeds = {s['id']: s for s in sequencias if s['origem'] == 'seed'}
    assert sorted(seeds) == list(range(6))
    assert seeds[1]['acordes'] == ['C', 'G', 'Am', 'F']
    assert seeds[5]['acordes'] == ['C', 'C7', 'F', 'Fm']


def test_post_cria_e_aparece_no_catalogo(client):
    resposta = client.post('/sequencias', json={'acordes': ['Dm', 'G', 'C']})
    assert resposta.status_code == 201

    criada = _json(resposta)
    assert criada['acordes'] == ['Dm', 'G', 'C']
    assert criada['origem'] == 'usuario'
    assert criada['total_musicas'] > 0

    catalogo = _json(client.get('/sequencias'))
    assert any(s['id'] == criada['id'] for s in catalogo)


def test_post_duplicado_devolve_409_com_id(client):
    primeira = _json(client.post('/sequencias', json={'acordes': ['Bm', 'Em', 'A']}))
    resposta = client.post('/sequencias', json={'acordes': ['Bm', 'Em', 'A']})

    assert resposta.status_code == 409
    corpo = _json(resposta)
    assert corpo['id'] == primeira['id']


@pytest.mark.parametrize('corpo', [
    {'acordes': ['C']},
    {'acordes': ['C'] * 17},
    {'acordes': ['C', 'G Am']},
    {'acordes': 'C,G'},
    {'outro': 'campo'},
    None,
])
def test_post_invalido_devolve_400(client, corpo):
    resposta = client.post('/sequencias', json=corpo)
    assert resposta.status_code == 400
    assert 'erro' in _json(resposta)


def test_post_com_corpo_nao_json_devolve_400(client):
    resposta = client.post('/sequencias', data='não é json',
                           content_type='application/json')
    assert resposta.status_code == 400


def test_busca_por_sequencia_nova(client):
    criada = _json(client.post('/sequencias', json={'acordes': ['Am', 'F', 'C']}))
    assert criada['total_musicas'] > 0
    acordes = criada['acordes']

    resposta = client.get('/similares', query_string={'sequencia': 'Am, F, C'})
    assert resposta.status_code == 200
    musicas = _json(resposta)

    assert len(musicas) == min(100, criada['total_musicas'])
    assert all('id_unico_musica' in m for m in musicas)

    esperado = [m.id_unico_musica for m in main.apply_filtro(main.musicas.values(), main.generos)
                if main.contem_subsequencia(m.cifra, acordes)]
    assert [m['id_unico_musica'] for m in musicas] == esperado[:100]


def test_busca_por_sequencia_nova_com_genero_e_paginacao(client):
    acordes = ['Em', 'Am', 'D', 'G']
    assert client.post('/sequencias', json={'acordes': acordes}).status_code == 201

    esperado = [m.id_unico_musica for m in main.genero_musicas['MPB']
                if main.contem_subsequencia(m.cifra, acordes)]

    pagina_1 = _json(client.get('/similares', query_string={
        'sequencia': 'Em,Am,D,G', 'generos': 'MPB', 'pagina': '1'}))
    assert [m['id_unico_musica'] for m in pagina_1] == esperado[:100]

    if len(esperado) > 100:
        pagina_2 = _json(client.get('/similares', query_string={
            'sequencia': 'Em,Am,D,G', 'generos': 'MPB', 'pagina': '2'}))
        assert [m['id_unico_musica'] for m in pagina_2] == esperado[100:200]


def test_sequencia_desconhecida_devolve_lista_vazia(client):
    resposta = client.get('/similares', query_string={'sequencia': 'Zz,Qq'})
    assert resposta.status_code == 200
    assert _json(resposta) == []


def test_formato_da_resposta_segue_json_dumps(client):
    resposta = client.get('/sequencias')
    assert resposta.headers['Content-Type'].startswith('text/html')
    assert resposta.get_data(as_text=True).startswith('[')
