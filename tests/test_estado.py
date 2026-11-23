"""A configuração REAL do canal (config/) e a identidade lida dela.

O resto da bateria roda sobre o estado de referência (tests/ref_config) para
validar o motor; aqui se valida o que é deste repositório.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.previsao import estado

RAIZ = Path(__file__).resolve().parents[1]


def test_configuracao_real_do_canal_e_coerente():
    env = dict(os.environ, PREVISAO_CONFIG_DIR=str(RAIZ / 'config'))
    r = subprocess.run([sys.executable, '-m', 'scripts.validar_estado'], cwd=RAIZ, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_marca_dos_arquivos_bate_com_o_estado_real():
    env = dict(os.environ, PREVISAO_CONFIG_DIR=str(RAIZ / 'config'))
    r = subprocess.run([sys.executable, '-m', 'scripts.sincronizar_marca', '--check'],
                       cwd=RAIZ, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize('artigo,curto,em,de', [
    ('o', 'Paraná', 'no Paraná', 'do Paraná'),
    ('a', 'Bahia', 'na Bahia', 'da Bahia'),
    ('', 'Minas', 'em Minas', 'de Minas'),
])
def test_preposicao_do_estado(monkeypatch, artigo, curto, em, de):
    dados = dict(estado.carregar(), artigo=artigo, curto=curto)
    monkeypatch.setattr(estado, 'carregar', lambda: dados)
    assert estado.em() == em and estado.de() == de
    assert estado.em(inicio=True) == em[0].upper() + em[1:]


@pytest.mark.parametrize('fuso,sufixo', [(-3, '-03:00'), (-4, '-04:00'), (-5, '-05:00')])
def test_fuso_do_estado(monkeypatch, fuso, sufixo):
    monkeypatch.setenv('FUSO_UTC', str(fuso))
    assert estado.offset_iso() == sufixo
    assert estado.fuso().utcoffset(None).total_seconds() == fuso * 3600


def test_validacao_recusa_configuracao_incompleta():
    dados = dict(estado.carregar())
    dados['regioes'] = dados['regioes'][:5]
    with pytest.raises(ValueError, match='seis|6'):
        estado.validar(dados)
    with pytest.raises(ValueError, match='handle'):
        estado.validar(dict(estado.carregar(), handle='@Previsao'))
    with pytest.raises(ValueError, match='fuso'):
        estado.validar(dict(estado.carregar(), fuso_utc=-8))
