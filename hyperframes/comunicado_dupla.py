# -*- coding: utf-8 -*-
"""
comunicado_dupla.py — Reel AVULSO com Bira e Bia conversando, sob pedido.

Para o que não é o boletim das 6h/18h:
  - ALERTA de tempo (tempestade, granizo, vendaval, calor, frio, virada brusca)
  - EVENTO / divulgação (agenda do fim de semana, show, festival, parceiro)
  - LEMBRETE / aviso (algo que o canal quer lembrar ou anunciar)

Tudo sai de UM arquivo de roteiro em YAML (veja comunicados/README.md e os
exemplos em comunicados/). O vídeo usa o mesmo estúdio HyperFrames dos Reels
diários, com os dois personagens na bancada, cada um com a sua voz Kokoro e o
seu lip sync, mais os recursos gratuitos de hyperframes/assets/dupla/:
  - SFX Kit (github.com/wyzowl/sfx-kit, CC0) no ponto de sincronia do guia
  - trilha "Sunset on the Beach" (Komiku, CC0) com ducking (desligada em alerta)
  - normalização EBU R128 a -14 LUFS (ffmpeg-normalize)
  - figurantes Open Peeps (CC0, via DiceBear) e fundo geopattern (MIT) no CTA

Uso:
    python hyperframes/comunicado_dupla.py comunicados/exemplo_alerta.yaml --out output/REEL.mp4
    # --ignorar-validade só para testar um roteiro vencido (nunca publicar)
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import yaml

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(AQUI))

import gerar_hf as HF  # noqa: E402
import compor as C  # noqa: E402
from src.previsao import estado  # noqa: E402
from src.previsao.render.characters.amplitude import gerar_cues  # noqa: E402
from src.previsao.render.characters.pipeline import PRESETS  # noqa: E402
from src.previsao.render.characters import kokoro as KK  # noqa: E402

SR = 44100
DUPLA = AQUI / 'assets' / 'dupla'
MUSICA = DUPLA / 'trilha_komiku_sunset_on_the_beach.ogg'
GAP_MESMO, GAP_TROCA = 0.24, 0.34
TIPOS = ('alerta', 'evento', 'lembrete', 'aviso')
CENAS = ('abertura', 'alerta', 'numero', 'cartaz', 'frase', 'cta')
# tipo interno da batida (o compor.py decide animações e legenda por ele)
TIPO_BATIDA = {'abertura': 'nenhum', 'alerta': 'alerta', 'numero': 'gancho', 'cartaz': 'cartaz',
               'frase': 'nenhum', 'cta': 'cta'}
SELO_HUD = {'alerta': 'ALERTA', 'evento': 'AGENDA', 'lembrete': 'LEMBRETE', 'aviso': 'AVISO'}
CEU_PADRAO = {'alerta': 'tempestade', 'evento': 'sol', 'lembrete': 'sol', 'aviso': 'nublado'}
TRILHA_PADRAO = {'alerta': False, 'evento': True, 'lembrete': True, 'aviso': True}
FUSO = ZoneInfo('America/Sao_Paulo')
esc = C.esc


def run(cmd, **kw):
    subprocess.run([str(x) for x in cmd], check=True, **kw)


# ----------------------------------------------------------- roteiro ---
class RoteiroInvalido(ValueError):
    pass


def _subst(txt):
    """{arroba}, {marca} e {curto} viram a identidade do canal (config/estado.yaml)."""
    return (str(txt).replace('{arroba}', estado.arroba()).replace('{marca}', estado.marca_falada())
            .replace('{curto}', estado.carregar()['curto']))


def carregar_roteiro(caminho, agora=None, ignorar_validade=False):
    r = yaml.safe_load(Path(caminho).read_text(encoding='utf-8'))
    if not isinstance(r, dict):
        raise RoteiroInvalido('roteiro vazio ou não é um mapa YAML')
    tipo = r.get('tipo')
    if tipo not in TIPOS:
        raise RoteiroInvalido(f'tipo deve ser um de {TIPOS}')
    apresenta = r.get('apresenta', 'bia')
    if apresenta not in ('bia', 'bira'):
        raise RoteiroInvalido('apresenta deve ser bia ou bira')
    outro = 'bira' if apresenta == 'bia' else 'bia'
    falas = r.get('falas') or []
    if len(falas) < 3:
        raise RoteiroInvalido('são necessárias pelo menos 3 falas (abertura, conteúdo e CTA)')
    if falas[0].get('cena') != 'abertura':
        raise RoteiroInvalido('a primeira fala tem de ser cena: abertura')
    if falas[-1].get('cena') != 'cta':
        raise RoteiroInvalido('a última fala tem de ser cena: cta')
    validade = r.get('validade')
    if validade:
        limite = dt.datetime.fromisoformat(str(validade))
        if limite.tzinfo is None:
            limite = limite.replace(tzinfo=FUSO)
        agora = agora or dt.datetime.now(FUSO)
        if agora > limite and not ignorar_validade:
            raise RoteiroInvalido(f'roteiro vencido em {limite:%d/%m %H:%M}: não renderiza nem publica')
    legenda = _subst(r.get('legenda') or '').strip()
    if estado.arroba() not in legenda.casefold():
        raise RoteiroInvalido(f'a legenda precisa citar {estado.arroba()} (o publicador exige)')

    bat, falante = [], []
    prox = apresenta
    for i, f in enumerate(falas):
        cena = f.get('cena', 'frase')
        if cena not in CENAS:
            raise RoteiroInvalido(f'fala {i}: cena desconhecida {cena!r} (use {CENAS})')
        quem = f.get('quem') or (apresenta if i == len(falas) - 1 else prox)
        if quem not in ('bia', 'bira'):
            raise RoteiroInvalido(f'fala {i}: quem deve ser bia ou bira')
        texto = _subst(f.get('fala') or '').strip()
        if not texto:
            raise RoteiroInvalido(f'fala {i} vazia')
        dados = {k: _subst(v) for k, v in f.items()
                 if k not in ('cena', 'quem', 'fala', 'legenda', 'continua') and isinstance(v, (str, int, float))}
        bat.append(dict(tipo=TIPO_BATIDA[cena], cena=cena, fala=texto,
                        legenda=_subst(f.get('legenda') or texto), dados=dados,
                        continua=bool(f.get('continua'))))
        falante.append(quem)
        prox = outro if quem == apresenta else apresenta
    if falante[0] != apresenta:
        raise RoteiroInvalido('a abertura é de quem apresenta')
    meta = dict(tipo=tipo, apresenta=apresenta, outro=outro,
                titulo=_subst(r.get('titulo') or SELO_HUD[tipo]),
                etiquetas=[_subst(e) for e in (r.get('etiquetas') or [])][:2],
                selo=_subst(r.get('selo') or SELO_HUD[tipo]),
                ceu=r.get('ceu') or CEU_PADRAO[tipo],
                trilha=bool(r.get('trilha', TRILHA_PADRAO[tipo])),
                ticker=[_subst(t) for t in (r.get('ticker') or [])],
                legenda=legenda, fonte=_subst(r.get('fonte') or ''))
    return meta, bat, falante


def agrupar(bat):
    cenas = []
    for i, b in enumerate(bat):
        if cenas and b['continua'] and cenas[-1]['tipo'] == b['cena'] and b['cena'] in ('frase', 'cta'):
            cenas[-1]['batidas'].append(i)
        else:
            cenas.append({'tipo': b['cena'], 'batidas': [i]})
    for j, c in enumerate(cenas):
        c['id'] = f's{j}-{c["tipo"]}'
    return cenas


# ------------------------------------------------------------- vozes ---
def narrar(bat, falante, work):
    from kokoro_onnx import Kokoro
    k = Kokoro(*KK.garantir_modelo())
    blocos, segs, t = [], [], 0.0
    for i, (b, quem) in enumerate(zip(bat, falante)):
        pr = PRESETS[quem]
        s, sr = k.create(b['fala'], voice=KK.estilo(k, pr['voice']), speed=pr['speed'], lang='pt-br')
        s = KK.resample_44100(np.asarray(s, dtype=np.float32), sr)
        prox = falante[i + 1] if i + 1 < len(bat) else quem
        n_gap = int((GAP_TROCA if prox != quem else GAP_MESMO) * SR)
        segs.append({'i': i, 'quem': quem, 'ini': round(t, 3), 'fim_fala': round(t + len(s) / SR, 3),
                     'fim': round(t + (len(s) + n_gap) / SR, 3), 'texto': b['fala']})
        blocos += [(s, quem), (np.zeros(n_gap, np.float32), None)]
        t += (len(s) + n_gap) / SR
        print(f'  [{quem:4s}] {segs[-1]["ini"]:5.2f}s  {b["fala"]}')
    voz = np.concatenate([b for b, _ in blocos])
    pk = float(np.abs(voz).max()) or 1.0
    pistas = {q: np.concatenate([b if w == q else np.zeros_like(b) for b, w in blocos]) / pk * 0.97
              for q in ('bia', 'bira')}
    HF.gravar_wav(work / 'raw.wav', voz / pk * 0.97, SR)
    (work / 'roteiro.txt').write_text('\n'.join(f'[{q}] {b["fala"]}' for b, q in zip(bat, falante)),
                                      encoding='utf-8')
    return segs, pistas, work / 'raw.wav'


# --------------------------------------------------------------- SFX ---
class Sfx:
    def __init__(self, dur):
        self.S = json.loads((DUPLA / 'sfx.json').read_text(encoding='utf-8'))['sons']
        self.n = int(dur * SR)
        self.bus = np.zeros(self.n, np.float32)
        self.cache, self.usados = {}, []

    def _carregar(self, sid):
        if sid not in self.cache:
            pcm = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(DUPLA / self.S[sid]['arquivo']),
                                           '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'])
            self.cache[sid] = np.frombuffer(pcm, np.float32).copy()
        return self.cache[sid]

    def por(self, sid, momento, ganho=0.5):
        """Guia do SFX Kit: início = momento − sync_at."""
        x = self._carregar(sid)
        ini = int(round((momento - self.S[sid]['sync_at']) * SR))
        if ini < 0:
            x, ini = x[-ini:], 0
        m = min(len(x), self.n - ini)
        if m > 0:
            self.bus[ini:ini + m] += x[:m] * ganho
            self.usados.append((round(momento, 2), sid))


def planejar_sfx(p, n_titulo):
    sx = Sfx(p['dur'])
    cenas = p['cenas']
    fins = [cenas[k + 1]['ini'] if k + 1 < len(cenas) else p['dur'] for k in range(len(cenas))]
    for T, tipo in zip(p['cortes'], p['transicoes']):
        if tipo == 'whip-pan':
            sx.por('whoosh-medium-soft', T + 0.30, 0.55)
        elif tipo == 'glitch':
            sx.por('digital-glitch-clear', T + 0.02, 0.40)
            sx.por('whoosh-fast-soft', T + 0.20, 0.30)
        else:
            sx.por('shimmer-short-soft', T + 0.20, 0.45)
    for c, fim in zip(cenas, fins):
        ini = c['ini']
        if c['tipo'] == 'abertura':
            sx.por('pop-medium-in', ini + 0.05, 0.45)
            sx.por('pop-medium-in', ini + 0.13, 0.45)
            t_imp = ini + 0.02 + 0.28 + 0.1 * (n_titulo - 1)
            sx.por('cinematic-drum-big', t_imp, 0.55)
            if p['meta_tipo'] == 'alerta':
                sx.por('notification-alert-clear', t_imp + 0.35, 0.40)
            else:
                sx.por('move-bounce', t_imp + 0.12, 0.30)
        elif c['tipo'] == 'numero':
            sx.por('data-countup-short', ini + 0.15, 0.35)
            sx.por('data-number-land', ini + 0.75, 0.45)
            sx.por('impact-medium-soft', ini + 0.55, 0.40)
            sx.por('impact-light-firm', ini + min(1.4, (fim - ini) * 0.45) + 0.28, 0.50)
        elif c['tipo'] == 'alerta':
            sx.por('notification-alert-clear', ini + 0.05, 0.40)
            sx.por('boom-hit-medium', ini + 0.47, 0.45)
            sx.por('impact-light-firm', ini + min(1.2, (fim - ini) * 0.4) + 0.28, 0.50)
        elif c['tipo'] == 'cartaz':
            sx.por('whoosh-fast-soft', ini + 0.12, 0.35)
            for k in range(3):
                sx.por(f'tone-step-{k + 1}', ini + 0.55 + 0.12 * k, 0.22)
            sx.por('impact-light-firm', ini + 0.95, 0.50)
        elif c['tipo'] == 'cta':
            sx.por('move-bounce', ini + 0.10, 0.35)
            for k in range(7):
                sx.por('pop-small-in', ini + 0.55 + 0.09 * k, 0.40)
    sx.por('notification-message-in-soft', p['tSiga'] + 0.15, 0.40)
    sx.por('sting-warm-short', p['dur'] - 1.75, 0.50)
    return sx


def mixar(work, narr, sfx_bus, dur, com_trilha):
    HF.gravar_wav(work / 'sfx.wav', sfx_bus, SR)
    mix = work / 'mix_bruto.wav'
    if com_trilha:
        grafo = (f'[1:a]atrim=0:{dur + 0.5},asetpts=PTS-STARTPTS,volume=0.32,afade=t=in:d=0.6,'
                 f'afade=t=out:st={max(0, dur - 1.6):.2f}:d=1.5,aformat=channel_layouts=stereo[mus];'
                 '[0:a]aformat=channel_layouts=stereo,asplit=2[voz][side];'
                 # DUCKING: a voz comprime a música enquanto alguém fala
                 '[mus][side]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=350:makeup=1[duck];'
                 '[2:a]aformat=channel_layouts=stereo[fx];'
                 '[voz][duck][fx]amix=inputs=3:normalize=0:duration=first,alimiter=limit=0.95[out]')
        ent = ['-i', narr, '-stream_loop', '-1', '-i', MUSICA, '-i', work / 'sfx.wav']
    else:
        grafo = ('[0:a]aformat=channel_layouts=stereo[voz];[1:a]aformat=channel_layouts=stereo[fx];'
                 '[voz][fx]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.95[out]')
        ent = ['-i', narr, '-i', work / 'sfx.wav']
    run(['ffmpeg', '-y', '-v', 'error', *ent, '-filter_complex', grafo, '-map', '[out]',
         '-ar', SR, '-t', f'{dur:.3f}', mix])
    final = work / 'mix.wav'
    run([sys.executable, '-m', 'ffmpeg_normalize', mix, '-nt', 'ebu', '-t', '-14', '-tp', '-1.5',
         '-ar', str(SR), '-c:a', 'pcm_s16le', '-f', '-o', final])
    return final


# ------------------------------------------------------------ cenas novas ---
def _nuvem_tempestade(tam=250):
    return (f'<svg viewBox="-150 -120 300 260" width="{tam}" height="{tam * 260 / 300:.0f}">'
            '<g fill="#5c6474" stroke="#10202e" stroke-width="9" stroke-linejoin="round">'
            '<path d="M-120 20 A48 48 0 0 1 -70 -46 A64 64 0 0 1 56 -56 A50 50 0 0 1 116 6 A32 32 0 0 1 96 54 L-96 54 A32 32 0 0 1 -120 20 Z"/></g>'
            '<path d="M8 50 L-28 112 L4 112 L-18 170 L52 92 L18 92 L40 50 Z" fill="#FFD166" stroke="#10202e" stroke-width="7" stroke-linejoin="round"/>'
            '<g fill="#e7f2fb" stroke="#10202e" stroke-width="5"><circle cx="-78" cy="96" r="13"/><circle cx="84" cy="104" r="11"/><circle cx="-44" cy="146" r="10"/></g></svg>')


def cena_abertura_comunicado(p, cena, bat):
    m = p['meta']
    titulo = m['titulo']
    palavras = ''.join(f'<span class="ab-w">{esc(w)}</span> ' for w in titulo.split())
    tags = ''.join(f'<span class="tag {cls}">{esc(t)}</span>'
                   for t, cls in zip(m['etiquetas'], ('tag-red', 'tag-yel')))
    mascote = _nuvem_tempestade(250) if m['tipo'] == 'alerta' else C.nuvem_rj_svg(240)
    miolo = f'''{C.paisagem(p["ceu"], "ab")}
 <div class="ab-kicker">{tags}</div>
 <div class="ab-placa"></div>
 <div class="ab-titulo" data-layout-allow-overlap="true" style="font-size: {C.tamanho_titulo(titulo)}px">{palavras}</div>
 <div class="ab-mascote">{mascote}</div>'''
    fundo = C.CEUS.get(p['ceu'], C.CEUS['sol'])[0]
    return C._scene(cena, p, fundo, miolo)


def cena_cartaz(p, cena, bat):
    """Cartaz de evento/lembrete: selo, nome, quando, onde e um detalhe."""
    d = bat[cena['batidas'][0]]['dados']
    nome = d.get('nome', '')
    linhas = ''.join(f'<div class="ct-linha"><span class="ct-rot">{esc(rot)}</span>'
                     f'<span class="ct-val">{esc(d[chave])}</span></div>'
                     for chave, rot in (('quando', 'QUANDO'), ('onde', 'ONDE'), ('detalhe', 'DETALHE'))
                     if d.get(chave))
    selo = f'<div class="ct-selo" data-layout-allow-overlap="true"><span>{esc(d["selo"])}</span></div>' if d.get('selo') else ''
    tam = 112 if len(nome) <= 16 else 96 if len(nome) <= 24 else 80
    miolo = f'''{C.paisagem(p["ceu"], "ct" + cena["id"], com_sol=False)}
 <div class="qd-veu"></div>
 <div class="ct-card">
  <div class="ct-topo">{esc(d.get("rotulo", "AGENDA"))}</div>
  <div class="ct-nome" style="font-size:{tam}px">{esc(nome)}</div>
  {linhas}
 </div>
 {selo}'''
    return C._scene(cena, p, C.INK, miolo)


ICONE_VENTO = ('<svg viewBox="-150 -150 300 300" width="250" height="250" fill="none" stroke-linecap="round">'
               '<g stroke="#10202e" stroke-width="30"><path d="M-120 -50 H40 A40 40 0 1 0 0 -90"/>'
               '<path d="M-120 10 H80 A40 40 0 1 1 40 50"/><path d="M-120 70 H-10"/></g>'
               '<g stroke="#dfeef8" stroke-width="16"><path d="M-120 -50 H40 A40 40 0 1 0 0 -90"/>'
               '<path d="M-120 10 H80 A40 40 0 1 1 40 50"/><path d="M-120 70 H-10"/></g></svg>')


def cena_numero_comunicado(p, cena, bat, _original=C.cena_numero):
    h = _original(p, cena, bat)
    if bat[cena['batidas'][0]]['dados'].get('icone') == 'vento':
        h = re.sub(r'<div class="nu-icone">.*?</svg></div>', f'<div class="nu-icone">{ICONE_VENTO}</div>', h,
                   count=1, flags=re.S)
    return h


def cena_alerta_comunicado(p, cena, bat, _original=C.cena_alerta):
    """O título do alerta encolhe conforme o tamanho, para não invadir o detalhe."""
    h = _original(p, cena, bat)
    titulo = bat[cena['batidas'][0]]['dados'].get('titulo', 'ATENÇÃO')
    n = max(len(w) for w in titulo.split()) if titulo.split() else 1
    tam = 136 if len(titulo) <= 13 else (112 if len(titulo) <= 18 and n <= 11 else 92)
    return h.replace('<div class="al-titulo">', f'<div class="al-titulo" style="font-size:{tam}px;top:{470 - (0 if tam == 136 else 40)}px">', 1)


CSS_CARTAZ = '''
.ct-card { position: absolute; top: 262px; left: 44px; right: 44px; padding: 30px 36px 34px; background-color: #f4f1e8; border: 7px solid #10202e; border-radius: 30px; box-shadow: 0 16px 0 #10202e; }
.ct-topo { display: inline-block; font-family: "BarlowC", sans-serif; font-size: 46px; letter-spacing: 3px; color: #ffffff; background-color: #d63a2f; border: 5px solid #10202e; border-radius: 12px; padding: 4px 18px 0; }
.ct-nome { margin: 14px 0 12px; font-family: "BarlowC", sans-serif; line-height: 0.98; color: #10202e; }
.ct-linha { display: flex; align-items: baseline; gap: 18px; padding: 14px 0 8px; border-top: 4px dashed #c9c2b0; }
.ct-rot { flex: 0 0 170px; font-family: "BarlowCB", sans-serif; font-size: 40px; letter-spacing: 2px; color: #007F87; }
.ct-val { font-family: "BarlowCB", sans-serif; font-size: 54px; line-height: 1.08; color: #10202e; }
.ct-selo { position: absolute; top: 238px; right: 40px; transform: rotate(8deg); }
.ct-selo span { display: block; font-family: "BarlowC", sans-serif; font-size: 72px; color: #10202e; background-color: #FFD166; border: 7px solid #10202e; border-radius: 16px; padding: 4px 26px 0; box-shadow: 0 10px 0 #10202e; }
'''


# ------------------------------------------------------- HTML da dupla ---
def html_comunicado(p, falante, boca_outro, extras):
    m = p['meta']
    outro = m['outro']
    fab_original = dict(C.FAB)
    lugar_original = C._lugar
    try:
        C.FAB['abertura'] = cena_abertura_comunicado
        C.FAB['cartaz'] = cena_cartaz
        C.FAB['numero'] = cena_numero_comunicado
        C.FAB['alerta'] = cena_alerta_comunicado
        C._lugar = lambda b: b['dados'].get('local') or lugar_original(b)
        h = C.compor(p)
    finally:
        C.FAB.clear()
        C.FAB.update(fab_original)
        C._lugar = lugar_original
    dur = p['dur']
    svg = C.apresentador_svg(outro).replace('ap-', 'bp-')
    h = h.replace(' <div id="bancada"',
                  f' <div id="bp-wrap" class="clip" data-start="0" data-duration="{dur}" data-track-index="12">'
                  f'<div id="bp-mov">{svg}</div></div>\n\n <div id="bancada"', 1)
    ap2 = C.APRESENTADOR[outro]
    h = h.replace(' <div id="legenda"',
                  f' <div id="lt2" class="clip" data-start="0.7" data-duration="4.2" data-track-index="13">'
                  f'<span class="lt-nome" id="lt2-nome">{esc(ap2["nome"])}</span>'
                  f'<span class="lt-cargo" id="lt2-cargo">{esc(ap2["cargo"])}</span></div>\n\n'
                  ' <div id="legenda"', 1)
    # HUD e ticker do comunicado
    h = h.replace('<span class="hud-ponto" id="hud-ponto"></span>PREVISÃO</div>',
                  f'<span class="hud-ponto" id="hud-ponto"></span>{esc(m["selo"])}</div>', 1)
    if m['ticker']:
        itens = ' &#9679; '.join(esc(t) for t in m['ticker']) + ' &#9679; ' + esc(estado.arroba().upper())
        h = re.sub(r'<div id="tk-trilho">.*?</div>', f'<div id="tk-trilho">{itens} &#9679; {itens}</div>', h,
                   count=1, flags=re.S)
    cor_outro = ap2['camisa']
    cor_bia = C.APRESENTADOR['bia']['camisa']
    css = (
        '\n#ap-wrap { left: -30px !important; }\n'
        '#bp-wrap { position: absolute; left: 590px; top: 1010px; width: 520px; height: 700px; z-index: 311; }\n'
        '#lt { left: 22px !important; top: 1392px !important; }\n'
        '#lt2 { position: absolute; right: 22px; top: 1392px; z-index: 330; display: flex; flex-direction: column; align-items: flex-end; }\n'
        '#lt .lt-nome, #lt2 .lt-nome { font-size: 52px; }\n'
        '#lt .lt-cargo, #lt2 .lt-cargo { font-size: 26px; margin-top: 10px; }\n'
        f'#lt2 .lt-nome {{ box-shadow: -10px 10px 0 {cor_outro}; }}\n'
        f'.cta-geo {{ position: absolute; inset: 0; background-image: url("{extras["geo"]}"); background-size: 420px; opacity: 0.30; mix-blend-mode: multiply; }}\n'
        '.cta-peeps { position: absolute; top: 650px; left: 0; right: 0; height: 200px; display: flex; justify-content: center; }\n'
        '.cta-peeps img { display: block; width: 170px; height: 170px; margin: 0 -14px; }\n'
        f'.lg-bia .lg-bg {{ background-color: {cor_bia} !important; }}\n' + CSS_CARTAZ)
    h = h.replace('</style>', css + '</style>', 1)
    imgs = ''.join(f'<img class="peep" src="{u}" alt=""/>' for u in extras['peeps'])
    h = h.replace('<div class="cta-fundo"></div>',
                  f'<div class="cta-fundo"></div><div class="cta-geo"></div><div class="cta-peeps">{imgs}</div>')
    dupla = {'principal': m['apresenta'], 'falante': falante,
             'boca2': [[t, C.MOUTH.get(v, 0.3)] for t, v in boca_outro]}
    trocas = [
        ('    if (dado) {\n      // braço direito',
         '    if (dado && window.__DUPLA.falante[c.batidas[0].i] === window.__DUPLA.principal) {\n      // braço direito'),
        ('  D.batidas.forEach(function (b, k) {\n    tl.fromTo(["#ap-sobE"',
         '  D.batidas.forEach(function (b, k) {\n    if (window.__DUPLA.falante[k] !== window.__DUPLA.principal) return;\n'
         '    tl.fromTo(["#ap-sobE"'),
        ('<script>\n(function () {',
         f'<script>window.__DUPLA = {json.dumps(dupla)};</script>\n<script>\n(function () {{'),
        ('  window.__timelines["main"] = tl;', JS_DUPLA + '\n  window.__timelines["main"] = tl;'),
    ]
    for antes, depois in trocas:
        if antes not in h:
            raise RuntimeError(f'compor.py mudou: ponto de injeção não encontrado ({antes[:40]!r})')
        h = h.replace(antes, depois, 1)
    return h


JS_DUPLA = r'''
  // ===== DUPLA: segundo personagem à direita; quem fala é destaque, o outro olha =====
  var F = window.__DUPLA.falante, P = window.__DUPLA.principal;
  var svgB = document.getElementById("bp-svg"), svgA = document.getElementById("ap-svg");
  var ombroBE = svgB.getAttribute("data-ombro-e");
  tl.fromTo("#bp-wrap", { y: 700 }, { y: 0, duration: 0.5, ease: "back.out(1.4)" }, 0.15);
  var nRespB = Math.max(1, Math.floor(D.dur / 1.7));
  tl.fromTo("#bp-corpo", { scaleY: 1, svgOrigin: "260 640" }, { scaleY: 1.018, duration: 0.85, repeat: nRespB * 2 - 1, yoyo: true, ease: "sine.inOut" }, 0.3);
  tl.fromTo("#bp-cabeca", { y: 0 }, { y: -5, duration: 0.85, repeat: nRespB * 2 - 1, yoyo: true, ease: "sine.inOut" }, 0.3);
  for (var tb = 2.2; tb < D.dur - 0.3; tb += 3.3) {
    tl.set("#bp-palp", { opacity: 1 }, tb);
    tl.set("#bp-palp", { opacity: 0 }, tb + 0.1);
  }
  tl.set("#bp-boca-abre", { scaleY: 0.06, svgOrigin: "0 0" }, 0);
  window.__DUPLA.boca2.forEach(function (c) {
    tl.set("#bp-boca-abre", { scaleY: c[1], scaleX: 0.75 + 0.25 * c[1], svgOrigin: "0 0" }, c[0]);
  });
  tl.fromTo("#lt2-nome", { xPercent: 120, opacity: 0 }, { xPercent: 0, opacity: 1, duration: 0.35, ease: "power3.out" }, 0.7);
  tl.fromTo("#lt2-cargo", { xPercent: 120, opacity: 0 }, { xPercent: 0, opacity: 1, duration: 0.35, ease: "power3.out" }, 0.82);
  tl.to(["#lt2-nome", "#lt2-cargo"], { xPercent: 130, opacity: 0, duration: 0.3, ease: "power2.in", stagger: 0.06 }, 4.4);
  function cenaDe(t) { var r = D.cenas[0]; D.cenas.forEach(function (c) { if (t >= c.ini - 0.01) r = c; }); return r; }
  D.batidas.forEach(function (b, k) {
    var quem = F[k], c = cenaDe(b.ini);
    var dado = (c.tipo === "numero" || c.tipo === "quadro" || c.tipo === "alerta" || c.tipo === "cartaz");
    var fala = quem === P ? "#ap-wrap" : "#bp-wrap", ouve = quem === P ? "#bp-wrap" : "#ap-wrap";
    tl.to(fala, { scale: 1.03, filter: "brightness(1)", transformOrigin: "50% 100%", duration: 0.25, ease: "power2.out" }, b.ini - 0.05);
    tl.to(ouve, { scale: 0.95, filter: "brightness(0.86)", transformOrigin: "50% 100%", duration: 0.25, ease: "power2.out" }, b.ini - 0.05);
    if (quem !== P) {
      tl.to("#ap-pupilas", { x: 12, y: 2, duration: 0.18 }, b.ini + 0.25);
      tl.to("#bp-pupilas", { x: dado ? -8 : -4, y: dado ? -7 : 0, duration: 0.18 }, b.ini + 0.1);
      tl.fromTo(["#bp-sobE", "#bp-sobD"], { y: 0 }, { y: -14, duration: 0.12, yoyo: true, repeat: 1, ease: "power2.out" }, b.ini);
      tl.fromTo("#bp-mov", { rotation: 0, svgOrigin: "260 640" }, { rotation: (k % 2 ? -2.5 : 2.5), duration: 0.18, yoyo: true, repeat: 1, ease: "power1.inOut" }, b.ini);
      if (dado) {
        tl.to("#bp-bracoE", { rotation: 128, svgOrigin: ombroBE, duration: 0.3, ease: "back.out(1.6)" }, b.ini + 0.15);
        tl.to("#bp-bracoE", { rotation: 0, svgOrigin: ombroBE, duration: 0.3, ease: "power2.inOut" }, Math.max(b.ini + 0.6, b.fim - 0.15));
      } else {
        tl.fromTo("#bp-bracoD", { rotation: 0, svgOrigin: svgB.getAttribute("data-ombro") }, { rotation: 10, duration: 0.35, yoyo: true, repeat: 1, ease: "sine.inOut", immediateRender: false }, b.ini + 0.05);
      }
    } else {
      tl.to("#bp-pupilas", { x: -12, y: 2, duration: 0.18 }, b.ini + 0.25);
      if (c.tipo === "cartaz") {
        tl.to("#ap-pupilas", { x: 8, y: -7, duration: 0.2 }, b.ini + 0.1);
        tl.to("#ap-bracoD", { rotation: -128, svgOrigin: svgA.getAttribute("data-ombro"), duration: 0.3, ease: "back.out(1.6)" }, b.ini + 0.15);
        tl.to("#ap-bracoD", { rotation: 0, svgOrigin: svgA.getAttribute("data-ombro"), duration: 0.3, ease: "power2.inOut" }, Math.max(b.ini + 0.6, b.fim - 0.15));
      }
    }
  });
  tl.to(["#ap-wrap", "#bp-wrap"], { scale: 1, filter: "brightness(1)", duration: 0.3 }, D.dur - 0.6);
  document.querySelectorAll(".lg-w").forEach(function (w) {
    var s = parseFloat(w.getAttribute("data-s"));
    for (var k = D.batidas.length - 1; k >= 0; k--) {
      if (s >= D.batidas[k].ini - 0.01) { if (F[k] === "bia") w.classList.add("lg-bia"); break; }
    }
  });
  D.cenas.forEach(function (c) {
    // CARTAZ: o cartão sobe, as linhas entram uma a uma e o selo bate
    if (c.tipo === "cartaz") {
      var id = c.id;
      tl.fromTo("#" + id + " .ct-card", { y: 260, rotation: -4, opacity: 0 }, { y: 0, rotation: 0, opacity: 1, duration: 0.45, ease: "back.out(1.6)" }, c.ini + 0.05);
      tl.fromTo("#" + id + " .ct-nome", { scale: 1.6, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.3, ease: "power4.in" }, c.ini + 0.25);
      tl.fromTo(document.querySelectorAll("#" + id + " .ct-linha"), { x: -60, opacity: 0 }, { x: 0, opacity: 1, duration: 0.28, stagger: 0.12, ease: "power2.out" }, c.ini + 0.55);
      var selo = document.querySelector("#" + id + " .ct-selo span");
      if (selo) tl.fromTo(selo, { scale: 3, rotation: -18, opacity: 0 }, { scale: 1, rotation: 0, opacity: 1, duration: 0.28, ease: "power4.in" }, c.ini + 0.67);
    }
    // CTA: figurantes Open Peeps entram, balançam e saem antes do card "Seguir"
    if (c.tipo !== "cta") return;
    var ps = document.querySelectorAll("#" + c.id + " .peep");
    if (!ps.length) return;
    tl.fromTo(ps, { y: 140, opacity: 0, scale: 0.5 }, { y: 0, opacity: 1, scale: 1, duration: 0.35, stagger: 0.09, ease: "back.out(2.2)" }, c.ini + 0.5);
    var tSai = Math.max(c.ini + 1.4, D.tSiga - 0.15);
    ps.forEach(function (p, k) {
      tl.fromTo(p, { y: 0 }, { y: -12, duration: 0.42, repeat: Math.max(1, Math.floor((tSai - c.ini - 1.2) / 0.42)), yoyo: true, ease: "sine.inOut", immediateRender: false }, c.ini + 1.2 + k * 0.06);
    });
    tl.to(ps, { opacity: 0, y: 60, scale: 0.7, duration: 0.25, stagger: 0.03, ease: "power2.in" }, tSai);
  });
'''


# ------------------------------------------------------------- render ---
def preparar(roteiro, out, ignorar_validade=False):
    meta, bat, falante = carregar_roteiro(roteiro, ignorar_validade=ignorar_validade)
    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    work = out.parent / 'work_comunicado'
    work.mkdir(parents=True, exist_ok=True)
    if HF.BUILD.exists():
        shutil.rmtree(HF.BUILD)
    HF.BUILD.mkdir(parents=True)
    HF.AUDIO.mkdir(parents=True, exist_ok=True)
    vendor = AQUI / 'assets' / 'vendor'
    vendor.mkdir(parents=True, exist_ok=True)
    shutil.copy(RAIZ / 'video/node_modules/gsap/dist/gsap.min.js', vendor)

    segs, pistas, raw = narrar(bat, falante, work)
    tempos = [(s['ini'], max(s['ini'] + 0.2, s['fim_fala'])) for s in segs]
    dur = round(segs[-1]['fim'] + HF.CAUDA, 2)
    narr = work / 'narracao.wav'
    run(['ffmpeg', '-y', '-v', 'error', '-i', raw, '-af', HF.FILTRO_VOZ, '-ar', SR, '-ac', 1, narr])
    x, _ = HF.ler_wav(narr)
    HF.gravar_wav(narr, np.concatenate([x, np.zeros(max(0, int(dur * SR) - len(x)), np.float32)])[:int(dur * SR)], SR)
    cues = {}
    for quem, p in pistas.items():
        p = np.concatenate([p, np.zeros(max(0, int(dur * SR) - len(p)), np.float32)])[:int(dur * SR)]
        cues[quem] = gerar_cues(p / (np.abs(p).max() or 1), SR, fps=30)

    cenas = agrupar(bat)
    for c in cenas:
        c['ini'] = tempos[c['batidas'][0]][0]
    cortes = [round(max(0.05, c['ini'] - HF.TRANS_DUR * 0.55), 3) for c in cenas[1:]]
    trans = [{'alerta': 'glitch', 'cta': 'flash-through-white'}.get(c['tipo'], 'whip-pan') for c in cenas[1:]]
    palavras = []
    for i, b in enumerate(bat):
        for w in HF.tempos_das_palavras(b['legenda'], *tempos[i]):
            w['b'] = i
            palavras.append(w)
    agora = dt.datetime.now(FUSO)
    hoje = agora.date().isoformat()
    lider = meta['apresenta']
    p = {
        'meta': meta, 'meta_tipo': meta['tipo'], 'dicas_praticas': [], 'direcao': [],
        'dur': dur, 'personagem': lider, 'formato': 'comunicado', 'demo': False,
        'data': hoje, 'data_ext': HF.data_extenso(hoje), 'data_previsao': hoje,
        'hora': f'{agora:%H:%M}', 'ceu': meta['ceu'], 'cidades': [],
        'batidas': [dict(b, ini=tempos[i][0], fim=tempos[i][1]) for i, b in enumerate(bat)],
        'cenas': cenas, 'cortes': cortes, 'transicoes': trans, 'palavras': palavras,
        'capa_s': round(min(cenas[1]['ini'] + 1.2, dur / 2) if len(cenas) > 1 else 1.5, 2),
        'boca': [[c['start'], c['value']] for c in cues[lider]],
    }
    ult = cenas[-1]
    p['tSiga'] = round(max(0.5, min(ult['ini'] + 0.9, dur - 2.2)), 2)
    sx = planejar_sfx(p, len(meta['titulo'].split()))
    mix = mixar(work, narr, sx.bus, dur, meta['trilha'])
    shutil.copy(mix, HF.AUDIO / 'narracao.wav')        # faixa única: voz + trilha + SFX
    for nome in ('trilha.wav', 'whoosh.wav'):
        HF.gravar_wav(HF.AUDIO / nome, np.zeros(int(dur * SR), np.float32), SR, estereo=True)
    extras = json.loads((DUPLA / 'figurantes.json').read_text(encoding='utf-8'))
    (AQUI / 'index.html').write_text(
        html_comunicado(p, falante, [[c['start'], c['value']] for c in cues[meta['outro']]], extras),
        encoding='utf-8')
    (work / 'sfx_usados.json').write_text(json.dumps(sx.usados, indent=1))
    legenda = meta['legenda'] + (f'\n\nFonte: {meta["fonte"]}' if meta['fonte'] else '')
    out.with_name('LEGENDA.txt').write_text(legenda + '\n', encoding='utf-8')
    print(f'index.html do comunicado ({meta["tipo"]}) — {dur:.1f}s | {lider} apresenta | '
          f'cenas: {" > ".join(c["tipo"] for c in cenas)} | {len(sx.usados)} efeitos sonoros')
    return p


def renderizar(out, p, qualidade='standard'):
    out = Path(out).resolve()
    HF.renderizar(out, p, qualidade)
    capa = out.with_name('CAPA.jpg')
    run(['ffmpeg', '-y', '-v', 'error', '-ss', f'{p["capa_s"]:.2f}', '-i', out, '-frames:v', '1', '-q:v', '2', capa])
    out.with_name('capa_ms.txt').write_text(str(int(p['capa_s'] * 1000)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('roteiro', help='arquivo YAML do comunicado (veja comunicados/README.md)')
    ap.add_argument('--out', default='output/REEL.mp4')
    ap.add_argument('--qualidade', default='standard', choices=['draft', 'standard', 'high'])
    ap.add_argument('--ignorar-validade', action='store_true', help='só para teste: nunca publicar')
    ap.add_argument('--so-validar', action='store_true', help='só confere o roteiro')
    a = ap.parse_args()
    if a.so_validar:
        meta, bat, falante = carregar_roteiro(a.roteiro, ignorar_validade=a.ignorar_validade)
        for b, q in zip(bat, falante):
            print(f'[{q:4s}] {b["cena"]:8s} {b["fala"]}')
        print('roteiro ok')
        return
    p = preparar(a.roteiro, a.out, a.ignorar_validade)
    renderizar(a.out, p, a.qualidade)
    print(f'ok: {a.out}')


if __name__ == '__main__':
    main()
