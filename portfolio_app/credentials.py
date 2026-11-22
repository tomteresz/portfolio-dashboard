"""Set the local admin password with python -m portfolio_app.credentials."""
from getpass import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile

AUTH_PATH = Path(__file__).resolve().parent.parent / "data" / "auth.json"


def password_hash(password, salt):
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32).hex()


def _create_credentials(password):
    salt = secrets.token_bytes(16)
    config = {"username": "admin", "salt": salt.hex(), "password_hash": password_hash(password, salt)}
    AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=AUTH_PATH.parent,
                                     delete_on_close=False) as temp:
        json.dump(config, temp)
        temp.write("\n")
        temp.close()
        # Publish the complete file only if another setup hasn't created it first.
        os.link(temp.name, AUTH_PATH)


def main():
    if AUTH_PATH.is_file():
        print("The admin account is already configured.")
        return 0
    print("Set a password for admin on this installation.")
    try:
        while True:
            password = getpass("New password: ")
            if not 1 <= len(password.encode("utf-8")) <= 512:
                print("Enter a non-empty password of up to 512 UTF-8 bytes.")
            elif password == getpass("Confirm password: "):
                break
            else:
                print("The passwords differ. Try again.")
        _create_credentials(password)
    except FileExistsError:
        if AUTH_PATH.is_file():
            print("The admin account is already configured.")
            return 0
        print("Could not create data/auth.json. Check the data directory.", file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\nPassword setup cancelled.", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Could not create data/auth.json: {exc}", file=sys.stderr)
        return 1
    print("Password saved. Sign in as admin.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
