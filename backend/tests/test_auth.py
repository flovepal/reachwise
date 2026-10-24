from urllib.parse import parse_qs, urlparse

from app.config import settings
from app.routers import auth


def test_google_sign_in_returns_to_website(client, monkeypatch):
    monkeypatch.setattr(settings, "google_web_client_id", "web.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "allowed_return_origins", "https://profmail.netlify.app")

    # Not allowed: an unknown website
    assert client.get("/auth/google/url", params={"redirect_uri": "https://evil.example/"}).status_code == 400

    r = client.get("/auth/google/url", params={"redirect_uri": "https://profmail.netlify.app/"})
    q = parse_qs(urlparse(r.json()["url"]).query)
    assert q["redirect_uri"] == ["https://profmail.netlify.app/"] and q["scope"] == ["openid email profile"]

    sent = {}

    class Resp:
        status_code = 200

        def json(self):
            return {"id_token": "google-id-token"}

    def fake_post(url, data, timeout):
        sent.update(data)
        return Resp()

    monkeypatch.setattr(auth.httpx, "post", fake_post)
    monkeypatch.setattr(auth, "verify_google_id_token",
                        lambda t: {"sub": "123", "email": "Student.JohnPaul@gmail.com", "name": "John Paul S"})
    r = client.post("/auth/google/exchange", json={"code": "abc", "state": q["state"][0]})
    assert r.status_code == 200, r.text
    assert sent["redirect_uri"] == "https://profmail.netlify.app/" and sent["code"] == "abc"
    token = r.json()["token"]
    me = client.get("/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["email"] == "student.johnpaul@gmail.com" and me["name"] == "John Paul S"

    # A made-up state is refused
    assert client.post("/auth/google/exchange", json={"code": "abc", "state": "nonsense"}).status_code == 401


def test_ngrok_header_allowed_by_cors(client):
    r = client.options("/me", headers={"Origin": "https://profmail.netlify.app", "Access-Control-Request-Method": "GET",
                                       "Access-Control-Request-Headers": "authorization,ngrok-skip-browser-warning"})
    assert r.status_code == 200
    assert "ngrok-skip-browser-warning" in r.headers["access-control-allow-headers"].lower()
