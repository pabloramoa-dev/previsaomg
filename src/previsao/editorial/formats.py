"""Cinco formatos com validação de dados antes de produzir a fala."""
from datetime import date, timedelta
from .contrast import regional_contrast
from .cinco import cinco_regioes, fala_resumo
from .engine import evaluate, stamp
from .script import (build_script, decimal_br, em_local, em_locais,
                     faixa_escrita, faixa_falada, hora_agora, janela_legivel,
                     number, para_voz, pico_escrito, pico_falado)

from .. import estado


class _Titulos(dict):
    """Títulos por formato, lidos do estado na hora do uso."""
    def __getitem__(self, chave):
        return estado.titulos()[chave]

    def get(self, chave, padrao=None):
        return estado.titulos().get(chave, padrao)


TITLES = _Titulos()


def batida(fala, tipo='nenhum', legenda=None, **dados):
    """`legenda` só difere da fala quando a tela pede forma curta ("23h")
    e a voz pede extenso ("vinte e três horas")."""
    return {'fala': para_voz(fala), 'legenda': decimal_br(legenda or fala),
            'tipo': tipo, 'dados': dados}



def destaque_da_semana(snapshot, locations):
    """Destaques por DIA DE PUBLICAÇÃO, nunca pela data de amanhã.

    A tabela (dia da semana -> local) é do estado (`destaques_semana` em
    config/estado.yaml) e pode ficar vazia. Se a coleta não trouxer mínima e
    máxima válidas, não cita uma previsão sem dados.
    """
    try:
        dia = date.fromisoformat(snapshot['forecast']['today']['date']).weekday()
    except (KeyError, ValueError, TypeError):
        return None
    regra = _regra_do_dia(dia)
    if regra is None:
        return None
    return next((loc for loc in locations
                 if loc.get('id') == regra.get('id')
                 and number(loc.get('min_c')) and number(loc.get('max_c'))), None)


def _regra_do_dia(dia):
    return next((r for r in estado.destaques_semana() if dia in (r.get('dias') or ())), None)


def gancho_destaque(snapshot, locations, periodo):
    """Gancho hiperlocal protegido contra corte; substitui o gancho térmico.

    Mantém a duração do Reel e deixa intacto o resumo das seis regiões.
    """
    local = destaque_da_semana(snapshot, locations)
    if local is None:
        return None
    regra = next(r for r in estado.destaques_semana() if r.get('id') == local['id'])
    onde = regra.get('onde') or em_local(local['name'])
    selo = regra.get('selo') or local['name'].upper()
    periodo_na_tela = 'HOJE' if periodo == 'hoje' else 'AMANHÃ'
    # A abertura noturna já diz 'amanhã'; não repetir na narração.
    inicio = 'Hoje, ' if periodo == 'hoje' else ''
    lugar = onde if inicio else onde[0].upper() + onde[1:]
    fala = (f"{inicio}{lugar}: mínima de {local['min_c']:g} e "
            f"máxima de {local['max_c']:g} graus.")
    return batida(fala, 'gancho', numero=f"{local['max_c']:g}°",
                  sub=f"{selo} · {periodo_na_tela}", destaque_local=True)


def _mm(valor):
    """Volume para a tela e a voz: inteiro, nunca '0' para chuva que existe."""
    return max(1, round(valor))


