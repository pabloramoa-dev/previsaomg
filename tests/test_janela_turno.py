"""Janela de cada turno: disparo atrasado de ontem não vira o boletim de hoje.

27/11/2026: os crons da noite de 26/11 (17h35, 18h25, 19h25) chegaram às
00h10, 00h40 e 01h19 de 27/11. A trava os tratou como "noite de 27/11", o job
instalou tudo e ficou esperando o preparo das 17h40 até estourar 75 min.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from scripts.aguardar_horario import BRT, janela_do_turno, esperar

MANHA = Path('.github/workflows/reel_manha.yml')
NOITE = Path('.github/workflows/reel_noite.yml')


def _t(dia, h, m):
    return datetime(2026, 11, dia, h, m, tzinfo=BRT)


@pytest.mark.parametrize('quando,esperado', [
    (_t(27, 0, 10), 'cedo'),      # cron das 17h35 de ontem, atrasado
    (_t(27, 0, 40), 'cedo'),
    (_t(27, 1, 19), 'cedo'),
    (_t(26, 16, 59), 'cedo'),
    (_t(26, 17, 0), 'dentro'),
    (_t(26, 17, 35), 'dentro'),   # gatilho externo
    (_t(26, 18, 25), 'dentro'),   # reserva 1
    (_t(26, 19, 25), 'dentro'),   # reserva 2
    (_t(26, 21, 0), 'dentro'),
    (_t(26, 21, 1), 'atrasado'),
    (_t(26, 23, 50), 'atrasado'),
])
def test_janela_da_noite(quando, esperado):
    assert janela_do_turno('18:00', '21:00', 60, quando)[0] == esperado


@pytest.mark.parametrize('quando,esperado', [
    (_t(27, 0, 30), 'cedo'),
    (_t(27, 4, 59), 'cedo'),
    (_t(27, 5, 35), 'dentro'),
    (_t(27, 6, 25), 'dentro'),
    (_t(27, 7, 25), 'dentro'),
    (_t(27, 10, 0), 'dentro'),
    (_t(26, 15, 30), 'atrasado'),  # 26/11: crons da manhã chegaram de tarde
    (_t(26, 16, 43), 'atrasado'),
])
def test_janela_da_manha(quando, esperado):
    assert janela_do_turno('06:00', '10:00', 60, quando)[0] == esperado


def test_espera_longa_encerra_em_vez_de_dormir(monkeypatch, tmp_path):
    import scripts.aguardar_horario as relogio
    resumo = tmp_path / 'resumo.md'
    monkeypatch.setenv('GITHUB_STEP_SUMMARY', str(resumo))
    monkeypatch.setattr(relogio, 'agora', lambda: _t(27, 0, 40))
    monkeypatch.setattr(relogio.time, 'sleep', lambda s: pytest.fail('não pode dormir'))
    with pytest.raises(SystemExit) as saida:
        esperar('18:00', 20, 'preparo')
    assert saida.value.code == 1
    assert 'fora da janela' in resumo.read_text(encoding='utf-8')


def test_espera_normal_continua(monkeypatch):
    import scripts.aguardar_horario as relogio
    dormiu = []
    monkeypatch.setattr(relogio, 'agora', lambda: _t(27, 17, 35))
    monkeypatch.setattr(relogio.time, 'sleep', dormiu.append)
    esperar('18:00', 20, 'preparo')
    assert dormiu == [5 * 60]


def _script_da_trava(caminho: Path) -> str:
    wf = yaml.safe_load(caminho.read_text(encoding='utf-8'))
    passo = next(s for s in wf['jobs']['trava']['steps'] if s.get('id') == 'conferir')
    corpo = re.search(r"<<'PY'\n(.*)\nPY", passo['run'], re.S).group(1)
    return corpo


def _rodar_trava(caminho, agora, evento, tmp_path, fila=(), publicar='', ignorar=''):
    wf = yaml.safe_load(caminho.read_text(encoding='utf-8'))
    (tmp_path / 'data').mkdir(exist_ok=True)
    (tmp_path / 'data' / 'editorial_queue.json').write_text(json.dumps(list(fila)))
    (tmp_path / 'scripts').mkdir(exist_ok=True)
    (tmp_path / 'scripts' / 'aguardar_horario.py').write_text(
        Path('scripts/aguardar_horario.py').read_text(encoding='utf-8'))
    corpo = _script_da_trava(caminho).replace(
        'datetime.datetime.now(', f'(lambda tz: datetime.datetime.fromisoformat({agora.isoformat()!r}).astimezone(tz))(')
    saida, resumo = tmp_path / 'out', tmp_path / 'summary'
    saida.write_text(''), resumo.write_text('')
    env = dict(os.environ, EVENTO=evento, IN_PUBLICAR=publicar, IN_IGNORAR=ignorar,
               GITHUB_OUTPUT=str(saida), GITHUB_STEP_SUMMARY=str(resumo),
               **{k: str(v) for k, v in wf['env'].items()})
    subprocess.run([sys.executable, '-c', corpo], cwd=tmp_path, env=env, check=True)
    out = dict(l.split('=', 1) for l in saida.read_text().split())
    return out, resumo.read_text(encoding='utf-8')


def test_trava_noite_disparada_depois_da_meia_noite(tmp_path):
    out, resumo = _rodar_trava(NOITE, _t(27, 0, 40), 'schedule', tmp_path)
    assert out['pular'] == 'sim'
    assert 'antes da janela' in resumo


def test_trava_noite_na_janela_segue(tmp_path):
    out, _ = _rodar_trava(NOITE, _t(27, 17, 35), 'repository_dispatch', tmp_path)
    assert out == {'pular': 'nao', 'publicar': 'true'}


def test_trava_manha_atrasada_nao_prepara(tmp_path):
    out, resumo = _rodar_trava(MANHA, _t(26, 16, 43), 'schedule', tmp_path)
    assert out['pular'] == 'sim' and 'depois do prazo' in resumo


def test_trava_manual_ignora_janela_e_respeita_caixinha(tmp_path):
    out, _ = _rodar_trava(NOITE, _t(27, 0, 40), 'workflow_dispatch', tmp_path,
                          publicar='false', ignorar='false')
    assert out == {'pular': 'nao', 'publicar': 'false'}


def test_trava_contra_duplicata_continua(tmp_path):
    publicado = {'status': 'published', 'format': 'amanha_no_estado',
                 'published_at': '2026-11-27T18:00:40-03:00', 'media_id': '1'}
    out, resumo = _rodar_trava(NOITE, _t(27, 18, 25), 'schedule', tmp_path, [publicado])
    assert out['pular'] == 'sim' and 'já publicado' in resumo
    # O Reel da noite não trava a manhã do dia seguinte.
    out, _ = _rodar_trava(MANHA, _t(28, 5, 35), 'repository_dispatch', tmp_path, [publicado])
    assert out['pular'] == 'nao'
