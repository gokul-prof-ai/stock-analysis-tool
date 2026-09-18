from pathlib import Path

import pytest

from src.ingestion.json_parser import JSONParser
from src.ingestion.normalizer import DataNormalizer

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "full_sample.json"


@pytest.fixture
def sample_company():
    extract = JSONParser().load(FIXTURE_PATH)
    return DataNormalizer().normalize(extract)
