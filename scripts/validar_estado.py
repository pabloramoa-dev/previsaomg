"""Confere se a configuração do canal está coerente antes de qualquer Reel.

    python -m scripts.validar_estado

Roda no CI. Falha com a lista de problemas encontrados; nada aqui toca a rede.
O que se confere:
  - estado.yaml completo (campos, artigo, fuso, recorte, seis regiões);
  - locais.yaml válido e dentro do recorte do estado;
  - cada região do quadro aponta para pontos que existem, e o preferido de
    cada uma é âncora (nível 1), ou seja, é coletado em todo Reel;
  - workflows no mesmo fuso do estado e com alvo às 6h e às 18h locais;
  - a lista de isolamento não proíbe o próprio canal.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src.previsao import config, estado  # noqa: E402


def problemas(raiz: Path = RAIZ) -> list[str]:
    erros: list[str] = []
    try:
        dados = estado.carregar()
    except (FileNotFoundError, ValueError) as exc:
        return [f'estado.yaml: {exc}']
    try:
        lugares = config.load_places()
    except (FileNotFoundError, ValueError) as exc:
        return [f'locais.yaml: {exc}']

    por_id = {loc['id']: loc for loc in lugares['locations']}
    zonas = set(lugares.get('zones') or {})
    for rotulo, ids, reservas in estado.regioes():
        faltam = [i for i in ids if i not in por_id]
        if faltam:
            erros.append(f'região {rotulo!r}: pontos inexistentes em locais.yaml: {faltam}')
            continue
        if por_id[ids[0]]['sample_tier'] != 1:
            erros.append(f'região {rotulo!r}: o preferido {ids[0]!r} precisa ser nível 1')
        fora = [z for z in reservas if z not in zonas]
        if fora:
            erros.append(f'região {rotulo!r}: zonas de reserva inexistentes: {fora}')

    for turno, hora in (('manha', 6), ('noite', 18)):
        caminho = raiz / '.github' / 'workflows' / f'reel_{turno}.yml'
        if not caminho.exists():
            erros.append(f'{caminho.name} ausente')
            continue
        env = (yaml.safe_load(caminho.read_text(encoding='utf-8')) or {}).get('env') or {}
        if str(env.get('FUSO_UTC')) != str(dados['fuso_utc']):
            erros.append(f"{caminho.name}: FUSO_UTC={env.get('FUSO_UTC')} difere de "
                         f"estado.yaml ({dados['fuso_utc']})")
        alvo = str(env.get('ALVO', ''))
        if not alvo[:2].isdigit() or int(alvo[:2]) != hora:
            erros.append(f'{caminho.name}: ALVO={alvo!r}; esperado {hora:02d}:MM')

    iso = raiz / 'config' / 'isolamento.yaml'
    if iso.exists():
        lista = {str(t).casefold() for t in
                 (yaml.safe_load(iso.read_text(encoding='utf-8')) or {}).get('proibidos') or []}
        proprios = {estado.handle(), estado.arroba(), dados['repo'].split('/')[-1]}
        if lista & proprios:
            erros.append(f'isolamento.yaml proíbe o próprio canal: {sorted(lista & proprios)}')
    return erros


def main() -> None:
    erros = problemas()
    if erros:
        raise SystemExit('configuração do canal com problemas:\n  - ' + '\n  - '.join(erros))
    print(f'estado ok: {estado.marca()} ({estado.arroba()}), '
          f'{len(estado.regioes())} regiões, fuso UTC{estado.offset_iso()}')


if __name__ == '__main__':
    main()
