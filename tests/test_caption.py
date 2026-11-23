import json
from pathlib import Path
from src.previsao.publish.caption import build_caption

def test_caption_brand_and_length():
    s=json.loads(Path('tests/fixtures/snapshot_ref.json').read_text(encoding='utf-8'))
    c=build_caption(s)
    assert '@previsaorj' in c and len(c)<2200
