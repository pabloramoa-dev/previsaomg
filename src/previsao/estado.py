"""Identidade do canal: tudo que muda de um estado para outro.

O motor (coleta, pauta, roteiro, vídeo, publicação) é o mesmo em todos os
repositórios. O que é próprio de cada um — nome, @, fuso, as seis regiões do
quadro, frases que citam o lugar, cenário do telão — vive em
`config/estado.yaml` e é lido por aqui. Nenhum outro módulo deve trazer o nome
de um estado, de uma cidade ou de uma conta escrito no código.

`PREVISAO_CONFIG_DIR` troca a pasta de configuração inteira. Os testes usam
isso para rodar o motor sobre o estado de referência (`tests/ref_config`), de
modo que a mesma bateria valida o motor em qualquer repositório.
"""
from __future__ import annotations

import os
from datetime import timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]

OBRIGATORIOS = ('uf', 'nome', 'curto', 'artigo', 'marca', 'marca_falada', 'handle',
                'slogan', 'repo', 'fuso_utc', 'timezone', 'recorte', 'litoral',
                'cenario', 'titulos', 'hashtags', 'legenda', 'regioes')
FORMATOS = ('antes_de_sair', 'chove_onde', 'fim_de_semana', 'vai_dar_praia',
            'vai_ao_jogo', 'amanha_no_estado')
MINIMO_REGIOES = 6


def config_dir() -> Path:
    return Path(os.environ.get('PREVISAO_CONFIG_DIR') or ROOT / 'config')


@lru_cache(maxsize=None)
def _carregar(pasta: str) -> dict[str, Any]:
    caminho = Path(pasta) / 'estado.yaml'
    if not caminho.exists():
        raise FileNotFoundError(f'configuracao ausente: {caminho}')
    dados = yaml.safe_load(caminho.read_text(encoding='utf-8'))
    validar(dados)
    return dados


def carregar() -> dict[str, Any]:
    return _carregar(str(config_dir()))


def limpar_cache() -> None:
    _carregar.cache_clear()


def validar(d: Any) -> None:
    """Falha cedo, com a mensagem do campo que falta, em vez de em produção."""
    if not isinstance(d, dict):
        raise ValueError('estado.yaml invalido (esperado mapa)')
    faltam = [k for k in OBRIGATORIOS if k not in d]
    if faltam:
        raise ValueError(f'estado.yaml sem os campos: {", ".join(faltam)}')
    if d['artigo'] not in ('o', 'a', 'os', 'as', ''):
        raise ValueError(f"artigo invalido: {d['artigo']!r}")
    if not isinstance(d['fuso_utc'], int) or not -5 <= d['fuso_utc'] <= -2:
        raise ValueError(f"fuso_utc fora do Brasil: {d['fuso_utc']!r}")
    if str(d['handle']).startswith('@') or d['handle'] != str(d['handle']).casefold():
        raise ValueError('handle vai sem arroba e em minusculas')
    r = d['recorte']
    if not (r['lat_min'] < r['lat_max'] and r['lon_min'] < r['lon_max']):
        raise ValueError('recorte geografico invertido')
    for chave in ('antes_de_sair', 'amanha_no_estado'):
        if not d['titulos'].get(chave):
            raise ValueError(f'titulos.{chave} ausente')
    if not d['hashtags'].get('padrao'):
        raise ValueError('hashtags.padrao ausente')
    regioes_ = d['regioes']
    if len(regioes_) < MINIMO_REGIOES:
        raise ValueError(f'o quadro precisa de {MINIMO_REGIOES} regioes; ha {len(regioes_)}')
    rotulos = [x.get('rotulo') for x in regioes_]
    if len(set(rotulos)) != len(rotulos) or not all(rotulos):
        raise ValueError('regioes com rotulo repetido ou vazio')
    for x in regioes_:
        if not x.get('ids'):
            raise ValueError(f"regiao {x['rotulo']!r} sem pontos preferidos")


# ------------------------------------------------------------ identidade ---
def uf() -> str:
    return carregar()['uf']


def handle() -> str:
    return carregar()['handle']


def arroba() -> str:
    return '@' + handle()


def marca() -> str:
    return carregar()['marca']


def marca_falada() -> str:
    return carregar()['marca_falada']


def slogan() -> str:
    return carregar()['slogan']


