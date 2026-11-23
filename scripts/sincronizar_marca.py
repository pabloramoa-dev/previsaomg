"""Regrava os arquivos que carregam a marca do canal a partir de config/estado.yaml.

    python -m scripts.sincronizar_marca          # regrava
    python -m scripts.sincronizar_marca --check  # falha se algo estiver fora de sincronia

Cobre o card "Seguir", o avatar e config/brand.yml. Rodado pelo gerador de
estado, pelo render e pelo CI (com --check).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / 'hyperframes'))

from src.previsao import estado  # noqa: E402


def _brand() -> str:
    caminho = estado.config_dir() / 'brand.yml'
    dados = yaml.safe_load(caminho.read_text(encoding='utf-8'))
    dados['brand'].update(name=estado.marca(), handle=estado.arroba(),
                          promise=estado.slogan(), timezone=estado.nome_fuso())
    return yaml.safe_dump(dados, allow_unicode=True, sort_keys=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()

    import compor
    alvos = {RAIZ / 'hyperframes/compositions/instagram-follow.html': compor.card_seguir_html(),
             RAIZ / 'hyperframes/assets/avatar.svg': compor.avatar_svg(),
             estado.config_dir() / 'brand.yml': _brand()}
    fora = [c for c, texto in alvos.items()
            if not c.exists() or c.read_text(encoding='utf-8') != texto]
    if args.check:
        if fora:
            raise SystemExit('marca fora de sincronia com estado.yaml: '
                             + ', '.join(str(c.relative_to(RAIZ)) for c in fora)
                             + '\nrode: python -m scripts.sincronizar_marca')
        print(f'marca em sincronia ({estado.arroba()})')
        return
    for caminho in fora:
        caminho.write_text(alvos[caminho], encoding='utf-8')
        print('regravado:', caminho.relative_to(RAIZ))
    if not fora:
        print('nada a regravar')


if __name__ == '__main__':
    main()
