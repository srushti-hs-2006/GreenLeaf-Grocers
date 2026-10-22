import pytest
import database
import app as application
from flask import Flask, url_for


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_database = tmp_path / "test_greenleaf.db"

    monkeypatch.setattr(database, "DATABASE", str(test_database))
    database.init_db()

    flask_app = next(
        (
            value
            for value in vars(application).values()
            if isinstance(value, Flask)
        ),
        None
    )

    if flask_app is None:
        pytest.fail("No Flask application found in app.py")

    flask_app.config.update(TESTING=True)

    with flask_app.test_client() as test_client:
        yield test_client


def test_login_page_opens(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Sign in to your account" in response.data


def test_admin_login(client):
    response = client.post(
        "/",
        data={"username": "admin", "password": "Admin@123"},
        follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Dashboard" in response.data


def test_cashier_login(client):
    response = client.post(
        "/",
        data={"username": "cashier", "password": "Cashier@123"},
        follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Dashboard" in response.data


def test_invalid_login(client):
    response = client.post(
        "/",
        data={"username": "wrong_user", "password": "wrong_password"},
        follow_redirects=True
    )
    assert response.status_code == 200
    assert b"Invalid username or password" in response.data


def test_dashboard_requires_login(client):
    response = client.get("/dashboard")
    assert response.status_code == 302


def test_dashboard_opens_after_login(client):
    client.post(
        "/",
        data={"username": "admin", "password": "Admin@123"}
    )
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"Analytics Dashboard" in response.data


def test_sales_report_download(client):
    client.post(
        "/",
        data={"username": "admin", "password": "Admin@123"}
    )

    flask_app = next(
        value
        for value in vars(application).values()
        if isinstance(value, Flask)
    )

    with flask_app.test_request_context():
        report_url = url_for("export_report")

    response = client.get(report_url)
    assert response.status_code == 200
    assert "text/csv" in response.content_type


def test_logout(client):
    client.post(
        "/",
        data={"username": "admin", "password": "Admin@123"}
    )
    response = client.get("/logout")
    assert response.status_code == 302
