from uuid import uuid4
import pytest
import jwt
from app.core.security import Actor, create_access_token, verify_password
from app.config import jwt_secret
from argon2 import PasswordHasher


def test_access_token_is_signed_and_contains_exp(monkeypatch):
    monkeypatch.setenv('JWT_SECRET', 'test-secret-longer-than-thirty-two-characters')
    jwt_secret.cache_clear()
    actor = Actor(id=uuid4(), role='CLIENT', company_id=uuid4())
    token = create_access_token(actor)
    payload = jwt.decode(token, jwt_secret(), algorithms=['HS256'], issuer='alfa-navigator-demo')
    assert payload['sub'] == str(actor.id)
    assert payload['exp'] > payload['iat']
    jwt_secret.cache_clear()


def test_bad_password_rejected():
    hashed = PasswordHasher().hash('correct-test-password')
    assert verify_password('correct-test-password', hashed)
    assert not verify_password('wrong-password', hashed)
