import pathlib
import pytest


@pytest.fixture
def fixtures_dir():
    return pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def simple_project(fixtures_dir):
    return fixtures_dir / "simple_project"
