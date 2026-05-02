from __future__ import annotations

import io
import json
import re
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass

from src.db.models import ProductFormat

MAX_PAYLOAD_BYTES = 5 * 1024 * 1024  # 5 МБ на 1 аккаунт — с большим запасом


@dataclass
class ParsedItem:
    payload: str
    file_name: str | None = None


class ParseError(Exception):
    pass


# ────────────────────────── ZIP режим ──────────────────────────
def parse_zip_archive(zip_bytes: bytes, fmt: ProductFormat) -> list[ParsedItem]:
    """Каждый файл в ZIP = 1 аккаунт.
    Содержимое сохраняется как есть (включая многострочный JSON)."""
    items: list[ParsedItem] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as e:
        raise ParseError(f"Невалидный ZIP-архив: {e}") from e

    for info in zf.infolist():
        if info.is_dir():
            continue
        name = info.filename
        if name.startswith("__MACOSX/") or name.endswith("/.DS_Store") or name.endswith("/Thumbs.db"):
            continue
        base = name.rsplit("/", 1)[-1]
        if not base or base.startswith("."):
            continue
        if info.file_size > MAX_PAYLOAD_BYTES:
            raise ParseError(f"Файл «{name}» слишком большой ({info.file_size} байт)")
        with zf.open(info) as fp:
            raw = fp.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ParseError(f"Файл «{name}» не в UTF-8: {e}") from e

        text = text.strip()
        if not text:
            continue

        if fmt == ProductFormat.cookies_json:
            # валидируем как JSON, но сохраняем оригинальный отформатированный текст
            try:
                json.loads(text)
            except json.JSONDecodeError as e:
                raise ParseError(f"Файл «{name}»: невалидный JSON ({e})") from e

        items.append(ParsedItem(payload=text, file_name=base))

    if not items:
        raise ParseError("В архиве не найдено ни одного валидного аккаунта")
    return items


# ────────────────────────── Line-based режим ──────────────────────────
LOGIN_PASS_RE = re.compile(r"^[^\s:]+:[^\s:]+(?::[^\s:]+)?$")


def parse_line_based(text: str, fmt: ProductFormat) -> list[ParsedItem]:
    """Каждая непустая строка = 1 аккаунт.
    Для login_pass проверяем формат `login:pass[:что-то]`."""
    items: list[ParsedItem] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if fmt == ProductFormat.login_pass and not LOGIN_PASS_RE.match(line):
            raise ParseError(f"Строка не соответствует формату login:pass — «{line[:60]}»")
        items.append(ParsedItem(payload=line))
    if not items:
        raise ParseError("Не найдено ни одной строки с аккаунтом")
    return items


# ─────────────────────────── Single-file режим (media group) ───────────────────────────
def parse_single_file(filename: str, content: bytes, fmt: ProductFormat) -> ParsedItem:
    if len(content) > MAX_PAYLOAD_BYTES:
        raise ParseError(f"Файл «{filename}» слишком большой ({len(content)} байт)")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ParseError(f"Файл «{filename}» не в UTF-8: {e}") from e

    text = text.strip()
    if not text:
        raise ParseError(f"Файл «{filename}» пустой")

    if fmt == ProductFormat.cookies_json:
        try:
            json.loads(text)
        except json.JSONDecodeError as e:
            raise ParseError(f"Файл «{filename}»: невалидный JSON ({e})") from e

    return ParsedItem(payload=text, file_name=filename)


# ─────────────────────────── ZIP-сборка для пачки на выдачу ───────────────────────────
def build_zip_archive(items: Iterable[tuple[str, str]]) -> bytes:
    """`items` — пары (имя_файла, payload). Возвращает байты zip-архива."""
    buf = io.BytesIO()
    seen: dict[str, int] = {}
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for filename, payload in items:
            name = filename
            if name in seen:
                seen[name] += 1
                base, _, ext = name.rpartition(".")
                if base:
                    name = f"{base}_{seen[name]}.{ext}"
                else:
                    name = f"{name}_{seen[name]}"
            else:
                seen[name] = 0
            zf.writestr(name, payload)
    return buf.getvalue()
