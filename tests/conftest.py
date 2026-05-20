import pathlib
import pytest


@pytest.fixture
def fixtures_dir():
    return pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def simple_project(fixtures_dir):
    return fixtures_dir / "simple_project"


@pytest.fixture
def jedi_project(fixtures_dir):
    return fixtures_dir / "jedi_project"


@pytest.fixture
def go_project(fixtures_dir):
    return fixtures_dir / "go_project"


@pytest.fixture
def ts_project(fixtures_dir):
    return fixtures_dir / "ts_project"