def regiao_id() -> str:
    return carregar().get('regiao_id') or uf().casefold()


def cenario() -> str:
    return carregar()['cenario']


def rotulo_ticker() -> str:
    """Selo curto da faixa de notícias: o nome do lugar, ou a sigla se for longo."""
    proprio = carregar().get('ticker')
    if proprio:
        return str(proprio)
    return curto().upper() if len(curto()) <= 8 else uf()


def litoral() -> bool:
    return bool(carregar()['litoral'])


# ---------------------------------------------------------------- lugar ---
_EM = {'o': 'no', 'a': 'na', 'os': 'nos', 'as': 'nas', '': 'em'}
_DE = {'o': 'do', 'a': 'da', 'os': 'dos', 'as': 'das', '': 'de'}


def curto() -> str:
    return carregar()['curto']


def com_artigo() -> str:
    """'o Rio', 'a Bahia', 'Minas'."""
    artigo = carregar()['artigo']
    return f'{artigo} {curto()}' if artigo else curto()


def em(inicio: bool = False) -> str:
    """'no Rio', 'na Bahia', 'em Minas'."""
    texto = f"{_EM[carregar()['artigo']]} {curto()}"
    return texto[0].upper() + texto[1:] if inicio else texto


def de() -> str:
    """'do Rio', 'da Bahia', 'de Minas'."""
    return f"{_DE[carregar()['artigo']]} {curto()}"


# ----------------------------------------------------------------- fuso ---
def fuso_utc() -> int:
    """Horas em relação ao UTC. `FUSO_UTC` no ambiente vence (workflows)."""
    bruto = os.environ.get('FUSO_UTC', '').strip()
    if bruto:
        return int(bruto)
    return int(carregar()['fuso_utc'])


def fuso() -> timezone:
    return timezone(timedelta(hours=fuso_utc()))


def offset_iso() -> str:
    """'-03:00', '-04:00', '-05:00' — sufixo dos carimbos de hora local."""
    h = fuso_utc()
    return f"{'-' if h < 0 else '+'}{abs(h):02d}:00"


def nome_fuso() -> str:
    return carregar()['timezone']


def recorte() -> dict[str, float]:
    return carregar()['recorte']


# ------------------------------------------------------------- editorial ---
def titulos() -> dict[str, str]:
    base = {'chove_onde': 'O TEMPO MUDA ONDE?', 'vai_dar_praia': 'VAI DAR PRAIA?',
            'fim_de_semana': 'SEU FIM DE SEMANA', 'vai_ao_jogo': 'VAI AO JOGO?'}
    base.update(carregar()['titulos'])
    return base


def hashtags(formato: str | None = None) -> str:
    tags = carregar()['hashtags']
    return tags.get(formato) or tags['padrao']


def legenda(chave: str, padrao: str = '') -> str:
    return carregar()['legenda'].get(chave, padrao)


def regioes() -> tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]:
    """(rótulo na tela, ids preferidos em ordem, zonas aceitas como reserva)."""
    return tuple((x['rotulo'], tuple(x['ids']), tuple(x.get('zonas') or ()))
                 for x in carregar()['regioes'])


def falado() -> dict[str, str]:
    return dict(carregar().get('falado') or {})


def preposicoes() -> dict[str, set[str]]:
    bruto = dict(carregar().get('preposicoes') or {})
    # YAML le a chave `no` sem aspas como o booleano False: aceitar os dois.
    if False in bruto and 'no' not in bruto:
        bruto['no'] = bruto[False]
    return {k: set(bruto.get(k) or ()) for k in ('na', 'no', 'nas', 'nos')}


def destaques_semana() -> list[dict[str, Any]]:
    return list(carregar().get('destaques_semana') or [])


def cargo(personagem: str) -> str:
    padrao = {'bira': f'TEMPO {em().upper()} E REGIÃO',
              'bia': f'O TEMPO DE AMANHÃ {em().upper()}'}
    return ((carregar().get('apresentadores') or {}).get(personagem) or {}).get(
        'cargo') or padrao.get(personagem, '')


def formato_ligado(formato: str) -> bool:
    """`vai_dar_praia` só existe onde há litoral; os demais, salvo veto explícito."""
    desligados = set(carregar().get('formatos_desligados') or ())
    if formato == 'vai_dar_praia' and not litoral():
        return False
    return formato not in desligados
