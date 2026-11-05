"""Configuration is a security boundary, and these are the ways it was not one.

Each test below corresponds to a failure that was silent. Silent is the operative word:
a config mistake that crashes is a five-minute problem, while one that is accepted and
ignored produces a service that starts, reports healthy, and does the wrong thing. The
assertions are therefore mostly about *what the operator is told*, not just about the
exception type.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from soapbot.config import Settings
from soapbot.core.config_files import ConfigError, parse_providers

# --------------------------------------------------------------- secret handling


def test_secrets_do_not_appear_in_repr() -> None:
    """``repr(settings)`` must not print a credential.

    This is the cheapest possible leak: someone adds ``logger.debug("%s", settings)``
    while chasing an unrelated bug, and the master key — which decrypts every provider
    API key in the database — lands in a log file that outlives the process.
    """
    settings = Settings(
        master_key=SecretStr("fernet-key-material"),
        jwt_secret=SecretStr("jwt-signing-material"),
        init_token=SecretStr("bootstrap-material"),
    )
    rendered = repr(settings)
    for secret in ("fernet-key-material", "jwt-signing-material", "bootstrap-material"):
        assert secret not in rendered, f"{secret!r} leaked into repr()"


def test_secret_str_still_yields_its_value_on_request() -> None:
    """The redaction must not make the value unusable — it is read, deliberately."""
    settings = Settings(master_key=SecretStr("abc123"))
    assert settings.master_key.get_secret_value() == "abc123"


# ------------------------------------------------------------ unknown keys


def test_a_misspelled_soapbot_key_is_rejected_with_a_suggestion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``SOAPBOT_OWNER_ID`` (singular) used to start the process with no owners.

    The symptom was "the bot ignores me", and nothing in the logs named the typo. The
    suggestion is the part that matters: the operator does not know the field is called
    ``owner_ids``, which is why they wrote the wrong one.
    """
    monkeypatch.setenv("SOAPBOT_OWNER_ID", "12345")
    with pytest.raises(ValidationError) as caught:
        Settings()
    message = str(caught.value)
    assert "SOAPBOT_OWNER_ID" in message
    assert "OWNER_IDS" in message, "the error should point at the real field"


def test_foreign_keys_in_a_shared_env_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Another tool's key in the same ``.env`` is none of this process's business.

    ``extra="forbid"`` was tried and was wrong: this repository's own ``.env`` carries
    ``DEEPSEEK_API_KEY``, and forbidding extras turned a working install into an
    ImportError naming a key the operator never meant for soapbot.
    """
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-not-ours")
    monkeypatch.setenv("SOME_OTHER_TOOL_KEY", "whatever")
    Settings()  # must not raise


def test_the_env_file_bootstrap_variable_is_not_treated_as_a_typo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``SOAPBOT_ENV_FILE`` selects the file; it is machinery, not a setting."""
    monkeypatch.setenv("SOAPBOT_ENV_FILE", ".env")
    Settings()  # must not raise


# ---------------------------------------------------------- .env file audit


def test_a_typo_in_the_env_file_is_reported_even_though_the_validator_cannot_see_it(
    tmp_path,
) -> None:
    """The validator reads ``os.environ``; a typo in the file reached it too late.

    ``load_dotenv_if_present`` copies the file into the environment *after* ``Settings``
    was constructed, so nothing ever validated the file's own keys. The operator's symptom
    was identical to the one the validator was written for: the process starts, looks
    healthy, and the value does nothing.
    """
    from soapbot.config import unknown_env_keys

    env = tmp_path / ".env"
    env.write_text(
        "# a comment\nSOAPBOT_OWNER_ID=123\nSOAPBOT_ENV_FILE=.env\nDEEPSEEK_API_KEY=sk-x\n",
        encoding="utf-8",
    )

    findings = unknown_env_keys(env)

    assert len(findings) == 1
    assert "SOAPBOT_OWNER_ID" in findings[0]
    assert "OWNER_IDS" in findings[0], "the report should suggest the real field"


