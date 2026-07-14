from __future__ import annotations

LIST_KEY_DEFAULT = "u0"
_LIST_KEY_PREFIXES = frozenset("uacgbdr")
_BACK_ROUTES = {
    "a": "adm:admins",
    "u": "adm:users",
    "c": "adm:channels",
    "g": "adm:groups",
    "b": "adm:bots",
    "d": "adm:del",
    "r": "adm:reports",
}


def encode_list_key(src: str, page: int) -> str:
    return f"{src}{page}"


def parse_list_key(key: str) -> tuple[str, int]:
    return key[0], int(key[1:])


def back_list_data(key: str) -> bytes:
    if key.startswith("bs") and len(key) > 2 and key[2:].isdigit():
        return bots_list_callback(int(key[2:]), show_system=True)
    if key.startswith("us") and len(key) > 2 and key[2:].isdigit():
        return users_list_callback(int(key[2:]), show_system=True)
    src, page = parse_list_key(key)
    route = _BACK_ROUTES.get(src, "adm:users")
    return f"{route}:{page}".encode()


def encode_user_list_key(page: int, *, show_system: bool = False) -> str:
    return f"us{page}" if show_system else f"u{page}"


def parse_user_list_key(key: str) -> tuple[int, bool]:
    if key.startswith("us") and len(key) > 2 and key[2:].isdigit():
        return int(key[2:]), True
    if key.startswith("u") and len(key) > 1 and key[1:].isdigit():
        return int(key[1:]), False
    return 0, False


def users_list_callback(page: int, *, show_system: bool = False) -> bytes:
    if show_system:
        return f"adm:users:sys:{page}".encode()
    return f"adm:users:{page}".encode()


def encode_bot_list_key(page: int, *, show_system: bool = False) -> str:
    return f"bs{page}" if show_system else f"b{page}"


def parse_bot_list_key(key: str) -> tuple[int, bool]:
    if key.startswith("bs") and len(key) > 2 and key[2:].isdigit():
        return int(key[2:]), True
    if key.startswith("b") and len(key) > 1 and key[1:].isdigit():
        return int(key[1:]), False
    return 0, False


def bots_list_callback(page: int, *, show_system: bool = False) -> bytes:
    if show_system:
        return f"adm:bots:sys:{page}".encode()
    return f"adm:bots:{page}".encode()


def split_list_key(data: bytes) -> tuple[bytes, str]:
    text = data.decode()
    parts = text.split(":")
    if len(parts) >= 2:
        last = parts[-1]
        if last.startswith("bs") and len(last) > 2 and last[2:].isdigit():
            body = ":".join(parts[:-1]).encode()
            return body, last
        if last.startswith("us") and len(last) > 2 and last[2:].isdigit():
            body = ":".join(parts[:-1]).encode()
            return body, last
        if len(last) >= 2 and last[0] in _LIST_KEY_PREFIXES and last[1:].isdigit():
            body = ":".join(parts[:-1]).encode()
            return body, last
    return data, LIST_KEY_DEFAULT


def user_link(user_id: int, list_key: str) -> bytes:
    return f"adm:user:{user_id}:{list_key}".encode()


def user_open_link(user_id: int, list_key: str) -> bytes:
    return f"adm:user:open:{user_id}:{list_key}".encode()


def bot_open_link(bot_id: int, list_key: str) -> bytes:
    return f"adm:bot:open:{bot_id}:{list_key}".encode()


def user_action(action: str, user_id: int, list_key: str) -> bytes:
    return f"adm:act:{action}:{user_id}:{list_key}".encode()


def stars_action(action: str, user_id: int, amount: int, list_key: str) -> bytes:
    return f"adm:act:stars:{action}:{user_id}:{amount}:{list_key}".encode()


def encode_stars_wait_data(user_id: int, list_key: str) -> bytes:
    return f"{user_id}:{list_key}".encode()


def decode_stars_wait_data(data: bytes | None) -> tuple[int, str]:
    if not data:
        return 0, LIST_KEY_DEFAULT
    text = data.decode()
    user_id_str, list_key = text.split(":", 1)
    return int(user_id_str), list_key