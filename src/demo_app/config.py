import os
from dataclasses import dataclass

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass(frozen=True)
class Settings:
    host: str = "0.0.0.0"
    port: int = 3000
    fail_after_s: float | None = None
    demo_password: str | None = None

    @property
    def host_is_loopback(self) -> bool:
        return self.host in LOOPBACK_HOSTS


def parse_fail_after(raw: str | None) -> float | None:
    """Unset, empty or 0 means the timer is off."""
    if raw is None or raw.strip() == "":
        return None
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"FAIL_AFTER_S must be a number of seconds, got {raw!r}") from None
    if value < 0:
        raise ValueError(f"FAIL_AFTER_S must not be negative, got {raw!r}")
    return value or None


def load_settings(env: dict[str, str] | None = None) -> Settings:
    env = dict(os.environ) if env is None else env
    return Settings(
        host=env.get("HOST", "").strip() or "0.0.0.0",
        port=int(env.get("PORT", "").strip() or 3000),
        fail_after_s=parse_fail_after(env.get("FAIL_AFTER_S")),
        demo_password=env.get("DEMO_PASSWORD") or None,
    )