def batida_chuva(locs, amanha=False):
    """A batida de chuva do Reel-base, com o melhor dado que a coleta trouxe.

    1. Probabilidade (quando o provedor dá): "chance de chuva de 70 por cento".
    2. Só volume (MET Norway no Brasil): milímetros previstos no ponto mais
       chuvoso — ou, se nenhum ponto chega ao limiar, "sem chuva significativa".
       Volume nunca é anunciado como chance.
    3. Nenhum dos dois: diz que o dado não veio. Nunca inventa.
    """
    quando = 'amanhã' if amanha else 'no dia'
    sufixo = ' AMANHÃ' if amanha else ''
    com_prob = [e for e in locs if number(e.get('rain_probability_pct'))]
    if com_prob:
        molhado = max(com_prob, key=lambda e: e['rain_probability_pct'])
        pct = molhado['rain_probability_pct']
        fala = (f"{em_local(molhado['name'], inicio=True)}, a chance de chuva amanhã é de {pct:g} por cento."
                if amanha else
                f"{em_local(molhado['name'], inicio=True)}, a chance de chuva no dia é de {pct:g} por cento. "
                'Não significa chuva o dia inteiro.')
        return batida(fala, 'gancho', numero=f'{pct:g}%', sub='CHANCE DE CHUVA' + sufixo)
    com_volume = [e for e in locs if number(e.get('rain_mm'))]
    if com_volume:
        from .. import config
        limiar = config.load_thresholds().get('rain_relevant_mm', 1.0)
        molhado = max(com_volume, key=lambda e: e['rain_mm'])
        if molhado['rain_mm'] >= limiar:
            mm = _mm(molhado['rain_mm'])
            unidade = 'milímetro' if mm == 1 else 'milímetros'
            fala = (f"{em_local(molhado['name'], inicio=True)}, a previsão é de "
                    f"{mm} {unidade} de chuva {quando}.")
            leitura = janela_legivel(molhado.get('rain_window'),
                                     None if amanha else hora_agora())
            legenda = None
            if leitura and leitura['tipo'] == 'faixa':
                legenda = fala[:-1] + ', ' + faixa_escrita(leitura['inicio'], leitura['fim']) + '.'
                fala = fala[:-1] + ', ' + faixa_falada(leitura['inicio'], leitura['fim']) + '.'
            elif leitura:
                legenda = fala[:-1] + ', mais forte ' + pico_escrito(leitura['hora']) + '.'
                fala = fala[:-1] + ', mais forte ' + pico_falado(leitura['hora']) + '.'
            return batida(fala, 'gancho', legenda, numero=f'{mm} mm',
                          sub='CHUVA PREVISTA' + sufixo)
        return batida('Sem chuva significativa prevista para amanhã.' if amanha
                      else 'Sem chuva significativa prevista para hoje.')
    return batida('A probabilidade de chuva para amanhã não está disponível nesta coleta.'
                  if amanha else 'A probabilidade de chuva não está disponível nesta coleta.')


def boletim_minas(bloco, amanha=False):
    locs = bloco['locations']
    dia = 'amanhã' if amanha else 'hoje'
    quadro = batida_resumo(locs, f'PREVISÃO PARA {dia.upper()}', data_previsao=bloco.get('date'))
    if quadro is None or len(quadro['dados']['cidades']) != len(estado.regioes()):
        raise ValueError('Coleta sem dados válidos para as oito regiões de Minas Gerais')
    batidas = [batida(f'Confira o tempo em Minas para {dia}.'), quadro]
    com_chuva = [loc for loc in locs if number(loc.get('rain_mm')) and loc['rain_mm'] > 0]
    if com_chuva:
        maior = max(com_chuva, key=lambda loc: (loc['rain_mm'], loc['id']))
        mm = f"{maior['rain_mm']:.1f}".replace('.', ',').removesuffix(',0')
        if mm != '0':
            unidade = 'milímetro' if mm == '1' else 'milímetros'
            fala = f"Maior volume previsto {dia}: {mm} {unidade} em {maior['name']}."
            batidas.append(batida(fala, 'gancho', numero=f'{mm} mm', sub=f"MAIOR CHUVA · {maior['name'].upper()}"))
    else:
        batidas.append(batida(f'Confira no quadro os volumes de chuva previstos para {dia}.'))
    return batidas


