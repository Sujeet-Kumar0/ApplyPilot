"""One-time OAuth setup for Gmail MCP.

Uses Google's installed app (Desktop) flow — opens browser, user consents,
token is saved to ~/.gmail-mcp/credentials.json for the MCP server to use.
"""

import json
import os
from pathlib import Path

GMAIL_MCP_DIR = Path.home() / ".gmail-mcp"
OAUTH_KEYS = GMAIL_MCP_DIR / "gcp-oauth.keys.json"
CREDENTIALS = GMAIL_MCP_DIR / "credentials.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]


def _chmod_if_supported(path: Path, mode: int) -> None:
    if os.name == "posix":
        os.chmod(path, mode)


def _ensure_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _chmod_if_supported(path, 0o700)


def _write_private_json(path: Path, payload: dict) -> None:
    _ensure_private_directory(path.parent)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _chmod_if_supported(path, 0o600)


def main():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Installing google-auth-oauthlib...")
        import subprocess
        import sys

        subprocess.check_call([sys.executable, "-m", "pip", "install",
                               "google-auth-oauthlib"])
        from google_auth_oauthlib.flow import InstalledAppFlow

    if not OAUTH_KEYS.exists():
        print("ERROR: Gmail OAuth client secrets file not found in ~/.gmail-mcp")
        return

    flow = InstalledAppFlow.from_client_secrets_file(str(OAUTH_KEYS), SCOPES)
    creds = flow.run_local_server(port=0)  # picks any free port

    # Save in the format the MCP server expects
    token_data = {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "scope": " ".join(SCOPES),
        "token_type": "Bearer",
        "expiry_date": int(creds.expiry.timestamp() * 1000) if creds.expiry else None,
    }

    _write_private_json(CREDENTIALS, token_data)
    print("\nToken saved to the Gmail MCP credentials store.")
    print("Gmail MCP is now authorized. Run: applypilot track --setup")


if __name__ == "__main__":
    main()
