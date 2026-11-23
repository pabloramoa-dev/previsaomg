"""Guard de isolamento: um canal nunca carrega a identidade de outro.

Nenhum @, nome de repositorio, id de conta ou caminho de OUTRO canal pode
aparecer no codigo, na configuracao ou nos workflows deste repositorio. A lista
de proibidos fica em config/isolamento.yaml e e escrita pelo gerador de estado
(todos os canais da rede, menos este).

`tests/` fica de fora de proposito: a bateria roda sobre o estado de referencia
(tests/ref_config), que e outro canal por definicao.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

ROOTS = [Path("src"), Path(".github"), Path("config"), Path("scripts"), Path("hyperframes"),
         Path("video"), Path("tools")]
# O gerador da rede (so no modelo) lista todos os canais por definicao.
ISENTOS = {Path("config/isolamento.yaml"), Path("scripts/novo_estado.py")}
SKIP_SUFFIXES = {".pyc", ".mp4", ".wav", ".png", ".jpg", ".woff2", ".ttf", ".js", ".csv", ".lock"}
SKIP_PARTS = {"__pycache__", "node_modules", "rede", "build"}


def proibidos() -> list[str]:
    caminho = RAIZ / "config" / "isolamento.yaml"
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    return [str(t).casefold() for t in dados.get("proibidos") or []]


def _padrao(token: str) -> re.Pattern[str]:
    # Limite de palavra: um repo "previsao-xx" nao pode acusar "previsao-xxyz".
    return re.compile(r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9_-])")


def scan(raiz: Path = RAIZ) -> list[tuple[str, str]]:
    padroes = [(t, _padrao(t)) for t in proibidos()]
    violations: list[tuple[str, str]] = []
    for root in ROOTS:
        base = raiz / root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            rel = path.relative_to(raiz)
            if not path.is_file() or rel in ISENTOS:
                continue
            if path.suffix in SKIP_SUFFIXES or SKIP_PARTS & set(rel.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8").casefold()
            except (UnicodeDecodeError, OSError):
                continue
            for token, padrao in padroes:
                if padrao.search(text):
                    violations.append((str(rel), token))
    return violations


def main() -> None:
    violations = scan()
    if violations:
        lines = "\n".join(f"  {path}: {token!r}" for path, token in violations)
        raise SystemExit(f"isolamento falhou:\n{lines}")
    print(f"isolation_guard: ok ({len(proibidos())} identificadores proibidos, {len(ROOTS)} raizes)")


if __name__ == "__main__":
    main()
