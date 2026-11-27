"""Юнит-тесты AuthService на фейковом репозитории (без БД/сети)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings
from app.core.exceptions import (
    AlreadyExistsError,
    UnauthorizedError,
    ValidationFailedError,
)
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

    async def get_refresh_token(
        self, token_hash: str, *, for_update: bool = False
    ) -> RefreshToken | None:
        return self.tokens.get(token_hash)

    async def revoke_all_for_user(self, user_id: uuid.UUID, now) -> None:
        # Как SqlAuthRepository: отзываем живые и гасим окно второй
        # вкладки у уже ротированных.
        for token in self.tokens.values():
            if token.user_id == user_id:
                if token.revoked_at is None:
                    token.revoked_at = now
                token.rotated_at = None

    async def delete_expired_tokens(self, now) -> None:
        for h in [h for h, t in self.tokens.items() if t.expires_at < now]:
            del self.tokens[h]


class FakePwnedOk:
    async def assert_not_pwned(self, plain: str) -> None:
        return None


class FakePwnedHit:
    async def assert_not_pwned(self, plain: str) -> None:
        raise PwnedError("в утечке")


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        secret_key="x" * 64,
    )  # type: ignore[call-arg]


def _service(
    settings: Settings,
    repo: FakeRepo,
    pwned: object = None,
) -> AuthService:
    return AuthService(
        repo,
        settings,
        pwned or FakePwnedOk(),
    )


async def test_register_ok(settings: Settings) -> None:
    repo = FakeRepo()

    user, tokens = await _service(settings, repo).register(
        "a@b.com",
        STRONG,
        "Аня",
    )

    assert user.email == "a@b.com"
    assert tokens.access_token
    assert tokens.refresh_token
    assert len(repo.tokens) == 1


async def test_register_duplicate_email(
    settings: Settings,
) -> None:
    repo = FakeRepo()
    svc = _service(settings, repo)

    await svc.register("a@b.com", STRONG)

    with pytest.raises(AlreadyExistsError):
        await svc.register("a@b.com", STRONG)


async def test_register_weak_password(
    settings: Settings,
) -> None:
    repo = FakeRepo()

    with pytest.raises(ValidationFailedError):
        await _service(settings, repo).register(
            "a@b.com",
            "short",
        )


async def test_register_pwned_password(
    settings: Settings,
) -> None:
    repo = FakeRepo()
    svc = _service(settings, repo, FakePwnedHit())

    with pytest.raises(ValidationFailedError):
        await svc.register("a@b.com", STRONG)


async def test_login_ok(settings: Settings) -> None:
    repo = FakeRepo()
    svc = _service(settings, repo)

    await svc.register("a@b.com", STRONG)

    user, tokens = await svc.login("a@b.com", STRONG)

    assert user.email == "a@b.com"
    assert tokens.access_token


async def test_login_wrong_password(
    settings: Settings,
) -> None:
    repo = FakeRepo()
    svc = _service(settings, repo)

    await svc.register("a@b.com", STRONG)

    with pytest.raises(UnauthorizedError):
        await svc.login(
            "a@b.com",
            "wrong-password-xyz",
        )


async def test_login_unknown_email(
    settings: Settings,
) -> None:
    repo = FakeRepo()

    with pytest.raises(UnauthorizedError):
        await _service(settings, repo).login(
            "no@b.com",
            STRONG,
        )


async def test_refresh_rotation(
    settings: Settings,
) -> None:
    repo = FakeRepo()
    svc = _service(settings, repo)

    _, tokens = await svc.register("a@b.com", STRONG)

    new_pair = await svc.refresh(tokens.refresh_token)

    assert new_pair.refresh_token != tokens.refresh_token

    old = repo.tokens[_hash_token(tokens.refresh_token)]
    assert old.revoked_at is not None


async def test_refresh_revoked_rejected(
    settings: Settings,
) -> None:
    repo = FakeRepo()
    svc = _service(settings, repo)

    _, tokens = await svc.register("a@b.com", STRONG)

    await svc.refresh(tokens.refresh_token)
    _age_rotation(repo, tokens.refresh_token)

    with pytest.raises(UnauthorizedError):
        await svc.refresh(tokens.refresh_token)


def _age_rotation(repo: FakeRepo, token: str, seconds: int = 60) -> None:
    """Сдвинуть момент ротации в прошлое — за окно второй вкладки."""
    stored = repo.tokens[_hash_token(token)]
    assert stored.rotated_at is not None
    stored.rotated_at -= timedelta(seconds=seconds)


async def test_second_tab_right_after_rotation_is_not_theft(
    settings: Settings,
) -> None:
    """Две вкладки шлют refresh с одной cookie почти одновременно."""
    repo = FakeRepo()
    svc = _service(settings, repo)
    _, first = await svc.register("a@b.com", STRONG)
    _, phone = await svc.login("a@b.com", STRONG)

    tab_a = await svc.refresh(first.refresh_token)
    tab_b = await svc.refresh(first.refresh_token)

    assert tab_b.refresh_token != tab_a.refresh_token
    # Ни одна сессия не отозвана — ни соседняя вкладка, ни телефон.
    assert repo.tokens[_hash_token(tab_a.refresh_token)].revoked_at is None
    assert repo.tokens[_hash_token(phone.refresh_token)].revoked_at is None


async def test_logout_everywhere_closes_the_second_tab_window(
    settings: Settings,
) -> None:
    repo = FakeRepo()
    svc = _service(settings, repo)
    user, first = await svc.register("a@b.com", STRONG)
    await svc.refresh(first.refresh_token)

    await svc.logout_everywhere(user)

    with pytest.raises(UnauthorizedError):
        await svc.refresh(first.refresh_token)
    assert user.sessions_revoked_at is not None


async def test_change_password_needs_the_current_one(
    settings: Settings,
) -> None:
    repo = FakeRepo()
    svc = _service(settings, repo)
    user, _ = await svc.register("a@b.com", STRONG)

    with pytest.raises(ValidationFailedError, match="Текущий"):
        await svc.change_password(user, "wrong" + STRONG, STRONG + "x")


async def test_change_password_signs_out_other_devices(
    settings: Settings,
) -> None:
    repo = FakeRepo()
    svc = _service(settings, repo)
    user, laptop = await svc.register("a@b.com", STRONG)
    new = "другой-длинный-пароль-для-проверки-2026"

    here = await svc.change_password(user, STRONG, new)

    assert repo.tokens[_hash_token(laptop.refresh_token)].revoked_at
    assert repo.tokens[_hash_token(here.refresh_token)].revoked_at is None
    assert user.sessions_revoked_at is not None
    with pytest.raises(UnauthorizedError):
        await svc.login("a@b.com", STRONG)
    await svc.login("a@b.com", new)


async def test_unknown_email_still_checks_a_password(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Время ответа не должно выдавать, есть ли такой email."""
    import app.domains.auth.service as auth_service  # noqa: PLC0415

    checked: list[str] = []
    real = auth_service.verify_password

    def spy(hashed: str, plain: str, s: Settings) -> bool:
        checked.append(hashed)
        return real(hashed, plain, s)

    monkeypatch.setattr(auth_service, "verify_password", spy)
    svc = _service(settings, FakeRepo())

    with pytest.raises(UnauthorizedError):
        await svc.login("nobody@b.com", STRONG)
    assert len(checked) == 1


