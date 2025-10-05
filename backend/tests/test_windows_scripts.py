from pathlib import Path


def test_windows_scripts_exist_and_reference_docker_and_npm():
    """Ensure Windows helper scripts exist and reference docker-compose or npm where appropriate.

    This test is platform-agnostic and only checks the presence and basic content of the
    scripts so Windows users without `make` can rely on the provided PowerShell/.bat helpers.
    """
    repo_root = Path(__file__).resolve().parents[2]

    expected_files = [
        "scripts/windows/up.ps1",
        "scripts/windows/down.ps1",
        "scripts/windows/build.ps1",
        "scripts/windows/test.ps1",
        "scripts/windows/setup-dev.ps1",
        "scripts/windows/readme-windows-commands.ps1",
        "scripts/windows/up.bat",
        "scripts/windows/down.bat",
        "scripts/windows/build.bat",
        "scripts/windows/test.bat",
    ]

    for rel in expected_files:
        path = repo_root / rel
        assert path.exists(), f"Expected file {rel} to exist"
        content = path.read_text(encoding="utf-8").lower()
        # Basic smoke checks: at least one of the scripts should mention docker-compose
        # and at least one should mention npm (frontend build/test) so Windows users can use them
        # We don't assert each file contains both to keep the test flexible.
        assert len(content) > 0, f"{rel} appears empty"

    # Additional heuristics: some scripts should mention docker-compose and npm
    all_contents = "\n".join((repo_root / f).read_text(encoding="utf-8").lower() for f in expected_files)
    assert "docker-compose" in all_contents or "docker compose" in all_contents, "No script references docker-compose"
    assert "npm" in all_contents, "No script references npm (frontend build)"

    # Ensure .env.example exists at repo root for easy bootstrap
    env_example = repo_root / ".env.example"
    assert env_example.exists(), ".env.example is missing from the repository root"
