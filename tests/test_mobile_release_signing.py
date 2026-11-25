"""A release APK must not be signed with the shared debug key (audit S-FE-02).

The Flutter template ships `signingConfig = signingConfigs.getByName("debug")` "so
`flutter run --release` works". That key's store password is `android`, it is the same key
on every Flutter machine, and it is what `flutter run --release` silently produced here —
so anyone could sign an update for `dev.soapbot.archive`, and Play rejects the upload.

These are static assertions, not a Gradle run: the Android toolchain is not available in
the backend test job, and the property being pinned (which key signs a release build) is
decided by this file's text.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRADLE = (ROOT / "mobile" / "android" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
README = (ROOT / "mobile" / "README.md").read_text(encoding="utf-8")


def test_release_does_not_fall_back_to_the_debug_key() -> None:
    assert 'signingConfigs.getByName("debug")' not in GRADLE, (
        "release 仍在使用 debug 密钥——那是每台机器共享的公开密钥"
    )
    assert 'signingConfigs.findByName("release")' in GRADLE


def test_a_missing_keystore_fails_a_release_build_but_not_a_debug_build() -> None:
    """The check must be on the task graph, not in configuration.

    Throwing during configuration would break `flutter build apk --debug`, IDE sync and
    `flutter test` on a machine without a keystore — and that is how a guard gets deleted
    instead of read.
    """
    assert "gradle.taskGraph.whenReady" in GRADLE
    assert "GradleException" in GRADLE
    assert "key.properties" in GRADLE
    # Debug builds have no keystore requirement at all.
    assert 'contains("Release"' in GRADLE


def test_the_keystore_is_git_ignored_and_documented() -> None:
    ignored = (ROOT / "mobile" / "android" / ".gitignore").read_text(encoding="utf-8")
    assert "key.properties" in ignored
    assert "**/*.jks" in ignored
    example = ROOT / "mobile" / "android" / "key.properties.example"
    assert example.is_file(), "没有给出 key.properties 的模板"
    text = example.read_text(encoding="utf-8")
    for field in ("storeFile", "storePassword", "keyAlias", "keyPassword"):
        assert field in text
    assert "key.properties" in README and "release" in README