async def test_logout_revokes(
    settings: Settings,
) -> None:
    repo = FakeRepo()
    svc = _service(settings, repo)

    _, tokens = await svc.register("a@b.com", STRONG)

    await svc.logout(tokens.refresh_token)

    with pytest.raises(UnauthorizedError):
        await svc.refresh(tokens.refresh_token)


async def test_refresh_reuse_revokes_whole_session(
    settings: Settings,
) -> None:
    repo = FakeRepo()
    svc = _service(settings, repo)

    _, first = await svc.register("a@b.com", STRONG)
    _, second = await svc.login("a@b.com", STRONG)

    # Легитимная ротация первого токена.
    rotated = await svc.refresh(first.refresh_token)
    _age_rotation(repo, first.refresh_token)

    # Повторное предъявление давно отозванного first — признак кражи:
    # должно отозвать ВСЕ живые токены юзера (и second, и rotated).
    with pytest.raises(UnauthorizedError):
        await svc.refresh(first.refresh_token)

    assert repo.tokens[_hash_token(second.refresh_token)].revoked_at
    assert repo.tokens[_hash_token(rotated.refresh_token)].revoked_at


async def test_issue_pair_prunes_expired(
    settings: Settings,
) -> None:
    repo = FakeRepo()
    svc = _service(settings, repo)

    expired = RefreshToken(
        user_id=uuid.uuid4(),
        token_hash="dead",
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    repo.tokens["dead"] = expired

    # Любой выпуск пары триггерит чистку протухших.
    await svc.register("a@b.com", STRONG)

    assert "dead" not in repo.tokens
