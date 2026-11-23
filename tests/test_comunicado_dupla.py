"""Comunicado avulso em dupla: roteiro, papéis, validade e recursos."""
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "hyperframes"))

import comunicado_dupla as CD  # noqa: E402

EXEMPLOS = sorted((RAIZ / "comunicados").glob("exemplo_*.yaml"))
ANTES = dt.datetime(2026, 11, 1, 12, 0, tzinfo=CD.FUSO)


@pytest.mark.parametrize("arquivo", EXEMPLOS, ids=lambda p: p.stem)
def test_exemplos_validos(arquivo):
    meta, bat, falante = CD.carregar_roteiro(arquivo, agora=ANTES)
    assert bat[0]["cena"] == "abertura" and bat[-1]["cena"] == "cta"
    assert falante[0] == meta["apresenta"]
    assert falante[-1] == meta["apresenta"]          # o CTA é de quem apresenta
    assert set(falante) == {"bia", "bira"}           # os dois falam
    assert CD.estado.arroba() in meta["legenda"]
    assert "{arroba}" not in meta["legenda"]


def test_alterna_falantes_sem_quem_explicito():
    _, _, falante = CD.carregar_roteiro(RAIZ / "comunicados/exemplo_alerta.yaml", agora=ANTES)
    meio = falante[:-1]
    assert all(a != b for a, b in zip(meio, meio[1:]))


def test_roteiro_vencido_nao_roda(tmp_path):
    exemplo = (RAIZ / "comunicados/exemplo_alerta.yaml").read_text(encoding="utf-8")
    depois = dt.datetime(2030, 1, 1, tzinfo=CD.FUSO)
    f = tmp_path / "r.yaml"
    f.write_text(exemplo, encoding="utf-8")
    with pytest.raises(CD.RoteiroInvalido, match="vencido"):
        CD.carregar_roteiro(f, agora=depois)
    CD.carregar_roteiro(f, agora=depois, ignorar_validade=True)


@pytest.mark.parametrize("troca,erro", [
    (("tipo: alerta", "tipo: festa"), "tipo"),
    (("{arroba}", "@outro_perfil"), "legenda"),
])
def test_roteiro_invalido(tmp_path, troca, erro):
    texto = (RAIZ / "comunicados/exemplo_alerta.yaml").read_text(encoding="utf-8")
    f = tmp_path / "r.yaml"
    f.write_text(texto.replace(*troca), encoding="utf-8")
    with pytest.raises(CD.RoteiroInvalido, match=erro):
        CD.carregar_roteiro(f, agora=ANTES)


def test_continua_junta_frases():
    _, bat, _ = CD.carregar_roteiro(RAIZ / "comunicados/exemplo_alerta.yaml", agora=ANTES)
    cenas = CD.agrupar(bat)
    frases = [c for c in cenas if c["tipo"] == "frase"]
    assert len(frases) == 1 and len(frases[0]["batidas"]) == 2


def test_recursos_gratuitos_versionados():
    sfx = json.loads((CD.DUPLA / "sfx.json").read_text(encoding="utf-8"))
    for som in sfx["sons"].values():
        assert (CD.DUPLA / som["arquivo"]).is_file()
    assert CD.MUSICA.is_file()
    fig = json.loads((CD.DUPLA / "figurantes.json").read_text(encoding="utf-8"))
    assert len(fig["peeps"]) >= 5
