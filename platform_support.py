"""Helpers for SteamOS handheld detection and support gating."""

STEAMOS_MIN_VERSION = (3, 8)
OFFICIAL_STEAMOS_BRAND = "steamos"
OFFICIAL_STEAMOS_CODENAME = "holo"
OFFICIAL_STEAMOS_URL_TOKEN = "steampowered.com"
ASUS_VENDOR_NAMES = {"ASUS", "ASUSTEK", "ASUSTEK COMPUTER INC."}
LENOVO_VENDOR_NAMES = {"LENOVO"}
GENERIC_HANDHELD_VENDOR_NAMES = {
    "AOKZOE",
    "AYA",
    "AYADEVICE",
    "AYANEO",
    "GPD",
    "MSI",
    "ONEXPLAYER",
    "ONE-NETBOOK",
    "ZOTAC",
    "ACER",
}
STEAM_DECK_VENDOR_NAMES = {"VALVE"}
HANDHELD_IDENTIFIER_KEYWORDS = (
    "ALLY",
    "AYA",
    "AYANEO",
    "CLAW",
    "GAMEPAD",
    "GAMING HANDHELD",
    "GPD",
    "HANDHELD",
    "LEGION",
    "ONEX",
    "PLAYER",
    "PORTABLE",
    "ROG",
    "WIN",
    "XBOX",
    "Z1",
)


def _normalized_os_release_value(values: dict, key: str) -> str:
    return str(values.get(key, "")).strip().lower()


def get_steamos_version(os_release_values: dict | None = None) -> str:
    values = os_release_values or {}
    return (
        values.get("PRETTY_NAME")
        or values.get("VERSION")
        or values.get("NAME")
        or "Unknown"
    )


def is_steam_deck_device(
    board_name: str,
    product_name: str,
    sys_vendor: str,
    product_family: str,
) -> bool:
    normalized_vendor = sys_vendor.strip().upper()
    identifiers = " ".join(
        value.strip().upper()
        for value in (board_name, product_name, product_family)
        if value and value != "Unknown"
    )
    return normalized_vendor in STEAM_DECK_VENDOR_NAMES or any(
        keyword in identifiers
        for keyword in ("STEAM DECK", "JUPITER", "GALILEO")
    )


def is_supported_handheld_vendor_device(
    board_name: str,
    product_name: str,
    sys_vendor: str,
    product_family: str,
) -> bool:
    normalized_vendor = sys_vendor.strip().upper()
    identifiers = " ".join(
        value.strip().upper()
        for value in (board_name, product_name, product_family)
        if value and value != "Unknown"
    )

    if normalized_vendor in ASUS_VENDOR_NAMES:
        return any(keyword in identifiers for keyword in ("ALLY", "ROG", "XBOX", "RC7"))

    if normalized_vendor in LENOVO_VENDOR_NAMES:
        return "LEGION" in identifiers

    if normalized_vendor in GENERIC_HANDHELD_VENDOR_NAMES:
        return any(keyword in identifiers for keyword in HANDHELD_IDENTIFIER_KEYWORDS)

    return any(keyword in identifiers for keyword in HANDHELD_IDENTIFIER_KEYWORDS)


def parse_version_tuple(raw_version: str) -> tuple[int, int] | None:
    parts = []
    current = ""
    for char in raw_version:
        if char.isdigit():
            current += char
        elif current:
            parts.append(int(current))
            current = ""
            if len(parts) == 2:
                break
    if current and len(parts) < 2:
        parts.append(int(current))
    if not parts:
        return None
    if len(parts) == 1:
        parts.append(0)
    return parts[0], parts[1]


def steamos_version_is_supported(values: dict) -> bool:
    for key in ("VERSION_ID", "VERSION", "PRETTY_NAME"):
        parsed = parse_version_tuple(values.get(key, ""))
        if parsed is not None:
            return parsed >= STEAMOS_MIN_VERSION
    return False


def is_official_steamos_build(values: dict) -> bool:
    if _normalized_os_release_value(values, "ID") != OFFICIAL_STEAMOS_BRAND:
        return False

    name_markers = (
        _normalized_os_release_value(values, "NAME"),
        _normalized_os_release_value(values, "PRETTY_NAME"),
    )
    has_brand_marker = any(OFFICIAL_STEAMOS_BRAND in marker for marker in name_markers)
    has_logo_marker = _normalized_os_release_value(values, "LOGO") == OFFICIAL_STEAMOS_BRAND
    has_codename_marker = _normalized_os_release_value(values, "VERSION_CODENAME") == OFFICIAL_STEAMOS_CODENAME
    has_valve_url_marker = any(
        OFFICIAL_STEAMOS_URL_TOKEN in _normalized_os_release_value(values, key)
        for key in ("HOME_URL", "DOCUMENTATION_URL", "SUPPORT_URL", "BUG_REPORT_URL")
    )

    official_markers = (
        has_brand_marker,
        has_logo_marker,
        has_codename_marker,
        has_valve_url_marker,
    )
    return sum(1 for marker in official_markers if marker) >= 3


def get_platform_support(
    board_name: str,
    product_name: str,
    sys_vendor: str,
    product_family: str,
    os_release_values: dict | None = None,
) -> dict:
    values = os_release_values or {}

    if is_steam_deck_device(board_name, product_name, sys_vendor, product_family):
        return {
            "supported": False,
            "support_level": "blocked",
            "reason": "Steam Deck is blocked to avoid interfering with Valve hardware defaults.",
        }

    if not is_official_steamos_build(values):
        return {
            "supported": False,
            "support_level": "blocked",
            "reason": "AnyDeck is only enabled on official SteamOS builds.",
        }

    if not steamos_version_is_supported(values):
        return {
            "supported": False,
            "support_level": "blocked",
            "reason": "AnyDeck requires SteamOS 3.8 or newer.",
        }

    if not is_supported_handheld_vendor_device(
        board_name,
        product_name,
        sys_vendor,
        product_family,
    ):
        return {
            "supported": False,
            "support_level": "blocked",
            "reason": "AnyDeck is only enabled on non-Steam-Deck handhelds it can identify.",
        }

    normalized_vendor = sys_vendor.strip().upper()
    support_level = (
        "supported"
        if normalized_vendor in ASUS_VENDOR_NAMES | LENOVO_VENDOR_NAMES
        else "experimental"
    )
    return {
        "supported": True,
        "support_level": support_level,
        "reason": (
            "Validated SteamOS handheld on SteamOS 3.8 or newer."
            if support_level == "supported"
            else "Experimental SteamOS handheld support on SteamOS 3.8 or newer."
        ),
    }


def get_device_metadata(
    board_name: str,
    product_name: str,
    sys_vendor: str = "",
    product_family: str = "",
) -> dict:
    vendor = (
        sys_vendor
        if sys_vendor and sys_vendor != "Unknown"
        else "Unknown"
    )
    friendly_name = product_name if product_name and product_name != "Unknown" else "SteamOS handheld"

    return {
        "board_name": board_name,
        "product_name": product_name,
        "product_family": product_family or "Unknown",
        "sys_vendor": vendor,
        "variant": board_name or product_name or "Unknown",
        "friendly_name": friendly_name,
        "device_family": "steamos_handheld",
        "support_level": "supported",
    }
