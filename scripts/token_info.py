"""Tipo e validade do IG_ACCESS_TOKEN, sem revelar a credencial.

O @previsaomg publica por graph.facebook.com com um token de USUÁRIO DO
SISTEMA do portfólio BM01 (login unificado). Esse token
não expira, então não existe "renovação" a agendar: o antigo
graph.instagram.com/refresh_access_token só vale para token do login do
Instagram (IGAA...) e não serve para ele.

Este script consulta /debug_token e devolve só metadados: tipo, app, validade,
escopos. Nunca imprime o token, nem a URL da chamada, nem a mensagem crua de
exceção do requests (que pode conter a URL com o token).

Uso:
    python -m scripts.token_info                # imprime JSON e escreve no resumo
    python -m scripts.token_info --exigir-sem-expiracao   # sai 1 se expira
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import requests

DIAS_AVISO = 15


def consultar(token: str, versao: str) -> dict:
    try:
        r = requests.get(f'https://graph.facebook.com/{versao}/debug_token',
                         params={'input_token': token, 'access_token': token},
                         timeout=30)
    except requests.RequestException as erro:
        return {'status': 'inconclusivo', 'motivo': type(erro).__name__}
    try:
        corpo = r.json()
    except ValueError:
        return {'status': 'inconclusivo', 'motivo': f'http_{r.status_code}'}
    if 'error' in corpo:
        e = corpo['error']
        info = {'status': 'inconclusivo', 'motivo': f"meta_{e.get('code')}",
                'mensagem': str(e.get('message', ''))[:160]}
        # Token de usuário do sistema não é "dono/desenvolvedor" do app e não
        # consegue se auto-inspecionar no /debug_token. Então descreve o dono
        # do token (/me) e as permissões concedidas, que não são segredo.
        info.update(identidade(token, versao))
        return info
    d = corpo.get('data') or {}
    expira = int(d.get('expires_at') or 0)
    acesso = int(d.get('data_access_expires_at') or 0)
    info = {
        'status': 'ok' if d.get('is_valid') else 'invalido',
        'tipo': d.get('type'),
        'app_id': d.get('app_id'),
        'aplicativo': d.get('application'),
        'expira': 'nunca' if expira == 0 else time.strftime('%Y-%m-%d', time.gmtime(expira)),
        'acesso_a_dados_expira': 'nunca' if acesso == 0 else time.strftime('%Y-%m-%d', time.gmtime(acesso)),
        'escopos': sorted(d.get('scopes') or []),
    }
    agora = time.time()
    if expira and expira - agora < DIAS_AVISO * 86400:
        info['alerta'] = 'expira_em_breve'
    if acesso and acesso - agora < DIAS_AVISO * 86400:
        info['alerta'] = 'acesso_a_dados_expira_em_breve'
    return info


def identidade(token: str, versao: str) -> dict:
    base = f'https://graph.facebook.com/{versao}'
    saida: dict = {}
    try:
        me = requests.get(f'{base}/me', params={'fields': 'id,name', 'access_token': token},
                          timeout=30).json()
        if 'error' not in me:
            saida['dono_do_token'] = me.get('name')
        perms = requests.get(f'{base}/me/permissions', params={'access_token': token},
                             timeout=30).json()
        if 'error' not in perms:
            saida['permissoes_concedidas'] = sorted(
                p['permission'] for p in perms.get('data', []) if p.get('status') == 'granted')
    except (requests.RequestException, ValueError) as erro:
        saida['identidade'] = f'inconclusivo:{type(erro).__name__}'
    return saida


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--exigir-sem-expiracao', action='store_true')
    args = p.parse_args()
    token = os.environ.get('IG_ACCESS_TOKEN', '')
    versao = os.environ.get('META_GRAPH_VERSION') or 'v26.0'
    info = consultar(token, versao) if token else {'status': 'sem_token'}
    print(json.dumps(info, ensure_ascii=False))
    resumo = os.environ.get('GITHUB_STEP_SUMMARY')
    if resumo:
        with open(resumo, 'a', encoding='utf-8') as f:
            f.write('## Token da Meta (sem revelar a credencial)\n\n```json\n'
                    + json.dumps(info, ensure_ascii=False, indent=2) + '\n```\n')
    if args.exigir_sem_expiracao:
        if info.get('status') == 'inconclusivo':
            print('::warning::A Meta não respondeu ao /debug_token; a validade não foi '
                  'conferida. O Health (verify_destination) continua valendo.')
            return
        ruim = info.get('status') != 'ok' or info.get('expira') != 'nunca' or 'alerta' in info
        if ruim:
            print('::error::Token não é permanente ou expira em breve: reautorize o '
                  'usuário do sistema no BM01 e grave o novo valor em IG_ACCESS_TOKEN.')
            sys.exit(1)


if __name__ == '__main__':
    main()