def antes_de_sair(snapshot, incerto):
    """Batidas com cartao proprio, em vez de um paragrafo sobre o apresentador.

    O formato devolvia UMA fala com tipo 'nenhum': o render nao tinha o que
    desenhar e o Reel virava locucao sobre fundo parado. Agora cada informacao
    tem a sua batida e o seu cartao — e nenhuma batida nasce sem o dado que ela
    mostra, entao coleta incompleta encurta o Reel em vez de inventar numero.
    """
    if estado.regiao_id() == 'estado_mg':
        return boletim_minas(snapshot['forecast']['today'])
    dados = build_script(snapshot)
    locs = snapshot['forecast']['today']['locations']
    quente, frio, chuvoso = dados['hottest'], dados['coolest'], dados['wettest']
    contraste = regional_contrast(locs)
    # Abre SEM cartao de proposito. Gancho, resumo e CTA sao altos e tiram o
    # apresentador de cena; se todas as batidas fossem dessas, a locucao inteira
    # sairia sobre um cenario vazio. A abertura e o aviso de incerteza sao as
    # batidas em que ele aparece.
    batidas = [batida(f'Veja a previsão {estado.de()} para hoje.')]
    if incerto:
        batidas.append(batida('O cenário ainda tem incerteza. Há possibilidade de mudança.'))
    destaque = gancho_destaque(snapshot, locs, 'hoje')
    if destaque is not None:
        batidas.append(destaque)
    elif contraste['temperature']['relevant']:
        vao = contraste['temperature']['spread']
        batidas.append(batida(
            f"Hoje a temperatura muda pela região: {vao:g} graus separam "
            f"{quente['name']} de {frio['name']}.",
            'gancho', numero=f'{vao:g}°', sub='DE DIFERENÇA NA REGIÃO'))
    else:
        batidas.append(batida(
            f"{estado.em(inicio=True)}, a máxima prevista chega a {quente['max_c']:g} graus {em_local(quente['name'])}.",
            'gancho', numero=f"{quente['max_c']:g}°", sub='MÁXIMA PREVISTA HOJE'))
    resumo = batida_resumo(locs, 'HOJE NA REGIÃO')
    if resumo:
        batidas.append(resumo)
    batidas.append(batida_chuva(locs))
    if contraste['gust']['relevant']:
        alta = contraste['gust']['high']
        batidas.append(batida(
            f"Atenção ao vento: rajadas de até {alta['value']:g} quilômetros por hora "
            f"{em_local(alta['name'])}.",
            'alerta', titulo='VENTO', detalhe=f"até {alta['value']:g} km/h {em_local(alta['name'])}"))
    batidas.append(batida(f'Manda pra quem sai cedo {estado.em()} hoje.', 'cta'))
    return batidas


def amanha_no_estado(snapshot, incerto):
    """Reel da noite (Bia, 18h): como fica o tempo AMANHÃ.

    Mesma espinha do `antes_de_sair`, lendo o bloco `tomorrow` do snapshot:
    abertura sem cartão, gancho de temperatura, as seis previsões, chance de
    chuva, vento (se relevante) e o fecho. Nenhuma batida sem o dado dela.
    """
    bloco = snapshot['forecast'].get('tomorrow') or {}
    if estado.regiao_id() == 'estado_mg':
        return boletim_minas(bloco, amanha=True)
    locs = bloco.get('locations') or []
    temps = [e for e in locs if number(e.get('max_c'))]
    if not temps:
        raise ValueError('Sem temperatura válida para amanhã')
    quente = max(temps, key=lambda e: e['max_c'])
    chuvas = [e for e in locs if number(e.get('rain_probability_pct'))]
    contraste = regional_contrast(locs)
    batidas = [batida(f'Amanhã, o tempo {estado.em()} fica assim.')]
    if incerto:
        batidas.append(batida('O cenário para amanhã ainda tem incerteza. Pode mudar até de manhã.'))
    destaque = gancho_destaque(snapshot, locs, 'amanha')
    if destaque is not None:
        batidas.append(destaque)
    elif contraste['temperature']['relevant']:
        alto, baixo = contraste['temperature']['high'], contraste['temperature']['low']
        vao = contraste['temperature']['spread']
        batidas.append(batida(
            f"A temperatura vai mudar pela região: {vao:g} graus separam "
            f"{alto['name']} de {baixo['name']}.",
            'gancho', numero=f'{vao:g}°', sub='DE DIFERENÇA AMANHÃ'))
    else:
        batidas.append(batida(
            f"A máxima chega a {quente['max_c']:g} graus {em_local(quente['name'])}.",
            'gancho', numero=f"{quente['max_c']:g}°", sub='MÁXIMA PREVISTA AMANHÃ'))
    # Sem repetir "amanhã" em toda frase: a abertura já disse, e o selo e os
    # cartões mostram AMANHÃ na tela.
    resumo = batida_resumo(locs, 'AMANHÃ NA REGIÃO')
    if resumo:
        batidas.append(resumo)
    batidas.append(batida_chuva(locs, amanha=True))
    if contraste['gust']['relevant']:
        alta = contraste['gust']['high']
        batidas.append(batida(
            f"Atenção ao vento: rajadas de até {alta['value']:g} quilômetros por hora "
            f"{em_local(alta['name'])}.",
            'alerta', titulo='VENTO AMANHÃ',
            detalhe=f"até {alta['value']:g} km/h {em_local(alta['name'])}"))
    batidas.append(batida(f'Manda pra quem vai sair amanhã {estado.em()}.', 'cta'))
    return batidas


