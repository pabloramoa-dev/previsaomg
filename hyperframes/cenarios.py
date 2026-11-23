# -*- coding: utf-8 -*-
"""
cenarios.py — o chão do telão, um desenho por cenário.

`compor.paisagem` desenha o céu (gradiente, sol, nuvens, chuva) e chama
`desenhar(nome, ...)` para o resto: morros, cartão-postal, água, prédios e o
primeiro plano. O nome vem de `cenario` em config/estado.yaml.

Regras para um cenário novo:
  - recebe as mesmas cores do céu do dia (`morro`, `mar`) para mudar com o tempo;
  - determinístico: toda variação sai do `rng` recebido (semente fixa);
  - a faixa de y entre 1310 e 1920 é o primeiro plano, atrás da bancada;
  - classes `{uid}-mar` e `{uid}-bonde` são animadas pelo compositor se existirem.

`litoral` e `interior` são genéricos e servem a qualquer estado até o desenho
próprio dele ficar pronto.
"""


def _predios(rng, pt, base=1290, cores=("#e9e2d3", "#d9d3c4", "#f2ede2", "#cfd6d8"),
             alt=(90, 230)):
    predios = []
    x = -10
    while x < 1090:
        w, h = rng.randint(60, 110), rng.randint(*alt)
        cor = rng.choice(list(cores))
        jan = "".join(f'<rect x="{x + 12 + j * 22}" y="{base - h + 16 + k * 30}" width="12" height="16" fill="#8fa9b8"/>'
                      for k in range(max(1, h // 30 - 1)) for j in range(max(1, (w - 16) // 22)))
        predios.append(f'<rect x="{x}" y="{base - h}" width="{w}" height="{h + 30}" fill="{cor}" stroke="{pt}" stroke-width="4"/>{jan}')
        x += w + rng.randint(-4, 6)
    return "".join(predios)


_ONDAS_MAR = ("M-60 1205 q30 -12 60 0" + " t60 0" * 19)


def rio(*, morro, mar, uid, rng, pt, red):
    """Corcovado, Pão de Açúcar com o bondinho, orla, mar e o calçadão de ondas."""
    predios = _predios(rng, pt)
    onda = "M0 1395 " + " ".join(f"Q{45 + 90 * k} {1375 if k % 2 == 0 else 1415} {90 + 90 * k} 1395" for k in range(13))
    return f'''<path d="M-20 1180 L60 1080 C110 1010 150 930 200 900 L226 892 C260 920 300 1010 360 1080 L470 1180 Z" fill="{morro}" stroke="{pt}" stroke-width="5"/>
 <g transform="translate(213,846)" fill="{pt}"><rect x="-6" y="0" width="12" height="48"/><rect x="-30" y="10" width="60" height="9"/></g>
 <path d="M640 1180 C660 1110 700 1080 760 1075 C800 1078 820 1110 832 1150 L850 1180 Z" fill="{morro}" stroke="{pt}" stroke-width="5"/>
 <path d="M840 1180 C850 1050 880 930 950 905 C1010 900 1040 990 1060 1180 Z" fill="{morro}" stroke="{pt}" stroke-width="5"/>
 <path d="M770 1078 L948 908" stroke="{pt}" stroke-width="3"/>
 <g class="{uid}-bonde"><rect x="842" y="985" width="30" height="20" rx="4" fill="{red}" stroke="{pt}" stroke-width="3"/></g>
 <rect x="0" y="1170" width="1080" height="140" fill="{mar}"/>
 <path class="{uid}-mar" d="{_ONDAS_MAR}" fill="none" stroke="#e8f6fb" stroke-width="5" opacity="0.8"/>
 {predios}
 <rect x="0" y="1310" width="1080" height="610" fill="#f7f3ea"/>
 <path d="{onda}" fill="none" stroke="{pt}" stroke-width="22"/>
 <path d="{onda.replace("1395", "1475").replace("1375", "1455").replace("1415", "1495")}" fill="none" stroke="{pt}" stroke-width="22"/>'''


def litoral(*, morro, mar, uid, rng, pt, red):
    """Genérico de capital litorânea: colinas ao fundo, mar, orla e areia."""
    predios = _predios(rng, pt)
    return f'''<path d="M-20 1180 C120 1040 260 1010 420 1090 C520 1130 600 1160 700 1180 Z" fill="{morro}" stroke="{pt}" stroke-width="5"/>
 <path d="M620 1180 C760 1060 900 1040 1100 1120 L1100 1180 Z" fill="{morro}" stroke="{pt}" stroke-width="5"/>
 <rect x="0" y="1170" width="1080" height="140" fill="{mar}"/>
 <path class="{uid}-mar" d="{_ONDAS_MAR}" fill="none" stroke="#e8f6fb" stroke-width="5" opacity="0.8"/>
 {predios}
 <rect x="0" y="1310" width="1080" height="610" fill="#f3e6c4"/>
 <path d="M0 1330 q90 -22 180 0 t180 0 t180 0 t180 0 t180 0 t180 0" fill="none" stroke="{pt}" stroke-width="6" opacity="0.35"/>'''


def interior(*, morro, mar, uid, rng, pt, red):
    """Genérico de capital do interior: serra ao fundo, cidade e praça."""
    predios = _predios(rng, pt, alt=(110, 260))
    arvores = "".join(
        f'<g transform="translate({x},1300)"><rect x="-7" y="-46" width="14" height="50" fill="#6b4a32" stroke="{pt}" stroke-width="4"/>'
        f'<circle cx="0" cy="-72" r="38" fill="{morro}" stroke="{pt}" stroke-width="5"/></g>'
        for x in (70, 300, 560, 800, 1010))
    return f'''<path d="M-20 1200 L120 1030 L260 1120 L420 960 L600 1110 L760 1000 L940 1130 L1100 1040 L1100 1200 Z" fill="{morro}" stroke="{pt}" stroke-width="5"/>
 {predios}
 <rect x="0" y="1310" width="1080" height="610" fill="#dfe8c9"/>
 {arvores}
 <path d="M0 1400 H1080" stroke="{pt}" stroke-width="6" opacity="0.25"/>'''


def parana(*, morro, mar, uid, rng, pt, red):
    """Estufa do Jardim Botânico de Curitiba entre araucárias."""
    def araucaria(x, esc=1.0):
        copa = "".join(
            f'<path d="M{-w} {y} Q0 {y - 34} {w} {y} Q0 {y - 10} {-w} {y} Z" fill="{morro}" stroke="{pt}" stroke-width="5"/>'
            for w, y in ((70, -250), (52, -212), (36, -178)))
        return (f'<g transform="translate({x},1300) scale({esc})">'
                f'<rect x="-9" y="-250" width="18" height="254" fill="#6b4a32" stroke="{pt}" stroke-width="4"/>{copa}</g>')
    arcos = "".join(
        f'<path d="M{cx - r} 1290 A{r} {r * 1.15:.0f} 0 0 1 {cx + r} 1290 Z" fill="#dff1f4" stroke="{pt}" stroke-width="6"/>'
        f'<path d="M{cx} {1290 - r * 1.15:.0f} V1290 M{cx - r * .5:.0f} {1290 - r:.0f} V1290 M{cx + r * .5:.0f} {1290 - r:.0f} V1290" stroke="{pt}" stroke-width="3" fill="none"/>'
        for cx, r in ((400, 86), (680, 86), (540, 150)))
    canteiros = "".join(
        f'<ellipse cx="{x}" cy="{y}" rx="120" ry="26" fill="{cor}" stroke="{pt}" stroke-width="5"/>'
        for x, y, cor in ((250, 1400, "#e86a5c"), (540, 1440, "#ffd34e"), (830, 1400, "#e86a5c")))
    return f'''<path d="M-20 1220 C160 1080 320 1060 520 1130 C700 1190 860 1080 1100 1140 L1100 1220 Z" fill="{morro}" stroke="{pt}" stroke-width="5"/>
 {araucaria(110, 1.05)}{araucaria(960, 1.0)}{araucaria(840, .72)}
 {arcos}
 <rect x="0" y="1290" width="1080" height="630" fill="#cfe3b4"/>
 <path d="M512 1300 H568 L660 1920 H420 Z" fill="#f2ede2" stroke="{pt}" stroke-width="5"/>
 {canteiros}'''


CENARIOS = {'rio': rio, 'litoral': litoral, 'interior': interior, 'parana': parana}


def desenhar(nome, **cores):
    if nome not in CENARIOS:
        raise KeyError(f'cenario desconhecido: {nome!r} (existem: {", ".join(sorted(CENARIOS))})')
    return CENARIOS[nome](**cores)
