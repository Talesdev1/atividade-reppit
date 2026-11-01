# coding: utf-8
import pytest

from main import contem_subsequencia


@pytest.mark.parametrize('cifra, seq, esperado', [
    (['C', 'G', 'Am', 'F'], ['C', 'G', 'Am', 'F'], True),
    (['C', 'G', 'Am', 'F'], ['G', 'Am'], True),
    (['C', 'G', 'Am', 'G'], ['G', 'Am'], True),
    (['C', 'G', 'Am'], ['Am', 'C'], False),          # ordem importa
    (['C', 'G', 'Am'], ['C', 'Am'], False),          # precisa ser contígua
    (['C', 'G', 'Am'], ['C', 'G', 'Am', 'F'], False),  # maior que a cifra
    (['A', 'A', 'A'], ['A', 'A'], True),             # repetição sobreposta
    (['Am', 'G'], ['am', 'G'], False),               # case-sensitive
    ([], ['C', 'G'], False),                         # cifra vazia
    (['C', 'G'], [], False),                         # sequência vazia
])
def test_contem_subsequencia(cifra, seq, esperado):
    assert contem_subsequencia(cifra, seq) is esperado


def test_musicas_sem_cifra_nunca_casam():
    assert contem_subsequencia([], ['C', 'G']) is False
