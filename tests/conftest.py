"""Fixtures compartilhadas: constroem um snapshot completo SEM tocar na rede."""
from __future__ import annotations

import json
import os
from pathlib import Path

# A bateria valida o MOTOR, e por isso roda sobre o estado de referencia
# (tests/ref_config): os mesmos testes passam no modelo e no repositorio de
# qualquer estado. A configuracao real do canal e validada a parte, por
# scripts/validar_estado.py (ver tests/test_estado.py). Tem de vir ANTES de
# importar `src.previsao`, que le a pasta de configuracao ao carregar.
os.environ['PREVISAO_CONFIG_DIR'] = str(Path(__file__).resolve().parent / 'ref_config')
os.environ.pop('FUSO_UTC', None)

import pytest

from src.previsao import config
from src.previsao.collectors.base import SourceResult
from src.previsao.normalizers import snapshot as snap

FIXTURES = Path("tests/fixtures")


@pytest.fixture(scope="session")
def raw_open_meteo() -> dict:
    return json.loads((FIXTURES / "open_meteo_raw.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def tier1_locations() -> list[dict]:
    return config.locations_by_tier(1)


@pytest.fixture
def collected(raw_open_meteo) -> dict[str, SourceResult]:
    """Mesma forma que open_meteo.fetch_all_models devolve, sem HTTP."""
    out = {}
    for model, points in raw_open_meteo["models"].items():
        first = next(iter(points.values()))
        times = first["daily"]["time"]
        out[model] = SourceResult(
            name=f"open_meteo_forecast:{model}",
            status="ok",
            payload={"model": model, "points": points},
            model_run=f"{model}@serie_inicia_{first['hourly']['time'][0]}",
            valid_for=f"{times[0]}..{times[-1]}",
        )
    return out


@pytest.fixture
def snapshot(collected, tier1_locations) -> dict:
    return snap.build(collected, tier1_locations)