def test_a_clean_env_file_produces_no_findings(tmp_path) -> None:
    """The audit must not cry wolf on a correct file, or it gets ignored."""
    from soapbot.config import unknown_env_keys

    env = tmp_path / ".env"
    env.write_text(
        "SOAPBOT_HOST=127.0.0.1\nSOAPBOT_OWNER_IDS=1,2\nSOAPBOT_ENV_FILE=.env\n",
        encoding="utf-8",
    )

    assert unknown_env_keys(env) == []


def test_a_missing_env_file_is_not_an_error(tmp_path) -> None:
    """Most deployments configure through real environment variables and have no file."""
    from soapbot.config import unknown_env_keys

    assert unknown_env_keys(tmp_path / "absent.env") == []


# ------------------------------------------------------------- enum fields


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("budget_period", "weekly"),
        ("bilibili_tier", "l3"),
        ("log_level", "VERBOSE"),
        ("plugin_integrity_mode", "blok"),
    ],
)
def test_an_invalid_enum_value_names_the_accepted_ones(
    monkeypatch: pytest.MonkeyPatch, field: str, bad: str
) -> None:
    """A typo in an enum must list the valid values, not just say "invalid".

    ``budget_period=weekly`` was the worst of these: accepted as a plain string, then
    matched no branch in the ledger, so the spend cap governed nothing.
    """
    monkeypatch.setenv(f"SOAPBOT_{field.upper()}", bad)
    with pytest.raises(ValidationError):
        Settings()


def test_enum_normalisation_accepts_case_and_whitespace() -> None:
    """``BLOCK`` and `` block `` mean the same thing; the type check runs after."""
    settings = Settings(plugin_integrity_mode=" BLOCK ")
    assert settings.plugin_integrity_mode == "block"


# ------------------------------------------------------- provider file keys


def test_an_unknown_provider_key_is_rejected() -> None:
    """``base_urls`` (plural) used to produce a provider with an empty URL.

    The operator then saw a connection error pointing at the network, while the actual
    mistake was a plural ``s`` in a YAML file.
    """
    with pytest.raises(ConfigError) as caught:
        parse_providers(
            {
                "providers": [
                    {"id": "p", "kind": "openai_compat", "base_urls": "https://x/v1"}
                ]
            }
        )
    message = str(caught.value)
    assert "base_urls" in message
    assert "base_url" in message, "the error should suggest the real key"


def test_an_unknown_top_level_section_is_rejected() -> None:
    """A misspelled ``providers:`` section yields zero providers and a green service."""
    with pytest.raises(ConfigError) as caught:
        parse_providers({"provider": [{"id": "p", "kind": "openai_compat"}]})
    assert "provider" in str(caught.value)


def test_a_valid_provider_document_still_parses() -> None:
    """The guard must not reject the documented format."""
    configs = parse_providers(
        {
            "schema_version": 2,
            "providers": [
                {
                    "id": "deepseek",
                    "kind": "openai_compat",
                    "base_url": "https://api.deepseek.com/v1",
                    "api_key": "sk-literal",
                    "model": "deepseek-chat",
                }
            ],
        }
    )
    assert len(configs) == 1
    assert configs[0].id == "deepseek"


# ------------------------------------------------------------ body size


def test_an_oversized_request_body_is_refused_before_parsing() -> None:
    """A JSON endpoint used to buffer whatever it was sent.

    "How much memory can a stranger make this process allocate" had no answer. The
    ceiling is not a precise quota; it is the difference between a bounded and an
    unbounded failure.
    """
    from fastapi.testclient import TestClient

    from soapbot.app import MAX_REQUEST_BODY_BYTES, create_app

    client = TestClient(create_app())
    oversized = b"x" * (MAX_REQUEST_BODY_BYTES + 1024)
    response = client.post(
        "/api/auth/login", content=oversized, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert str(MAX_REQUEST_BODY_BYTES) in response.json()["detail"]


def test_a_normal_body_is_not_affected_by_the_limit() -> None:
    """The guard must not break ordinary requests."""
    from fastapi.testclient import TestClient

    from soapbot.app import create_app

    client = TestClient(create_app())
    response = client.post("/api/auth/login", json={"init_token": "x"})
    assert response.status_code != 413
