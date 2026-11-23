"""Preposição certa antes do nome do lugar: na Tijuca, no Méier, em Copacabana.

Usado pela fala do Reel, pela legenda e pelas respostas do atendimento. Fica em
`geo` (e sem dependência nenhuma) porque o serviço do Render importa daqui e não
pode carregar o motor editorial.
"""
from __future__ import annotations

# "Em Barra da Tijuca", "Em Centro": um Reel já saiu assim. Lugar com artigo
# — na Tijuca, no Recife, nas Barcas — precisa dele na fala. As listas são de
# cada estado (config/estado.yaml); nome fora delas fica com "em", que é o
# certo para a maior parte dos municípios.
from .. import estado


def em_local(nome: str, inicio: bool = False) -> str:
    """'Barra da Tijuca' -> 'na Barra da Tijuca'; 'Centro' -> 'no Centro'."""
    listas = estado.preposicoes()
    prep = next((p for p in ('na', 'no', 'nas', 'nos') if nome in listas[p]), 'em')
    texto = f'{prep} {nome}'
    return texto[0].upper() + texto[1:] if inicio else texto


def em_locais(nomes: list[str], inicio: bool = False) -> str:
    """['Barra da Tijuca', 'Campo Grande'] -> 'na Barra da Tijuca e em Campo Grande'."""
    partes = [em_local(n) for n in nomes]
    texto = partes[0] if len(partes) == 1 else ', '.join(partes[:-1]) + ' e ' + partes[-1]
    return texto[0].upper() + texto[1:] if inicio else texto