def batida_resumo(locations, titulo, quando='', *, data_previsao=None):
    """Cartão das seis previsões obrigatórias (ver editorial/cinco.py)."""
    cidades = cinco_regioes(locations, data_previsao=data_previsao)
    if not cidades:
        return None
    return batida(fala_resumo(cidades, quando), 'resumo', cidades=cidades, titulo=titulo)


def prepare(snapshot, format='antes_de_sair', reference=None, history=None, topic=None):
    """`topic` vem da pauta escolhida: sem ele, `chove_onde` podia desenhar
    'chuva' enquanto a legenda (que segue a pauta) falava de 'temperatura' —
    a fila usa histórico na nota e o render não."""
    options = [c for c in evaluate(snapshot, history, reference) if c['format'] == format and c['status'] == 'ready']
    if topic:
        options = [c for c in options if c['topic'] == topic]
    if not options:
        raise ValueError(f'Formato {format} (tópico {topic or "qualquer"}) sem candidato válido e atualizado')
    candidate = options[0]
    locs = [e for e in snapshot['forecast']['today']['locations'] if e['id'] in candidate['location_ids']]
    if format == 'antes_de_sair':
        return {'title': TITLES[format], 'candidate': candidate, 'publication': False,
                'beats': antes_de_sair(snapshot, candidate['language'] == 'probabilistic')}
    if format == 'amanha_no_estado':
        return {'title': TITLES[format], 'candidate': candidate, 'publication': False,
                'beats': amanha_no_estado(snapshot, candidate['language'] == 'probabilistic')}
    lines = []
    if format == 'chove_onde':
        topic = candidate['topic']
        metric, unit = {'temperatura':('max_c','graus'), 'vento':('wind_gust_max_kmh','quilômetros por hora'),
                        'chuva':('rain_probability_pct','por cento')} .get(topic, ('rain_mm', 'milímetros'))
        janelas = []   # (leitura, [nomes]) na ordem em que aparecem
        for loc in locs[:3]:
            value = loc.get(metric)
            if number(value):
                label = {'temperatura':'máxima', 'vento':'rajadas', 'chuva':'probabilidade de chuva no dia'}.get(topic,'volume previsto no dia')
                lines.append(f"{em_local(loc['name'], inicio=True)}, {label} de {value:g} {unit}.")
            if loc.get('rain_window') and topic in {'chuva','janela_chuva'}:
                leitura = janela_legivel(loc['rain_window'], hora_agora())
                if not leitura:
                    continue
                grupo = next((g for g in janelas if g[0] == leitura), None)
                if grupo:
                    grupo[1].append(loc['name'])
                else:
                    janelas.append((leitura, [loc['name']]))
        # Uma frase por horário, com todos os bairros que o compartilham: o
        # Reel de 15/09/2026 repetia "das vinte e uma às vinte e três horas"
        # bairro a bairro.
        for leitura, nomes in janelas:
            onde = em_locais(nomes, inicio=True)
            if leitura['tipo'] == 'faixa':
                resto = '; pode haver intervalos sem chuva.'
                lines.append((
                    f"{onde}, a chuva é mais provável "
                    + faixa_falada(leitura['inicio'], leitura['fim']) + resto,
                    f"{onde}, a chuva é mais provável "
                    + faixa_escrita(leitura['inicio'], leitura['fim']) + resto))
            elif 'volume' in leitura:
                mm = _mm(leitura['volume'])
                resto = (f", com cerca de {mm} {'milímetro' if mm == 1 else 'milímetros'} na hora; "
                         'pode haver intervalos sem chuva.')
                lines.append((
                    f"{onde}, a chuva mais forte é " + pico_falado(leitura['hora']) + resto,
                    f"{onde}, a chuva mais forte é " + pico_escrito(leitura['hora']) + resto))
                continue
            else:
                resto = (f", com {leitura['probabilidade']:g} por cento; "
                         'pode haver intervalos sem chuva.')
                lines.append((
                    f"{onde}, a maior probabilidade é " + pico_falado(leitura['hora']) + resto,
                    f"{onde}, a maior probabilidade é " + pico_escrito(leitura['hora']) + resto))
        tem_prob = any(number(l.get('rain_probability_pct')) for l in locs)
        if topic in {'chuva','janela_chuva'}:
            lines.append('Probabilidade não indica chuva contínua durante todo o período.' if tem_prob
                         else 'O volume é a soma do dia: não significa chuva contínua.')
    elif format == 'fim_de_semana':
        for block in snapshot['forecast'].values():
            if not isinstance(block, dict) or block.get('date') not in candidate['extra']['dates']: continue
            values = [e for e in block['locations'] if number(e.get('max_c'))]
            if not values: raise ValueError('Fim de semana com dia sem dados')
            # A faixa de máximas de cada dia sai no cartão das cinco previsões
            # (resumo), inserido abaixo — repetir aqui dobraria a mesma frase.
        lines.append('Confira as próximas atualizações: o cenário pode mudar até o fim de semana.')
    elif format == 'vai_ao_jogo':
        event = candidate['extra']['event']; start,end = stamp(event['start_at']),stamp(event['end_at'])
        loc = locs[0]
        lines.append(f"Vai a {event['name']}? Confira a previsão para {loc['name']}.")
        for label, a, b in [('chegada',start-timedelta(hours=2),start),('evento',start,end),('saída',end,end+timedelta(hours=2))]:
            all_rows = [r for block in snapshot['forecast'].values() if isinstance(block,dict)
                        for e in block.get('locations',[]) if e['id']==loc['id'] for r in e.get('hourly',[])]
            rows = [r for r in all_rows if a<=stamp(r['time'])<b and number(r.get('precipitation_probability'))]
            if not rows: raise ValueError(f'Sem previsão para a janela de {label}')
            lines.append(f"Na {label}, a maior probabilidade de chuva por hora é de {max(r['precipitation_probability'] for r in rows):g} por cento.")
    elif format == 'vai_dar_praia':
        # Exige vínculo por local; um status global não autoriza praia específica.
        sea = snapshot['marine'].get('data',{}).get('points',{})
        reports = snapshot['beach_status'].get('data',{}).get('points',{})
        for loc in locs[:2]:
            report = reports.get(loc['id'],{})
            if not report.get('source_url','').startswith('https://') or not report.get('valid_until'):
                raise ValueError('Boletim oficial da praia sem origem ou validade')
            current = stamp(candidate['created_at'])
            if stamp(report['valid_until'])<=current: raise ValueError('Boletim de praia vencido')
            point=sea.get(loc['id'],{})
            if point.get('date')!=snapshot['forecast']['today'].get('date'): raise ValueError('Ondas fora da data consultada')
            wave = point.get('wave_height_max')
            if not number(wave): raise ValueError('Ondas indisponíveis para a praia')
            lines.append(f"{em_local(loc['name'], inicio=True)}, ondas modeladas de até {wave:g} metros. O boletim oficial informa: {report.get('classification','não informada')}.")
        lines.append('A previsão do tempo não determina segurança para banho. Confira a sinalização e os avisos locais.')
    if not lines: raise ValueError('Nenhuma fala sustentada pelos dados')
    if candidate['language']=='probabilistic': lines.insert(0,'O cenário ainda tem incerteza. Há possibilidade de mudança.')
    destinatario = {'vai_dar_praia': 'vai à praia', 'fim_de_semana': 'vai passear no fim de semana'}.get(format, f'vai sair {estado.em()}')
    lines.append(f'Manda pra quem {destinatario}.')
    beats=[batida(line[0], legenda=line[1]) if isinstance(line, tuple) else batida(line) for line in lines]
    # Todo Reel mostra as seis previsões obrigatórias, antes do fecho.
    resumos = []
    if format == 'fim_de_semana':
        for block in snapshot['forecast'].values():
            if not isinstance(block, dict) or block.get('date') not in candidate['extra']['dates']:
                continue
            dia = 'SÁBADO' if stamp(block['date']+'T12:00:00'+estado.offset_iso()).weekday()==5 else 'DOMINGO'
            resumos.append(batida_resumo(block['locations'], f'{dia} NA REGIÃO', f'No {dia.lower()}'))
        # Os dias vêm antes do aviso de que o cenário pode mudar.
        posicao = len(beats) - 2
    else:
        resumos.append(batida_resumo(snapshot['forecast']['today']['locations'], 'HOJE NA REGIÃO'))
        posicao = len(beats) - 1
    for r in reversed(resumos):
        if r:
            beats.insert(max(posicao, 0), r)
    if format == 'fim_de_semana' and beats[0]['tipo'] == 'resumo':
        # Abre sem cartão (o apresentador precisa aparecer na primeira batida).
        beats.insert(0, batida(f'Veja como fica o fim de semana {estado.em()}.'))
    return {'title':TITLES[format], 'candidate':candidate,'beats':beats,'publication':False}
