from fastapi.testclient import TestClient
from aifootball.service.app import create_app

def test_spa_routes_and_missing_api_assets(service_settings,tmp_path):
    (tmp_path/'index.html').write_text('<html>Cabinet</html>')
    app=create_app(service_settings,web_dist=tmp_path)
    with TestClient(app) as client:
        assert client.get('/matches/example').status_code==200
        assert client.get('/api/v1/missing').status_code==404
        assert client.get('/assets/missing.js').status_code==404
        assert client.get('/private.txt').status_code==404
