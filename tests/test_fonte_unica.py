"""Canal de provedor único: só a MET Norway, com o Open-Meteo desligado.

É o arranjo dos canais novos (dado gratuito, CC BY 4.0, uso comercial
permitido). A MET Norway não fornece probabilidade de chuva nem rajada para o
Brasil, então o que estes testes protegem é:

  - o snapshot sai com a met.no como principal, SEM marca de fallback;
  - a nota de confiança não carrega para sempre a penalidade de um critério
    que não existe (concordância entre modelos) — mas dado velho ainda reprova;
  - o Reel e a legenda falam de VOLUME (mm) e de horário, nunca de "chance";
  - nada vira zero inventado: sem dado de chuva, a frase diz que não veio.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.previsao import config
from src.previsao.collectors import met_no
from src.previsao.collectors.base import SourceResult, not_collected, now
from src.previsao.editorial.engine import evaluate
from src.previsao.editorial.formats import amanha_no_estado, antes_de_sair
from src.previsao.normalizers import snapshot as snap
from src.previsao.publish.caption import build_caption
from src.previsao.quality import confidence as conf
from src.previsao.render.practical import tips


def _serie(chuva_das: tuple[int, int] | None, mm_hora: float, base: float) -> dict:
    """72 h no formato `compact`, começando à meia-noite local (03:00Z)."""
    inicio = datetime(2026, 9, 12, 3, 0, tzinfo=timezone.utc)
    pontos = []
    for i in range(72):
        hora_local = i % 24
        chove = chuva_das is not None and chuva_das[0] <= hora_local < chuva_das[1]
        pontos.append({
            'time': (inicio + timedelta(hours=i)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'data': {
                'instant': {'details': {
                    'air_temperature': round(base + 8.0 * (1 - abs((hora_local - 14) / 14)), 1),
                    'cloud_area_fraction': 80.0 if chove else 20.0,
                    'wind_speed': 3.0 + (hora_local % 5) * 0.5,
                }},
                'next_1_hours': {
                    'summary': {'symbol_code': 'rain' if chove else 'fair_day'},
                    'details': {'precipitation_amount': mm_hora if chove else 0.0},
                },
            },
        })
    return {'properties': {'timeseries': pontos}}


def _coletado(locais, chuvoso: str | None, mm_hora: float = 2.5) -> dict[str, SourceResult]:
    points = {}
    for n, loc in enumerate(locais):
        janela = (15, 19) if loc['id'] == chuvoso else None
        points[loc['id']] = met_no.to_open_meteo_shape(_serie(janela, mm_hora, 18.0 + n))
    primeiro = next(iter(points.values()))
    return {
        # Como open_meteo.fetch_all_models responde com a fonte desligada.
        'icon_seamless': not_collected('open_meteo_forecast:icon_seamless',
                                       'fonte desligada em fontes.yaml'),
        met_no.MODEL: SourceResult(
            name=f'{met_no.SOURCE}:{met_no.MODEL}', status='ok',
            payload={'model': met_no.MODEL, 'points': points},
            valid_for=f"{primeiro['daily']['time'][0]}..{primeiro['daily']['time'][-1]}",
            model_run='met_no@teste'),
    }


@pytest.fixture
def locais():
    return config.locations_by_tier(1)


@pytest.fixture
def snapshot(locais):
    return snap.build(_coletado(locais, chuvoso=locais[0]['id']), locais)


@pytest.fixture
def snapshot_seco(locais):
    return snap.build(_coletado(locais, chuvoso=None), locais)


def test_met_no_e_a_principal_sem_fallback(snapshot):
    assert snapshot['forecast']['primary_model'] == met_no.MODEL
    assert snapshot['forecast']['models'] == [met_no.MODEL]
    assert snapshot['fallback_used'] is False
    estados = {s['name']: s['status'] for s in snapshot['sources']}
    assert estados['open_meteo_forecast:icon_seamless'] == 'not_collected'


def test_campos_que_a_met_no_nao_da_ficam_ausentes(snapshot):
    for entrada in snapshot['forecast']['today']['locations']:
        assert entrada['rain_probability_pct'] is None
        assert entrada['wind_gust_max_kmh'] is None
        assert entrada['uv_index_max'] is None
        assert isinstance(entrada['rain_mm'], float)
        assert entrada['wind_max_kmh'] > 0          # vento sustentado: esse existe


def test_confianca_de_provedor_unico_libera_o_reel(snapshot):
    c = snapshot['confidence']
    assert c['single_provider'] is True
    assert c['score'] >= conf.MIN_FOR_CATEGORICAL
    assert c['gates']['allow_categorical_language'] is True
    assert any('provedor unico' in n for n in c['notes'])


def test_dado_velho_ainda_reprova_no_provedor_unico():
    velho = conf.compute(per_model={}, age_minutes=175, freshness_ttl_minutes=180,
                         previous_reference=None, current_reference={},
                         observed_status='not_collected', observation_agreement=None,
                         spatial_fits=['baixo'], single_provider=True)
    assert velho['score'] < conf.MIN_FOR_ALERT
    assert velho['gates']['allow_alert_reel'] is False


def test_falha_do_outro_provedor_nao_conta_como_provedor_unico(locais):
    """Open-Meteo LIGADO que falhou é degradação, não escolha: mantém a nota
    conservadora de 'só um modelo disponível'."""
    coletado = _coletado(locais, chuvoso=None)
    coletado['icon_seamless'] = SourceResult('open_meteo_forecast:icon_seamless',
                                             'failed', detail='429')
    c = snap.build(coletado, locais)['confidence']
    assert c['single_provider'] is False and c['parts']['model_agreement'] == 12.0


def test_janela_de_chuva_sai_do_volume(snapshot, locais):
    entrada = next(e for e in snapshot['forecast']['today']['locations']
                   if e['id'] == locais[0]['id'])
    janela = entrada['rain_window']
    assert janela['basis'] == 'volume'
    assert (janela['start'], janela['end']) == ('15:00', '18:00')
    assert janela['peak_mm'] == 2.5 and 'peak_probability_pct' not in janela
    assert entrada['rain_mm'] == 10.0
    secos = [e for e in snapshot['forecast']['today']['locations'] if e['id'] != locais[0]['id']]
    assert all(e['rain_window'] is None for e in secos)


def test_reel_de_hoje_fala_em_milimetros(snapshot, locais, monkeypatch):
    monkeypatch.setenv('PREVISAO_HORA_ALVO', '6')
    monkeypatch.setattr('src.previsao.editorial.script.hora_agora', lambda: 6)
    monkeypatch.setattr('src.previsao.editorial.formats.hora_agora', lambda: 6)
    batidas = antes_de_sair(snapshot, False)
    cartao = [b for b in batidas if b['dados'].get('sub') == 'CHUVA PREVISTA']
    assert len(cartao) == 1
    assert cartao[0]['dados']['numero'] == '10 mm'
    assert '10 milímetros de chuva no dia' in cartao[0]['fala']
    assert 'das quinze às dezoito horas' in cartao[0]['fala']
    assert 'das 15h às 18h' in cartao[0]['legenda']
    texto = ' '.join(b['fala'] for b in batidas)
    assert 'por cento' not in texto and 'não está disponível' not in texto
    assert [b['tipo'] for b in batidas].count('resumo') == 1


def test_reel_de_amanha_tambem(snapshot):
    batidas = amanha_no_estado(snapshot, False)
    cartao = [b for b in batidas if b['dados'].get('sub') == 'CHUVA PREVISTA AMANHÃ']
    assert len(cartao) == 1 and 'de chuva amanhã' in cartao[0]['fala']


def test_dia_seco_diz_que_nao_chove(snapshot_seco):
    falas = [b['fala'] for b in antes_de_sair(snapshot_seco, False)]
    assert 'Sem chuva significativa prevista para hoje.' in falas
    assert not any('por cento' in f or 'milímetro' in f for f in falas)


def test_quadro_leva_volume_e_vento_sustentado(snapshot):
    resumo = next(b for b in antes_de_sair(snapshot, False) if b['tipo'] == 'resumo')
    for linha in resumo['dados']['cidades']:
        assert 'prob_chuva' not in linha and 'vento_kmh' not in linha
        assert 'chuva_mm' in linha and 'vento_medio_kmh' in linha


def test_pauta_diaria_fica_pronta_e_a_legenda_credita_a_fonte(snapshot):
    snapshot['generated_at'] = now().isoformat(timespec='seconds')
    prontos = {c['format']: c for c in evaluate(snapshot) if c['status'] == 'ready'}
    assert {'antes_de_sair', 'amanha_no_estado'} <= set(prontos)
    assert prontos['antes_de_sair']['language'] == 'forecast'
    for formato in ('antes_de_sair', 'amanha_no_estado'):
        legenda = build_caption(snapshot, prontos[formato])
        assert 'MET Norway' in legenda and 'mm previstos' in legenda
        assert '%' not in legenda


def test_dica_pratica_sai_do_volume(snapshot, snapshot_seco):
    assert 'LEVE GUARDA-CHUVA' in tips(snapshot['forecast']['today']['locations'])
    assert not any('CHUV' in t or 'CHOVER' in t
                   for t in tips(snapshot_seco['forecast']['today']['locations']))
