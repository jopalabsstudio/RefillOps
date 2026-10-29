import json
import pytest
from fastapi.testclient import TestClient
from refillops.api import app
from refillops.cli import seed


@pytest.fixture
def demo(tmp_path, monkeypatch):
    path = tmp_path / 'demo.sqlite3'
    monkeypatch.setenv('REFILLOPS_DB', str(path))
    seed(reset=True)
    access = json.loads((tmp_path / 'demo_access.json').read_text())['actors']
    client = TestClient(app)

    def headers(role):
        return {'Authorization': 'Bearer '+access[role]['api_key']}

    yield client, headers, path
    client.close()
