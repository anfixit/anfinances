"""Юнит-тесты AuthService на фейковом репозитории (без БД/сети)."""

import uuid

import pytest

from app.config import Settings
from app.core.exceptions import AlreadyExistsError, UnauthorizedError
from app.core.pwned import PwnedError
from app.domains.auth.models import RefreshToken, User
from app.domains.auth.service import AuthService, _hash_token

STRONG = "fluffy-zebra-canyon-marble-97"


class FakeRepo:
    def __init__(self) -> None:
        self.users: dict[uuid.UUID, User] = {}
        self.by_email: dict[str, User] = {}
        self.tokens: dict[str, RefreshToken] = {}

    async def get_user_by_email(self, email: str) -> User | None:
        return self.by_email.get(email)

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.users.get(user_id)

    async def add_user(self, user: User) -> User:
        if user.id is None:
            user.id = uuid.uuid4()
        if user.is_active is None:
            user.is_active = True
        self.users[user.id] = user
        self.by_email[user.email] = user
        return user

    async def add_refresh_token(self, token: RefreshToken) -> RefreshToken:
        self.tokens[token.token_hash] = token
        return token

    async def get_refresh_token(self, token_hash: str) -> RefreshToken | None:
        return self.tokens.get(token_hash)


class FakePwnedOk:
    async def assert_not_pwned(self, plain: str) -> None:
        return None


class FakePwnedHit:
    async def assert_not_pwned(self, plain: str) -> None:
        raise PwnedError("в утечке")


@pytest.fixture
def settings() -> Settings:
    return Settings(secret_key="x" * 64)  # type: ignore[call-arg]


def _service(
    settings: Settings, repo: FakeRepo, pwned: object = None
) -> AuthService:
    return AuthService(repo, settings, pwned or FakePwnedOk())


async def test_register_ok(settings: Settings) -> None:
    repo = FakeRepo()
    user, tokens = await _service(settings, repo).register(
        "a@b.com", STRONG, "Аня"
    )
    assert user.email == "a@b.com"
    assert tokens.access_token and tokens.refresh_token
    assert len(repo.tokens) == 1


async def test_register_duplicate_email(settings: Settings) -> None:
    repo = FakeRepo()
    svc = _service(settings, repo)
    await svc.register("a@b.com", STRONG)
    with pytest.raises(AlreadyExistsError):
        await svc.register("a@b.com", STRONG)


async def test_register_weak_password(settings: Settings) -> None:
    repo = FakeRepo()
    from app.core.password_policy import PasswordPolicyError

    with pytest.raises(PasswordPolicyError):
        await _service(settings, repo).register("a@b.com", "short")


async def test_register_pwned_password(settings: Settings) -> None:
    repo = FakeRepo()
    svc = _service(settings, repo, FakePwnedHit())
    with pytest.raises(AlreadyExistsError):
        await svc.register("a@b.com", STRONG)


async def test_login_ok(settings: Settings) -> None:
    repo = FakeRepo()
    svc = _service(settings, repo)
    await svc.register("a@b.com", STRONG)
    user, tokens = await svc.login("a@b.com", STRONG)
    assert user.email == "a@b.com"
    assert tokens.access_token


async def test_login_wrong_password(settings: Settings) -> None:
    repo = FakeRepo()
    svc = _service(settings, repo)
    await svc.register("a@b.com", STRONG)
    with pytest.raises(UnauthorizedError):
        await svc.login("a@b.com", "wrong-password-xyz")


async def test_login_unknown_email(settings: Settings) -> None:
    repo = FakeRepo()
    with pytest.raises(UnauthorizedError):
        await _service(settings, repo).login("no@b.com", STRONG)


async def test_refresh_rotation(settings: Settings) -> None:
    repo = FakeRepo()
    svc = _service(settings, repo)
    _, tokens = await svc.register("a@b.com", STRONG)

    new_pair = await svc.refresh(tokens.refresh_token)
    assert new_pair.refresh_token != tokens.refresh_token

    old = repo.tokens[_hash_token(tokens.refresh_token)]
    assert old.revoked_at is not None


async def test_refresh_revoked_rejected(settings: Settings) -> None:
    repo = FakeRepo()
    svc = _service(settings, repo)
    _, tokens = await svc.register("a@b.com", STRONG)
    await svc.refresh(tokens.refresh_token)
    with pytest.raises(UnauthorizedError):
        await svc.refresh(tokens.refresh_token)


async def test_logout_revokes(settings: Settings) -> None:
    repo = FakeRepo()
    svc = _service(settings, repo)
    _, tokens = await svc.register("a@b.com", STRONG)
    await svc.logout(tokens.refresh_token)
    with pytest.raises(UnauthorizedError):
        await svc.refresh(tokens.refresh_token)
