"""Static theme regression checks; no browser dependency required for CI."""
from fastapi.testclient import TestClient
from refillops.api import app


def test_theme_assets_are_served_as_css_and_js():
    client = TestClient(app)
    page = client.get('/')
    assert page.status_code == 200
    assert '/static/styles.css?v=0.1.5' in page.text
    assert '/static/app.js?v=0.1.5' in page.text
    stylesheet = client.get('/static/styles.css?v=0.1.5')
    assert stylesheet.status_code == 200
    assert 'text/css' in stylesheet.headers['content-type']
    assert 'html[data-theme="light"]' in stylesheet.text
    assert 'html[data-theme="system"]' in stylesheet.text
    script = client.get('/static/app.js?v=0.1.5')
    assert script.status_code == 200
    assert 'text/javascript' in script.headers['content-type']


def test_theme_selector_is_available_without_sign_in():
    page = TestClient(app).get('/').text
    assert 'id="theme-select"' in page
    for option in ('dark', 'light', 'system'):
        assert f'<option value="{option}">' in page
    assert 'refillops-theme' in page


def test_light_theme_uses_system_preference_and_dialog_tokens():
    css = TestClient(app).get('/static/styles.css').text
    assert '@media (prefers-color-scheme: light)' in css
    assert '--surface:' in css and '--input-bg:' in css
    assert '.action-modal-backdrop' in css
    assert '.badge.unpaid' in css
