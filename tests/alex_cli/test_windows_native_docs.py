from pathlib import Path


def test_windows_native_install_path_docs_match_installer() -> None:
    doc = Path("website/docs/user-guide/windows-native.md").read_text()
    install = Path("scripts/install.ps1").read_text()

    assert "%LOCALAPPDATA%\\alex\\alex-agent\\venv\\Scripts" in doc
    assert "Get-Command alex        # should print C:\\Users\\<you>\\AppData\\Local\\alex\\alex-agent\\venv\\Scripts\\alex.exe" in doc
    assert '$alexBin = "$InstallDir\\venv\\Scripts"' in install
