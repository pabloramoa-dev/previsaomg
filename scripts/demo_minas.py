"""Snapshot sintético exclusivo dos ensaios, sem previsão meteorológica."""
from datetime import datetime, timedelta

from src.previsao import config, estado


def snapshot():
    agora = datetime.now(estado.fuso())
    datas = (agora.date(), agora.date() + timedelta(days=1))
    blocos = {}
    for dia, data in zip(('today', 'tomorrow'), datas):
        locais = []
        for i, local in enumerate(config.locations_by_tier(2)):
            locais.append(dict(id=local['id'], name=local['name'], zone=local['zone'],
                               min_c=15 + i % 7, max_c=25 + i % 9, rain_mm=i / 2))
        blocos[dia] = dict(date=data.isoformat(), locations=locais)
    return dict(generated_at=agora.isoformat(), synthetic=True, forecast=blocos)
