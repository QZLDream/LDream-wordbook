import json
import urllib.error
import urllib.request

import pytest

from shici.core import Core
from shici.server import Server


@pytest.fixture
def srv(tmp_path):
    core = Core(tmp_path)
    s = Server(core)
    s.start()
    yield s
    s.stop()
    core.close()


def post(s, name, body=None, token=None, host=None):
    req = urllib.request.Request(f"http://127.0.0.1:{s.port}/api/{name}", data=json.dumps(body or {}).encode(),
                                 headers={"X-Shici-Token": s.token if token is None else token, "Content-Type": "application/json"})
    if host:
        req.add_header("Host", host)
    return json.loads(urllib.request.urlopen(req).read())


def test_api_roundtrip_and_token(srv):
    assert post(srv, "bootstrap")["data"]["app"] == "小梦的词书"
    assert post(srv, "add_word", {"term": ""}) == {"ok": False, "error": "请输入单词"}
    with pytest.raises(urllib.error.HTTPError) as e:
        post(srv, "bootstrap", token="wrong")
    assert e.value.code == 403
    with pytest.raises(urllib.error.HTTPError) as e:
        post(srv, "bootstrap", host="evil.example")
    assert e.value.code == 403


def test_static_files_and_traversal(srv):
    html = urllib.request.urlopen(f"http://127.0.0.1:{srv.port}/").read().decode()
    assert "<html" in html.lower()
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(f"http://127.0.0.1:{srv.port}/../core.py")
    assert e.value.code == 404
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(f"http://127.0.0.1:{srv.port}/%2e%2e/core.py")
    assert e.value.code == 404


def test_user_font_served(srv):
    from test_core import _tiny_font
    import base64
    r = post(srv, "font_import", {"filename": "t.ttf", "data": base64.b64encode(_tiny_font()).decode()})["data"]["font"]
    res = urllib.request.urlopen(f"http://127.0.0.1:{srv.port}/userfonts/{r['file']}")
    assert res.headers["Content-Type"] == "font/ttf" and len(res.read()) > 200
    for bad in ("../user.db", "%2e%2e%2fuser.db", "fonts.json", "abc.ttf"):
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(f"http://127.0.0.1:{srv.port}/userfonts/{bad}")
