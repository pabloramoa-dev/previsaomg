"""Isolamento: um canal nunca carrega a identidade de outro."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path("scripts").resolve()))
import isolation_guard  # noqa: E402


def test_nenhum_identificador_de_outro_canal_no_projeto():
    assert isolation_guard.scan() == []


def test_o_guard_cobre_codigo_config_workflows_scripts_e_estudio():
    roots = {str(r) for r in isolation_guard.ROOTS}
    assert {"src", ".github", "config", "scripts", "hyperframes"} <= roots


def test_o_guard_acusa_e_respeita_limite_de_palavra(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "isolamento.yaml").write_text("proibidos: [previsao-se, previsaoes]\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 'previsao-semanal previsões'\n")
    (tmp_path / "src" / "b.py").write_text("repo = 'pabloramoa-dev/previsao-se'\n")
    monkeypatch.setattr(isolation_guard, "RAIZ", tmp_path)
    assert isolation_guard.scan(tmp_path) == [("src/b.py", "previsao-se")]


def test_nenhum_import_em_runtime_do_projeto_anterior():
    for path in Path("src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "import previsao_lib" not in text
        assert "from previsao_lib" not in text
