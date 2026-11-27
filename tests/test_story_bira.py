"""Reel do Bira também vai para os Stories, uma vez por pauta."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import scripts.publicar_story as story

MANHA = Path('.github/workflows/reel_manha.yml')
NOITE = Path('.github/workflows/reel_noite.yml')
MANUAL = Path('.github/workflows/publicar_manual.yml')


@pytest.fixture
def meta(monkeypatch):
    chamadas = []
    monkeypatch.setattr(story.instagram, 'verify_destination', lambda: {'username': 'previsaomg'})
    monkeypatch.setattr(story.instagram, 'create_story',
                        lambda url: chamadas.append(('story', url)) or 'c1')
    monkeypatch.setattr(story.instagram, 'wait_ready', lambda c: None)
    monkeypatch.setattr(story.instagram, 'publish', lambda c: chamadas.append(('publish', c)) or '999')
    return chamadas


def test_publica_uma_vez_por_pauta(tmp_path, meta):
    registro = tmp_path / 'stories.json'
    assert story.publicar('https://x/REEL.mp4', 'k1', registro) == '999'
    assert meta == [('story', 'https://x/REEL.mp4'), ('publish', 'c1')]
    assert json.loads(registro.read_text())['k1']['media_id'] == '999'
    assert story.publicar('https://x/REEL.mp4', 'k1', registro) is None
    assert len(meta) == 2


def _passo(caminho):
    wf = yaml.safe_load(caminho.read_text(encoding='utf-8'))
    passos = wf['jobs']['reel']['steps']
    nomes = [p.get('name') for p in passos]
    return passos, nomes


@pytest.mark.parametrize('caminho,publicar', [(MANHA, 'Publicar o Reel do dia'),
                                              (MANUAL, 'Publicar Reel controlado')])
def test_story_vem_depois_do_reel_e_nao_derruba(caminho, publicar):
    passos, nomes = _passo(caminho)
    i = nomes.index('Publicar o mesmo vídeo nos Stories')
    assert nomes.index(publicar) < i
    assert passos[i]['continue-on-error'] is True
    assert 'success()' in passos[i]['if']
    texto = caminho.read_text(encoding='utf-8')
    assert 'git add data/stories.json' in texto


def test_noite_da_bia_nao_publica_story():
    assert 'publicar_story' not in NOITE.read_text(encoding='utf-8')
    passos, nomes = _passo(MANUAL)
    cond = passos[nomes.index('Publicar o mesmo vídeo nos Stories')]['if']
    assert "inputs.turno == 'manha'" in cond and "inputs.personagem != 'bia'" in cond
