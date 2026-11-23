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


def test_monitor_exige_aviso_oficial_vigente_para_municipio_monitorado():
    from datetime import datetime
    from scripts.monitor_alertas import ler_cap

    inicio = '2026-11-23T10:00:00-03:00'
    fim = '2026-11-23T19:00:00-03:00'
    agora = datetime.fromisoformat('2026-11-23T11:00:00-03:00')
    cap = f"""
    <alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
      <identifier>123</identifier><sender>avisos@inmet.gov.br</sender>
      <sent>{inicio}</sent><status>Actual</status><scope>Public</scope>
      <msgType>Alert</msgType>
      <info>
        <event>Tempestade</event><onset>{inicio}</onset><expires>{fim}</expires>
        <web>https://avisos.inmet.gov.br/123</web>
        <parameter><valueName>Municipios</valueName>
          <value>Belo Horizonte - MG (3106200)</value></parameter>
      </info>
    </alert>
    """
    cidades = {'3106200': 'Belo Horizonte'}
    params = {'accepted_events': ['tempestade'], 'next_hours': 24}
    assert ler_cap(cap, cidades, agora, params)[0]['cidades'] == ['Belo Horizonte']
    for proibido in (cap.replace('3106200', '3106705'),
                     cap.replace('Actual', 'Test'),
                     cap.replace(fim, inicio),
                     cap.replace('avisos.inmet.gov.br', 'example.org')):
        assert ler_cap(proibido, cidades, agora, params) == []
