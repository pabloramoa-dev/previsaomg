"""Monitora avisos CAP oficiais com interseção pelos códigos de municípios."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
import unicodedata

from defusedxml import ElementTree as SafeXML
import requests

from src.previsao import config, estado

INMET = 'https://apiprevmet3.inmet.gov.br'
NS = {'cap': 'urn:oasis:names:tc:emergency:cap:1.2'}
TIPOS = {
    'TEMPESTADE': 'tempestade', 'GRANIZO': 'granizo', 'VENDAVAL': 'vendaval',
    'CHUVAS INTENSAS': 'chuva_intensa', 'ACUMULADO DE CHUVA': 'chuva_intensa',
    'CICLONE': 'ciclone', 'CICLONE TROPICAL': 'ciclone',
    'CICLONE SUBTROPICAL': 'ciclone', 'CICLONE EXTRATROPICAL': 'ciclone',
}


def consultar(caminho):
    resposta = requests.get(INMET + caminho, timeout=(10, 30), allow_redirects=False)
    if resposta.status_code != 200:
        raise RuntimeError(f'INMET indisponível: HTTP {resposta.status_code}')
    return resposta


def codigos(texto):
    return set(re.findall(r'\bMG\s*\((31\d{5})\)', texto))


def ler_cap(xml, cidades, agora, parametros):
    raiz = SafeXML.fromstring(xml)
    def campo(no, nome):
        return no.findtext(f'cap:{nome}', '', NS).strip()

    if (campo(raiz, 'status') != 'Actual' or campo(raiz, 'scope') != 'Public'
            or campo(raiz, 'msgType') not in {'Alert', 'Update'}
            or not campo(raiz, 'sender').lower().endswith('@inmet.gov.br')):
        return []
    identificador = campo(raiz, 'identifier')
    if not identificador:
        return []
    emitido = datetime.fromisoformat(campo(raiz, 'sent'))
    if emitido.tzinfo is None or emitido > agora + timedelta(minutes=5):
        return []
    alertas = []
    for info in raiz.findall('cap:info', NS):
        evento = campo(info, 'event')
        sem_acentos = unicodedata.normalize('NFKD', evento).encode('ascii', 'ignore').decode()
        tipo = TIPOS.get(sem_acentos.upper())
        if tipo not in parametros['accepted_events']:
            continue
        inicio = datetime.fromisoformat(campo(info, 'onset') or campo(info, 'effective'))
        fim = datetime.fromisoformat(campo(info, 'expires'))
        if (inicio.tzinfo is None or fim.tzinfo is None or fim <= max(inicio, agora)
                or inicio > agora + timedelta(hours=parametros['next_hours'])):
            continue
        municipios = set()
        for parametro in info.findall('cap:parameter', NS):
            if campo(parametro, 'valueName').casefold() in {'municipios', 'municípios'}:
                municipios.update(codigos(campo(parametro, 'value')))
        locais = [cidades[codigo] for codigo in sorted(municipios & cidades.keys())]
        fonte = campo(info, 'web')
        if locais and re.fullmatch(r'https://avisos\.inmet\.gov\.br/\d+/?', fonte):
            alertas.append(dict(id=identificador, tipo=tipo, evento=evento, cidades=locais,
                                inicio=inicio.isoformat(), fim=fim.isoformat(), fonte=fonte))
    return alertas


def main():
    agora = datetime.now(estado.fuso())
    cidades = {str(loc['ibge']): loc['name'] for loc in config.locations_by_tier(2)}
    parametros = config.load_thresholds()['severe_weather']
    ativos = consultar('/avisos/ativos').json()
    if any(not isinstance(ativos.get(dia), list) for dia in ('hoje', 'futuro')):
        raise RuntimeError('Janelas da API do INMET ausentes')
    ids = {str(item['id']) for item in ativos['hoje'] + ativos['futuro']
           if codigos(item['municipios']) & cidades.keys()}
    alertas = []
    for identificador in sorted(ids):
        if not identificador.isdecimal():
            raise ValueError('Identificador INMET inválido')
        xml = consultar('/avisos/rss/' + identificador).content
        alertas.extend(ler_cap(xml, cidades, agora, parametros))
    saida = Path('output/alertas_mg.json')
    saida.parent.mkdir(exist_ok=True)
    saida.write_text(json.dumps(dict(checagem=agora.isoformat(), alertas=alertas),
                                indent=2, ensure_ascii=False))
    print(f'{len(alertas)} avisos oficiais elegíveis em Minas Gerais')


if __name__ == '__main__':
    main()
