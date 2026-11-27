"""Publica nos Stories o mesmo vídeo do Reel do Bira (turno da manhã).

Roda logo depois do Reel, no mesmo job, com a mesma URL do MP4. Uma vez por
Reel: o registro `data/stories.json` guarda a chave da pauta (dedupe_key) e o
media_id do Story, e uma chave já registrada nunca publica de novo.

Falha aqui não desfaz o Reel (o passo do workflow usa continue-on-error) e
nunca imprime credencial: erros saem só com o tipo da exceção.

Uso:
    python -m scripts.publicar_story --video-url URL --chave DEDUPE \
        --registro data/stories.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.previsao.publish import instagram  # noqa: E402


def _resumo(texto: str) -> None:
    destino = os.environ.get('GITHUB_STEP_SUMMARY')
    if destino:
        with open(destino, 'a', encoding='utf-8') as f:
            f.write(texto)


def carregar(caminho: Path) -> dict:
    return json.loads(caminho.read_text(encoding='utf-8')) if caminho.exists() else {}


def publicar(video_url: str, chave: str, registro: Path) -> str | None:
    dados = carregar(registro)
    if chave in dados:
        print(f'story_ja_publicado= {dados[chave].get("media_id")}')
        _resumo(f'### Story já publicado para esta pauta\n\n- media_id: `{dados[chave].get("media_id")}`\n')
        return None
    destino = instagram.verify_destination()
    print('destino_verificado=', destino.get('username'))
    container = instagram.create_story(video_url)
    instagram.wait_ready(container)
    media_id = instagram.publish(container)
    agora = datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec='seconds')
    dados[chave] = {'media_id': media_id, 'published_at': agora}
    registro.parent.mkdir(parents=True, exist_ok=True)
    registro.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('story_media_id=', media_id)
    _resumo(f'### Story publicado\n\n- media_id: `{media_id}`\n- pauta: `{chave}`\n')
    return media_id


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--video-url', required=True)
    p.add_argument('--chave', required=True)
    p.add_argument('--registro', default='data/stories.json')
    args = p.parse_args()
    try:
        publicar(args.video_url, args.chave, Path(args.registro))
    except Exception as erro:  # sem str(erro): pode conter URL com token
        print(f'::error::Story não publicado ({type(erro).__name__}). O Reel não é afetado.')
        _resumo(f'### Story NÃO publicado\n\nErro: `{type(erro).__name__}`. O Reel segue publicado.\n')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
