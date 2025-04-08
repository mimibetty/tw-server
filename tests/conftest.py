import pytest
from flask import Flask
from flask.testing import FlaskClient, FlaskCliRunner

from app import AppContext
from app.environments import TestingConfig


@pytest.fixture()
def app():
    app = AppContext().get_app()
    app.config.from_object(TestingConfig)
    yield app


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture()
def runner(app: Flask) -> FlaskCliRunner:
    return app.test_cli_runner()
