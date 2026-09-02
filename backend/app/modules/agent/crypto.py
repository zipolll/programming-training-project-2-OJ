"""API credential encryption with an environment-owned Fernet key."""

from cryptography.fernet import Fernet, InvalidToken


class CredentialUnavailableError(RuntimeError):
    pass


class CredentialCipher:
    def __init__(self, key: str | None) -> None:
        self._fernet: Fernet | None = None
        if key:
            try:
                self._fernet = Fernet(key.encode("ascii"))
            except (ValueError, TypeError):
                self._fernet = None

    @property
    def configured(self) -> bool:
        return self._fernet is not None

    def encrypt(self, value: str) -> str:
        if self._fernet is None:
            raise CredentialUnavailableError("credential encryption is not configured")
        return self._fernet.encrypt(value.encode()).decode("ascii")

    def decrypt(self, value: str) -> str:
        if self._fernet is None:
            raise CredentialUnavailableError("credential encryption is not configured")
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode()
        except InvalidToken as exc:
            raise CredentialUnavailableError("stored credential cannot be decrypted") from exc


def mask_key(has_key: bool) -> str:
    return "********" if has_key else ""
