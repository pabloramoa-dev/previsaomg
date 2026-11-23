"""Verifica o canal com a configuração real, fora das fixtures legadas."""
import os
from pathlib import Path
import subprocess
import sys


def test_boletins_de_minas_cobrem_oito_regioes_e_alternam_as_cidades():
    env = os.environ.copy()
    env.pop('PREVISAO_CONFIG_DIR', None)
    subprocess.run([sys.executable, '-c', """
from scripts.demo_minas import snapshot
from src.previsao.editorial.formats import antes_de_sair, amanha_no_estado

dados = snapshot()
manha = antes_de_sair(dados, False)
noite = amanha_no_estado(dados, False)
def cidades(boletim):
    return {item['id'] for item in boletim[1]['dados']['cidades']}
assert len(cidades(manha)) == len(cidades(noite)) == 8
assert cidades(manha).isdisjoint(cidades(noite))
assert all(x['chuva_mm'] >= 0 for x in manha[1]['dados']['cidades'])
for boletim in (manha, noite):
    assert sum('Maior volume previsto' in b['fala'] for b in boletim) == 1
"""], cwd=Path(__file__).resolve().parents[1], env=env, check=True)
