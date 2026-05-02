from __future__ import annotations

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def encode_user_id(user_id: int) -> str:
    """Простая base62 кодировка для коротких реф-кодов."""
    if user_id < 0:
        raise ValueError("user_id должен быть >= 0")
    if user_id == 0:
        return "0"
    base = len(ALPHABET)
    chars: list[str] = []
    n = user_id
    while n:
        n, r = divmod(n, base)
        chars.append(ALPHABET[r])
    return "".join(reversed(chars))
