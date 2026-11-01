import os
import sys
import tempfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# Banco isolado por sessão de teste. Precisa ser definido ANTES de importar
# main/persistencia, que resolvem o caminho no import.
_DIR_BANCO = tempfile.mkdtemp(prefix='deciframe-testes-')
os.environ['DECIFRAME_DB'] = os.path.join(_DIR_BANCO, 'deciframe.db')

import main  # noqa: E402  (import tardio de propósito)
import persistencia  # noqa: E402


@pytest.fixture(scope='session')
def client():
    return main.app.test_client()


@pytest.fixture(scope='session')
def fixture_regressao():
    import json

    caminho = RAIZ / 'tests' / 'fixtures' / 'baseline_sequencias.json'
    with open(str(caminho), encoding='utf-8') as arquivo:
        return json.load(arquivo)
