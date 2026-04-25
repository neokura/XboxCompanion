"""
Xbox Companion - Decky Loader Plugin Backend
SteamOS handheld control and SteamOS-native system management

Licensed under MIT
"""

import os
import json
import subprocess
import shlex
import glob
import shutil

import decky

# Hardware paths. Vendor-specific paths are optional and features stay hidden
# when the running handheld does not expose them.
BATTERY_PATH = "/sys/class/power_supply/BAT0"
DMI_PATH = "/sys/class/dmi/id"
ALLY_LED_PATH = "/sys/class/leds/ally:rgb:joystick_rings"
SMT_CONTROL_PATH = "/sys/devices/system/cpu/smt/control"

RGB_LED_PATH_GLOBS = [
    "/sys/class/leds/*:rgb:joystick_rings",
    "/sys/class/leds/*ally*rgb*",
    "/sys/class/leds/*legion*rgb*",
    "/sys/class/leds/*joystick*ring*",
]

STEAMOS_MIN_VERSION = (3, 8)
ASUS_VENDOR_NAMES = {"ASUS", "ASUSTEK", "ASUSTEK COMPUTER INC."}
LENOVO_VENDOR_NAMES = {"LENOVO"}
STEAM_DECK_VENDOR_NAMES = {"VALVE"}

PLUGIN_NAME = "Xbox Companion"

STEAMOS_MANAGER_SERVICE = "com.steampowered.SteamOSManager1"
STEAMOS_MANAGER_OBJECT = "/com/steampowered/SteamOSManager1"
STEAMOS_PERFORMANCE_INTERFACE = "com.steampowered.SteamOSManager1.PerformanceProfile1"
STEAMOS_CHARGE_LIMIT_PERCENT = 80
STEAMOS_CHARGE_FULL_PERCENT = 100
STEAMOS_CHARGE_LIMIT_INTERFACES = [
    "com.steampowered.SteamOSManager1",
    "com.steampowered.SteamOSManager1.BatteryChargeLimit1",
    "com.steampowered.SteamOSManager1.Battery1",
    "com.steampowered.SteamOSManager1.PowerManagement1",
    "com.steampowered.SteamOSManager1.Power1",
]
STEAMOS_CHARGE_LIMIT_PROPERTIES = [
    "ChargeLimit",
    "BatteryChargeLimit",
    "ChargeControlEndThreshold",
    "MaxChargeLevel",
    "ChargeLimitPercent",
    "ChargeLimitEnabled",
]
STEAMOS_SMT_INTERFACES = [
    "com.steampowered.SteamOSManager1",
    "com.steampowered.SteamOSManager1.PerformanceProfile1",
    "com.steampowered.SteamOSManager1.PowerManagement1",
    "com.steampowered.SteamOSManager1.Cpu1",
]
STEAMOS_SMT_PROPERTIES = [
    "SMT",
    "Smt",
    "SmtEnabled",
    "SMTEnabled",
    "CpuSmtEnabled",
]

GAMESCOPE_VRR_CAPABLE_ATOM = "GAMESCOPE_VRR_CAPABLE"
GAMESCOPE_VRR_ENABLED_ATOM = "GAMESCOPE_VRR_ENABLED"
GAMESCOPE_VRR_FEEDBACK_ATOM = "GAMESCOPE_VRR_FEEDBACK"
GAMESCOPE_ALLOW_TEARING_ATOM = "GAMESCOPE_ALLOW_TEARING"

NATIVE_PERFORMANCE_PROFILES = {
    "low-power": {
        "name": "Low Power",
        "native_id": "low-power",
        "description": "SteamOS low-power profile for cooler battery-focused play"
    },
    "balanced": {
        "name": "Balanced",
        "native_id": "balanced",
        "description": "SteamOS balanced profile for everyday handheld play"
    },
    "performance": {
        "name": "Performance",
        "native_id": "performance",
        "description": "SteamOS performance profile for demanding games"
    }
}

FPS_NATIVE_PRESET_VALUES = [30, 40, 60]
FPS_HIGH_REFRESH_MIN = 90
FPS_OPTION_DISABLED = 0
RGB_COLOR_PRESETS = ["#FF0000", "#00B7FF", "#00FF85", "#FFFFFF"]

ATOMIC_UPDATE_DIR = "/etc/atomic-update.conf.d"

SCX_DEFAULT_PATH = "/etc/default/scx"
MEMORY_SYSCTL_PATH = "/etc/sysctl.d/99-xbox-companion-memory-tuning.conf"
THP_TMPFILES_PATH = "/etc/tmpfiles.d/xbox-companion-thp.conf"
NPU_BLACKLIST_PATH = "/etc/modprobe.d/blacklist-xbox-companion-npu.conf"
USB_WAKE_SERVICE_PATH = "/etc/systemd/system/xbox-companion-disable-usb-wake.service"
GRUB_HEALER_SCRIPT_PATH = "/etc/xbox-companion-grub-healer.sh"
GRUB_HEALER_SERVICE_PATH = "/etc/systemd/system/xbox-companion-grub-healer.service"
ATOMIC_MANIFEST_PATH = f"{ATOMIC_UPDATE_DIR}/xbox-companion.conf"
LEGACY_ATOMIC_PATHS = [
    f"{ATOMIC_UPDATE_DIR}/xbox-companion-scx.conf",
    f"{ATOMIC_UPDATE_DIR}/xbox-companion-memory.conf",
    f"{ATOMIC_UPDATE_DIR}/xbox-companion-power.conf",
    f"{ATOMIC_UPDATE_DIR}/xbox-companion-grub-healer.conf",
]
GRUB_DEFAULT_PATH = "/etc/default/grub"
CPU_BOOST_PATH = "/sys/devices/system/cpu/cpufreq/boost"
THP_ENABLED_PATH = "/sys/kernel/mm/transparent_hugepage/enabled"

SCX_DEFAULT_CONTENT = '''SCX_SCHEDULER="scx_lavd"
SCX_FLAGS="--performance"
'''

MEMORY_SYSCTL_CONTENT = """vm.swappiness = 10
vm.min_free_kbytes = 524288
vm.dirty_ratio = 5
"""

THP_TMPFILES_CONTENT = (
    "w /sys/kernel/mm/transparent_hugepage/enabled - - - - madvise\n"
)

NPU_BLACKLIST_CONTENT = "blacklist amdxdna\n"

USB_WAKE_SERVICE_CONTENT = """[Unit]
Description=Xbox Companion - Block USB Wake
After=network.target

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'awk "$NF == \\"enabled\\" && ($1 ~ /^XHC/ || $1 ~ /^USB/) { print $1 }" /proc/acpi/wakeup | while read -r device; do echo "$device" > /proc/acpi/wakeup; done'

[Install]
WantedBy=multi-user.target
"""

GRUB_KERNEL_PARAMS = [
    "amd_pstate=active",
    "amdgpu.abmlevel=0",
    "split_lock_mitigate=0",
    "nmi_watchdog=0",
    "pcie_aspm=force",
]

GRUB_HEALER_SCRIPT_CONTENT = """#!/bin/bash
set -e

PARAMS="amd_pstate=active amdgpu.abmlevel=0 split_lock_mitigate=0 nmi_watchdog=0 pcie_aspm=force"
if ! grep -q "amd_pstate=active" /proc/cmdline; then
    sed -i 's/ amd_pstate=active amdgpu.abmlevel=0 split_lock_mitigate=0 nmi_watchdog=0 pcie_aspm=force//g' /etc/default/grub
    sed -i "s/GRUB_CMDLINE_LINUX_DEFAULT=\\"\\(.*\\)\\"/GRUB_CMDLINE_LINUX_DEFAULT=\\"\\1 $PARAMS\\"/" /etc/default/grub
    update-grub
    reboot
fi
"""

GRUB_HEALER_SERVICE_CONTENT = """[Unit]
Description=Xbox Companion - Auto-patch GRUB after SteamOS updates
ConditionFileIsExecutable=/etc/xbox-companion-grub-healer.sh
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/etc/xbox-companion-grub-healer.sh

[Install]
WantedBy=multi-user.target
"""


class SteamOsManagerClient:
    """Small DBus client for SteamOS Manager via busctl."""

    def __init__(self, logger):
        self.logger = logger

    def _run_busctl(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["busctl", "--system", *args],
            capture_output=True,
            text=True,
            timeout=5
        )

    def _get_property(
        self,
        prop: str,
        interface: str = STEAMOS_PERFORMANCE_INTERFACE,
    ) -> tuple[bool, str, str]:
        try:
            result = self._run_busctl([
                "get-property",
                STEAMOS_MANAGER_SERVICE,
                STEAMOS_MANAGER_OBJECT,
                interface,
                prop
            ])
        except FileNotFoundError:
            return False, "", "busctl is not installed"
        except subprocess.TimeoutExpired:
            return False, "", "SteamOS Manager DBus request timed out"
        except Exception as e:
            return False, "", str(e)

        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip() or "DBus property read failed"
            return False, "", error

        return True, result.stdout.strip(), ""

    def _set_property(self, interface: str, prop: str, signature: str, value: str) -> tuple[bool, str]:
        try:
            result = self._run_busctl([
                "set-property",
                STEAMOS_MANAGER_SERVICE,
                STEAMOS_MANAGER_OBJECT,
                interface,
                prop,
                signature,
                value,
            ])
        except FileNotFoundError:
            return False, "busctl is not installed"
        except subprocess.TimeoutExpired:
            return False, "SteamOS Manager DBus request timed out"
        except Exception as e:
            return False, str(e)

        if result.returncode != 0:
            return False, result.stderr.strip() or result.stdout.strip() or "DBus property write failed"

        return True, ""

    def _parse_busctl_bool(self, output: str) -> bool:
        tokens = shlex.split(output)
        return len(tokens) >= 2 and tokens[0] == "b" and tokens[1].lower() in ("true", "1")

    def _parse_busctl_int(self, output: str) -> int:
        tokens = shlex.split(output)
        if len(tokens) >= 2:
            try:
                return int(tokens[1], 0)
            except ValueError:
                return 0
        return 0

    def _busctl_signature(self, output: str) -> str:
        tokens = shlex.split(output)
        return tokens[0] if tokens else ""

    def _parse_busctl_string(self, output: str) -> str:
        tokens = shlex.split(output)
        if len(tokens) >= 2 and tokens[0] == "s":
            return tokens[1]
        return ""

    def _parse_busctl_string_array(self, output: str) -> list[str]:
        tokens = shlex.split(output)
        if not tokens or tokens[0] != "as":
            return []

        if len(tokens) >= 2 and tokens[1].isdigit():
            return tokens[2:]

        return tokens[1:]

    def get_performance_state(self) -> dict:
        available_ok, available_output, available_error = self._get_property(
            "AvailablePerformanceProfiles"
        )
        if not available_ok:
            return {
                "available": False,
                "available_native": [],
                "current": "",
                "suggested_default": "",
                "status": f"SteamOS native profiles unavailable: {available_error}"
            }

        available_native = self._parse_busctl_string_array(available_output)

        current_ok, current_output, current_error = self._get_property("PerformanceProfile")
        current = self._parse_busctl_string(current_output) if current_ok else ""

        suggested_ok, suggested_output, _ = self._get_property(
            "SuggestedDefaultPerformanceProfile"
        )
        suggested_default = (
            self._parse_busctl_string(suggested_output)
            if suggested_ok
            else ""
        )

        if not current_ok:
            self.logger.warning(f"Could not read SteamOS performance profile: {current_error}")

        return {
            "available": True,
            "available_native": available_native,
            "current": current,
            "suggested_default": suggested_default,
            "status": "available"
        }

    def set_performance_profile(self, profile_id: str) -> tuple[bool, str]:
        try:
            return self._set_property(
                STEAMOS_PERFORMANCE_INTERFACE,
                "PerformanceProfile",
                "s",
                profile_id,
            )
        except Exception as e:
            return False, str(e)

    def _get_charge_limit_property(self) -> tuple[bool, str, str, str, str]:
        last_error = "SteamOS Manager charge limit API unavailable"
        for interface in STEAMOS_CHARGE_LIMIT_INTERFACES:
            for prop in STEAMOS_CHARGE_LIMIT_PROPERTIES:
                ok, output, error = self._get_property(prop, interface)
                if ok:
                    signature = self._busctl_signature(output)
                    if signature in ("b", "y", "n", "q", "i", "u", "x", "t"):
                        return True, interface, prop, signature, output
                elif error:
                    last_error = error
        return False, "", "", "", last_error

    def get_charge_limit_state(self) -> dict:
        ok, _interface, _prop, signature, output = self._get_charge_limit_property()
        if not ok:
            return {
                "available": False,
                "enabled": False,
                "limit": STEAMOS_CHARGE_FULL_PERCENT,
                "status": output,
                "details": "SteamOS Manager charge limit control unavailable",
            }

        if signature == "b":
            enabled = self._parse_busctl_bool(output)
            limit = STEAMOS_CHARGE_LIMIT_PERCENT if enabled else STEAMOS_CHARGE_FULL_PERCENT
        else:
            limit = self._parse_busctl_int(output)
            enabled = 0 < limit <= STEAMOS_CHARGE_LIMIT_PERCENT

        return {
            "available": True,
            "enabled": enabled,
            "limit": limit or STEAMOS_CHARGE_FULL_PERCENT,
            "status": "available",
            "details": f"Limits battery charging to {STEAMOS_CHARGE_LIMIT_PERCENT}% through SteamOS Manager",
        }

    def set_charge_limit_enabled(self, enabled: bool) -> tuple[bool, str]:
        ok, interface, prop, signature, _output = self._get_charge_limit_property()
        if not ok:
            return False, "SteamOS Manager charge limit control unavailable"

        if signature == "b":
            return self._set_property(interface, prop, signature, "true" if enabled else "false")

        value = STEAMOS_CHARGE_LIMIT_PERCENT if enabled else STEAMOS_CHARGE_FULL_PERCENT
        return self._set_property(interface, prop, signature, str(value))

    def _get_smt_property(self) -> tuple[bool, str, str, str, str]:
        last_error = "SteamOS Manager SMT control unavailable"
        for interface in STEAMOS_SMT_INTERFACES:
            for prop in STEAMOS_SMT_PROPERTIES:
                ok, output, error = self._get_property(prop, interface)
                if ok:
                    signature = self._busctl_signature(output)
                    if signature in ("b", "y", "n", "q", "i", "u", "x", "t"):
                        return True, interface, prop, signature, output
                elif error:
                    last_error = error
        return False, "", "", "", last_error

    def get_smt_state(self) -> dict:
        ok, _interface, _prop, signature, output = self._get_smt_property()
        if not ok:
            return {
                "available": False,
                "enabled": False,
                "status": output,
                "details": "SteamOS Manager SMT control unavailable",
            }

        enabled = (
            self._parse_busctl_bool(output)
            if signature == "b"
            else self._parse_busctl_int(output) > 0
        )
        return {
            "available": True,
            "enabled": enabled,
            "status": "available",
            "details": "Controls SMT through SteamOS Manager",
        }

    def set_smt_enabled(self, enabled: bool) -> tuple[bool, str]:
        ok, interface, prop, signature, _output = self._get_smt_property()
        if not ok:
            return False, "SteamOS Manager SMT control unavailable"

        if signature == "b":
            return self._set_property(interface, prop, signature, "true" if enabled else "false")

        return self._set_property(interface, prop, signature, "1" if enabled else "0")


class GamescopeSettingsClient:
    """Small X11 root-property client for SteamOS gamescope settings."""

    def __init__(self, logger, display: str | None = None):
        self.logger = logger
        self.display = display or os.environ.get("DISPLAY") or ":0"
        self.display_candidates = self._build_display_candidates(display)

    def _build_display_candidates(self, preferred: str | None) -> list[str]:
        candidates = []
        for candidate in (preferred, os.environ.get("DISPLAY"), ":0", ":1"):
            if candidate and candidate not in candidates:
                candidates.append(candidate)
        return candidates or [":0"]

    def _xprop_env(self, display: str) -> dict:
        env = os.environ.copy()
        env["DISPLAY"] = display
        return env

    def _run_xprop(self, args: list[str], display: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["xprop", "-root", *args],
            capture_output=True,
            text=True,
            timeout=5,
            env=self._xprop_env(display),
        )

    def _should_try_next_display(self, error: str) -> bool:
        lowered = error.lower()
        return any(
            fragment in lowered
            for fragment in (
                "unable to open display",
                "can't open display",
                "cannot open display",
                "no such atom",
                "not available",
            )
        )

    def _read_cardinal(self, atom: str) -> tuple[bool, int, str]:
        last_error = ""

        for display in self.display_candidates:
            try:
                result = self._run_xprop([atom], display)
            except FileNotFoundError:
                return False, 0, "xprop is not installed"
            except subprocess.TimeoutExpired:
                return False, 0, "gamescope X property request timed out"
            except Exception as e:
                return False, 0, str(e)

            if result.returncode != 0:
                error = result.stderr.strip() or result.stdout.strip() or "xprop read failed"
                last_error = error
                if self._should_try_next_display(error):
                    continue
                return False, 0, error

            for line in result.stdout.splitlines():
                if not line.startswith(f"{atom}(") or "=" not in line:
                    continue

                raw_value = line.split("=", 1)[1].strip().split(",", 1)[0].strip()
                try:
                    self.display = display
                    return True, int(raw_value, 0), ""
                except ValueError:
                    return False, 0, f"Invalid gamescope property value: {raw_value}"

            last_error = f"{atom} is not available"

        return False, 0, last_error or f"{atom} is not available"

    def _set_cardinal(self, atom: str, enabled: bool) -> tuple[bool, str]:
        last_error = ""

        for display in self.display_candidates:
            try:
                result = self._run_xprop([
                    "-f",
                    atom,
                    "32c",
                    "-set",
                    atom,
                    "1" if enabled else "0",
                ], display)
            except FileNotFoundError:
                return False, "xprop is not installed"
            except subprocess.TimeoutExpired:
                return False, "gamescope X property request timed out"
            except Exception as e:
                return False, str(e)

            if result.returncode != 0:
                error = result.stderr.strip() or result.stdout.strip() or "xprop write failed"
                last_error = error
                if self._should_try_next_display(error):
                    continue
                return False, error

            self.display = display
            return True, ""

        return False, last_error or "xprop write failed"

    def get_display_sync_state(self) -> dict:
        vrr_capable_ok, vrr_capable_value, vrr_capable_error = self._read_cardinal(
            GAMESCOPE_VRR_CAPABLE_ATOM
        )
        vrr_enabled_ok, vrr_enabled_value, vrr_enabled_error = self._read_cardinal(
            GAMESCOPE_VRR_ENABLED_ATOM
        )
        vrr_feedback_ok, vrr_feedback_value, _ = self._read_cardinal(
            GAMESCOPE_VRR_FEEDBACK_ATOM
        )
        tearing_ok, tearing_value, tearing_error = self._read_cardinal(
            GAMESCOPE_ALLOW_TEARING_ATOM
        )

        vrr_capable = vrr_capable_ok and bool(vrr_capable_value)
        vrr_enabled = vrr_enabled_ok and bool(vrr_enabled_value)
        vrr_active = vrr_feedback_ok and bool(vrr_feedback_value)

        if not vrr_capable_ok:
            vrr_status = f"VRR state unavailable: {vrr_capable_error}"
        elif not vrr_capable:
            vrr_status = "Display is not VRR capable"
        else:
            vrr_status = "available"

        if not tearing_ok:
            vsync_status = f"VSync state unavailable: {tearing_error}"
        else:
            vsync_status = "available"

        return {
            "backend": "gamescope-xprop",
            "display": self.display,
            "vrr": {
                "available": vrr_capable_ok and vrr_capable,
                "capable": vrr_capable,
                "enabled": vrr_enabled,
                "active": vrr_active,
                "status": vrr_status,
                "details": "Gamescope VRR on current display",
            },
            "vsync": {
                "available": tearing_ok,
                "enabled": not bool(tearing_value) if tearing_ok else False,
                "allow_tearing": bool(tearing_value) if tearing_ok else False,
                "status": vsync_status,
                "details": "Maps to SteamOS Allow Tearing",
            },
        }

    def set_vrr_enabled(self, enabled: bool) -> tuple[bool, str]:
        capable_ok, capable_value, capable_error = self._read_cardinal(
            GAMESCOPE_VRR_CAPABLE_ATOM
        )
        if not capable_ok:
            return False, capable_error
        if not capable_value:
            return False, "Display is not VRR capable"

        return self._set_cardinal(GAMESCOPE_VRR_ENABLED_ATOM, enabled)

    def set_vsync_enabled(self, enabled: bool) -> tuple[bool, str]:
        # SteamOS exposes this as "Allow Tearing"; VSync is the inverse.
        return self._set_cardinal(GAMESCOPE_ALLOW_TEARING_ATOM, not enabled)


class Plugin:
    def __init__(self):
        self.settings_path: str | None = None
        self.settings: dict = {}
        self.steamos_manager: SteamOsManagerClient | None = None
        self.gamescope_settings: GamescopeSettingsClient | None = None

    async def _main(self):
        """Main entry point for the plugin"""
        self.settings_path = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json")
        self.steamos_manager = SteamOsManagerClient(decky.logger)
        self.gamescope_settings = GamescopeSettingsClient(decky.logger)
        await self.load_settings()
        decky.logger.info(f"{PLUGIN_NAME} initialized")

    async def _unload(self):
        """Cleanup when plugin is unloaded"""
        decky.logger.info(f"{PLUGIN_NAME} unloaded")

    async def _migration(self):
        """Handle plugin migrations"""
        pass

    async def load_settings(self):
        try:
            if os.path.exists(self.settings_path):
                with open(self.settings_path, 'r') as f:
                    self.settings = json.load(f)
            else:
                self.settings = {}
        except Exception as e:
            decky.logger.error(f"Failed to load settings: {e}")
            self.settings = {}

        return self.settings

    def _read_file(self, path: str, default: str = "Unknown") -> str:
        try:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    return f.read().strip() or default
        except Exception:
            pass
        return default

    def _find_first_existing_path(
        self,
        direct_paths: list[str],
        glob_patterns: list[str],
    ) -> str:
        for path in direct_paths:
            if path and os.path.exists(path):
                return path

        for pattern in glob_patterns:
            for path in sorted(glob.glob(pattern)):
                if path and os.path.exists(path):
                    return path

        return ""

    def _get_rgb_led_path(self) -> str:
        return self._find_first_existing_path([ALLY_LED_PATH], RGB_LED_PATH_GLOBS)

    def _get_os_release_values(self) -> dict:
        os_release = "/etc/os-release"
        try:
            if not os.path.exists(os_release):
                return {}

            values = {}
            with open(os_release, 'r') as f:
                for line in f:
                    if "=" not in line:
                        continue
                    key, value = line.strip().split("=", 1)
                    values[key] = value.strip('"')

            return values
        except Exception as e:
            decky.logger.error(f"Failed to read OS release data: {e}")
            return {}

    def _get_steamos_version(self, os_release_values: dict | None = None) -> str:
        values = os_release_values if os_release_values is not None else self._get_os_release_values()
        return (
            values.get("PRETTY_NAME")
            or values.get("VERSION")
            or values.get("NAME")
            or "Unknown"
        )

    def _is_steam_deck_device(
        self,
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

    def _is_supported_handheld_vendor_device(
        self,
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

        return False

    def _parse_version_tuple(self, raw_version: str) -> tuple[int, int] | None:
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

    def _steamos_version_is_supported(self, values: dict) -> bool:
        for key in ("VERSION_ID", "VERSION", "PRETTY_NAME"):
            parsed = self._parse_version_tuple(values.get(key, ""))
            if parsed is not None:
                return parsed >= STEAMOS_MIN_VERSION
        return False

    def _get_platform_support(
        self,
        board_name: str,
        product_name: str,
        sys_vendor: str,
        product_family: str,
        os_release_values: dict | None = None,
    ) -> dict:
        values = os_release_values if os_release_values is not None else self._get_os_release_values()
        os_id = values.get("ID", "").strip().lower()
        os_name = " ".join(
            values.get(key, "")
            for key in ("NAME", "PRETTY_NAME", "ID", "ID_LIKE")
        ).lower()

        if self._is_steam_deck_device(board_name, product_name, sys_vendor, product_family):
            return {
                "supported": False,
                "support_level": "blocked",
                "reason": "Steam Deck is blocked to avoid interfering with Valve hardware defaults.",
            }

        if os_id != "steamos" or any(name in os_name for name in ("bazzite", "chimeraos", "chimera")):
            return {
                "supported": False,
                "support_level": "blocked",
                "reason": "Xbox Companion is only enabled on SteamOS 3.8 or newer.",
            }

        if not self._steamos_version_is_supported(values):
            return {
                "supported": False,
                "support_level": "blocked",
                "reason": "Xbox Companion requires SteamOS 3.8 or newer.",
            }

        if not self._is_supported_handheld_vendor_device(
            board_name,
            product_name,
            sys_vendor,
            product_family,
        ):
            return {
                "supported": False,
                "support_level": "blocked",
                "reason": "Xbox Companion is only enabled on ASUS and Lenovo handhelds.",
            }

        return {
            "supported": True,
            "support_level": "supported",
            "reason": "Supported ASUS/Lenovo handheld on SteamOS 3.8 or newer.",
        }

    def _get_device_metadata(
        self,
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

    def _get_current_platform_support(self) -> dict:
        board_name = self._read_file(os.path.join(DMI_PATH, "board_name"))
        product_name = self._read_file(os.path.join(DMI_PATH, "product_name"))
        product_family = self._read_file(os.path.join(DMI_PATH, "product_family"))
        sys_vendor = self._read_file(os.path.join(DMI_PATH, "sys_vendor"))
        return self._get_platform_support(
            board_name,
            product_name,
            sys_vendor,
            product_family,
        )

    async def get_device_info(self) -> dict:
        info = {
            "model": "Unknown",
            "friendly_name": "Unknown",
            "board_name": "Unknown",
            "product_name": "Unknown",
            "sys_vendor": "Unknown",
            "variant": "Unknown",
            "device_family": "unknown",
            "support_level": "unsupported",
            "steamos_version": "Unknown",
            "bios_version": "Unknown",
            "serial": "Unknown",
            "cpu": "Unknown",
            "gpu": "Unknown",
            "kernel": "Unknown",
            "memory_total": "Unknown",
            "platform_supported": False,
            "platform_support_reason": "Platform support has not been checked",
        }
        
        try:
            os_release_values = self._get_os_release_values()

            # Read DMI info
            dmi_files = {
                "model": "product_name",
                "product_name": "product_name",
                "product_family": "product_family",
                "sys_vendor": "sys_vendor",
                "board_name": "board_name",
                "bios_version": "bios_version",
                "serial": "product_serial"
            }
            
            for key, filename in dmi_files.items():
                filepath = os.path.join(DMI_PATH, filename)
                if os.path.exists(filepath):
                    with open(filepath, 'r') as f:
                        info[key] = f.read().strip()

            device_metadata = self._get_device_metadata(
                board_name=info.get("board_name", "Unknown"),
                product_name=info.get("model", "Unknown"),
                sys_vendor=info.get("sys_vendor", "Unknown"),
                product_family=info.get("product_family", "Unknown"),
            )
            platform_support = self._get_platform_support(
                board_name=info.get("board_name", "Unknown"),
                product_name=info.get("model", "Unknown"),
                sys_vendor=info.get("sys_vendor", "Unknown"),
                product_family=info.get("product_family", "Unknown"),
                os_release_values=os_release_values,
            )
            info.update(device_metadata)
            info.update(platform_support)
            info["platform_supported"] = platform_support.get("supported", False)
            info["platform_support_reason"] = platform_support.get("reason", "")
            info["steamos_version"] = self._get_steamos_version(os_release_values)
            
            # Get CPU info
            if os.path.exists("/proc/cpuinfo"):
                with open("/proc/cpuinfo", 'r') as f:
                    for line in f:
                        if line.startswith("model name"):
                            info["cpu"] = line.split(":")[1].strip()
                            break
            
            # Get kernel version
            result = subprocess.run(["uname", "-r"], capture_output=True, text=True)
            if result.returncode == 0:
                info["kernel"] = result.stdout.strip()
            
            # Get memory info
            if os.path.exists("/proc/meminfo"):
                with open("/proc/meminfo", 'r') as f:
                    for line in f:
                        if line.startswith("MemTotal"):
                            mem_kb = int(line.split()[1])
                            info["memory_total"] = f"{mem_kb // 1024 // 1024} GB"
                            break
            
            # GPU info (AMD APU)
            info["gpu"] = "AMD Radeon 780M" if "Z1" in info.get("cpu", "") else "AMD Radeon Graphics"
            
        except Exception as e:
            decky.logger.error(f"Failed to get device info: {e}")
        
        return info

    async def get_battery_info(self) -> dict:
        battery = {
            "present": False,
            "status": "Unknown",
            "capacity": 0,
            "health": 100,
            "cycle_count": 0,
            "voltage": 0,
            "current": 0,
            "temperature": 0,
            "design_capacity": 0,
            "full_capacity": 0,
            "charge_limit": STEAMOS_CHARGE_FULL_PERCENT,
            "time_to_empty": "Unknown",
            "time_to_full": "Unknown"
        }
        
        try:
            if not os.path.exists(BATTERY_PATH):
                return battery
            
            battery["present"] = True
            
            # Read battery files
            battery_files = {
                "status": "status",
                "capacity": "capacity",
                "cycle_count": "cycle_count",
                "voltage_now": "voltage_now",
                "current_now": "current_now",
                "energy_full_design": "energy_full_design",
                "energy_full": "energy_full"
            }
            
            for key, filename in battery_files.items():
                filepath = os.path.join(BATTERY_PATH, filename)
                if os.path.exists(filepath):
                    with open(filepath, 'r') as f:
                        value = f.read().strip()
                        if key == "status":
                            battery["status"] = value
                        elif key == "capacity":
                            battery["capacity"] = int(value)
                        elif key == "cycle_count":
                            battery["cycle_count"] = int(value)
                        elif key == "voltage_now":
                            battery["voltage"] = int(value) / 1000000  # Convert to V
                        elif key == "current_now":
                            battery["current"] = int(value) / 1000000  # Convert to A
                        elif key == "energy_full_design":
                            battery["design_capacity"] = int(value) / 1000000  # Convert to Wh
                        elif key == "energy_full":
                            battery["full_capacity"] = int(value) / 1000000  # Convert to Wh
            
            # Calculate health percentage
            if battery["design_capacity"] > 0:
                battery["health"] = round((battery["full_capacity"] / battery["design_capacity"]) * 100, 1)
            
            # Try to get temperature from ACPI
            temp_path = os.path.join(BATTERY_PATH, "temp")
            if os.path.exists(temp_path):
                with open(temp_path, 'r') as f:
                    battery["temperature"] = int(f.read().strip()) / 10  # Convert to Celsius

            charge_limit_state = await self.get_charge_limit_state()
            battery["charge_limit"] = charge_limit_state.get("limit", battery["charge_limit"])
            
        except Exception as e:
            decky.logger.error(f"Failed to get battery info: {e}")
        
        return battery

    def _set_led_color(self, led_path: str, color: str, enabled: bool) -> bool:
        try:
            brightness_path = os.path.join(led_path, "brightness")
            multi_intensity_path = os.path.join(led_path, "multi_intensity")
            if not os.path.exists(brightness_path) or not os.path.exists(multi_intensity_path):
                return False

            if not enabled:
                with open(brightness_path, "w") as f:
                    f.write("0")
                return True

            rgb = color.lstrip("#")
            if len(rgb) != 6:
                return False

            r = int(rgb[0:2], 16)
            g = int(rgb[2:4], 16)
            b = int(rgb[4:6], 16)
            color_int = (r << 16) | (g << 8) | b

            with open(multi_intensity_path, "w") as f:
                f.write(f"{color_int} {color_int} {color_int} {color_int}")
            with open(brightness_path, "w") as f:
                f.write("255")
            return True
        except Exception as e:
            decky.logger.warning(f"Failed to apply RGB state: {e}")
            return False

    def _read_rgb_state_from_led(self, led_path: str) -> tuple[bool, str]:
        enabled = False
        color = RGB_COLOR_PRESETS[0]

        try:
            brightness_path = os.path.join(led_path, "brightness")
            if os.path.exists(brightness_path):
                with open(brightness_path, "r") as f:
                    enabled = int(f.read().strip() or "0") > 0
        except Exception:
            enabled = False

        try:
            multi_intensity_path = os.path.join(led_path, "multi_intensity")
            if os.path.exists(multi_intensity_path):
                with open(multi_intensity_path, "r") as f:
                    values = [int(value) for value in f.read().split() if value.strip()]
                if values:
                    color_int = values[0]
                    r = (color_int >> 16) & 0xFF
                    g = (color_int >> 8) & 0xFF
                    b = color_int & 0xFF
                    color = f"#{r:02X}{g:02X}{b:02X}"
        except Exception:
            color = RGB_COLOR_PRESETS[0]

        return enabled, color

    async def get_rgb_state(self) -> dict:
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            return {
                "available": False,
                "enabled": False,
                "color": RGB_COLOR_PRESETS[0],
                "presets": RGB_COLOR_PRESETS,
                "details": support.get("reason", "Platform is not supported"),
            }

        led_path = self._get_rgb_led_path()
        enabled, color = self._read_rgb_state_from_led(led_path) if led_path else (False, RGB_COLOR_PRESETS[0])
        return {
            "available": bool(led_path),
            "enabled": enabled,
            "color": color,
            "presets": RGB_COLOR_PRESETS,
            "details": "Simple RGB lighting control for compatible joystick rings",
        }

    async def set_rgb_enabled(self, enabled: bool) -> bool:
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            decky.logger.warning(support.get("reason", "Platform is not supported"))
            return False

        led_path = self._get_rgb_led_path()
        if not led_path:
            decky.logger.warning("RGB control not available")
            return False

        _current_enabled, current_color = self._read_rgb_state_from_led(led_path)
        success = self._set_led_color(led_path, current_color, enabled)
        if not success:
            return False

        return True

    async def set_rgb_color(self, color: str) -> bool:
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            decky.logger.warning(support.get("reason", "Platform is not supported"))
            return False

        led_path = self._get_rgb_led_path()
        if not led_path:
            decky.logger.warning("RGB control not available")
            return False

        normalized = color.upper()
        if normalized not in RGB_COLOR_PRESETS:
            decky.logger.warning(f"Unsupported RGB color preset: {color}")
            return False

        enabled, _current_color = self._read_rgb_state_from_led(led_path)
        success = self._set_led_color(led_path, normalized, enabled)
        if not success:
            return False

        return True

    def _command_exists(self, cmd: str) -> bool:
        return shutil.which(cmd) is not None

    def _write_managed_file(self, path: str, content: str, mode: int | None = None):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        if mode is not None:
            os.chmod(path, mode)

    def _remove_file(self, path: str):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            decky.logger.warning(f"Failed to remove {path}: {e}")

    def _cleanup_legacy_atomic_manifests(self):
        for path in LEGACY_ATOMIC_PATHS:
            self._remove_file(path)

    def _atomic_managed_entries(self) -> list[str]:
        checks = [
            (SCX_DEFAULT_PATH, ['SCX_SCHEDULER="scx_lavd"', 'SCX_FLAGS="--performance"']),
            (
                MEMORY_SYSCTL_PATH,
                ["vm.swappiness = 10", "vm.min_free_kbytes = 524288", "vm.dirty_ratio = 5"],
            ),
            (THP_TMPFILES_PATH, ["madvise"]),
            (NPU_BLACKLIST_PATH, ["blacklist amdxdna"]),
            (USB_WAKE_SERVICE_PATH, ["Xbox Companion - Block USB Wake"]),
            (
                GRUB_HEALER_SCRIPT_PATH,
                ["amd_pstate=active", "amdgpu.abmlevel=0", "pcie_aspm=force"],
            ),
            (GRUB_HEALER_SERVICE_PATH, ["Xbox Companion - Auto-patch GRUB"]),
        ]
        return [path for path, needles in checks if self._file_contains_all(path, needles)]

    def _refresh_atomic_manifest(self):
        entries = self._atomic_managed_entries()
        if entries:
            content = "\n".join(entries) + "\n"
            self._write_managed_file(ATOMIC_MANIFEST_PATH, content)
        else:
            self._remove_file(ATOMIC_MANIFEST_PATH)
        self._cleanup_legacy_atomic_manifests()

    def _atomic_manifest_contains(self, paths: list[str]) -> bool:
        return self._file_contains_all(ATOMIC_MANIFEST_PATH, paths)

    def _migrate_atomic_manifest_if_needed(self):
        if any(os.path.exists(path) for path in LEGACY_ATOMIC_PATHS):
            self._refresh_atomic_manifest()

    def _remove_managed_file(
        self,
        path: str,
        removed_files: list[str],
        skipped_files: list[str],
        errors: list[str],
        needles: list[str] | None = None,
    ):
        try:
            if not os.path.exists(path):
                return

            if needles and not self._file_contains_all(path, needles):
                skipped_files.append(path)
                return

            os.remove(path)
            removed_files.append(path)
        except Exception as e:
            errors.append(f"{path}: {e}")

    def _run_command(self, command: list[str]) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except FileNotFoundError:
            return False, f"{command[0]} is not installed"
        except subprocess.TimeoutExpired:
            return False, f"{command[0]} timed out"
        except Exception as e:
            return False, str(e)

        if result.returncode != 0:
            return False, result.stderr.strip() or result.stdout.strip()

        return True, ""

    def _run_command_output(self, command: list[str]) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except FileNotFoundError:
            return False, f"{command[0]} is not installed"
        except subprocess.TimeoutExpired:
            return False, f"{command[0]} timed out"
        except Exception as e:
            return False, str(e)

        if result.returncode != 0:
            return False, result.stderr.strip() or result.stdout.strip()

        return True, result.stdout.strip()

    def _run_optional_command(self, command: list[str]) -> str:
        success, error = self._run_command(command)
        if not success:
            decky.logger.warning(f"Optional command failed: {' '.join(command)}: {error}")
            return error
        return ""

    def _get_fps_presets(self) -> list[int]:
        presets = list(FPS_NATIVE_PRESET_VALUES)
        presets.extend(self._get_supported_high_refresh_rates())
        presets.append(FPS_OPTION_DISABLED)
        return presets

    def _get_supported_high_refresh_rates(self) -> list[int]:
        if not self._command_exists("xrandr"):
            return []

        success, output = self._run_command_output(["xrandr", "--current"])
        if not success:
            return []

        refresh_rates = set()
        for token in output.split():
            candidate = token.rstrip("*+")
            if "." not in candidate:
                continue

            try:
                value = float(candidate)
            except ValueError:
                continue

            rounded = int(round(value))
            if rounded >= FPS_HIGH_REFRESH_MIN:
                refresh_rates.add(rounded)

        return sorted(refresh_rates)

    def _systemctl(self, *args: str) -> str:
        return self._run_optional_command(["systemctl", *args])

    def _service_enabled(self, service: str) -> bool:
        try:
            result = subprocess.run(
                ["systemctl", "is-enabled", service],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0 and result.stdout.strip() == "enabled"
        except Exception:
            return False

    def _service_active(self, service: str) -> bool:
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0 and result.stdout.strip() == "active"
        except Exception:
            return False

    def _read_sysctl(self, key: str) -> str:
        result = subprocess.run(
            ["sysctl", "-n", key],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip()

    def _file_contains_all(self, path: str, needles: list[str]) -> bool:
        try:
            if not os.path.exists(path):
                return False
            with open(path, "r") as f:
                contents = f.read()
            return all(needle in contents for needle in needles)
        except Exception:
            return False

    def _is_amd_platform(self) -> bool:
        return "AMD" in self._read_file("/proc/cpuinfo", "").upper()

    def _thp_is_madvise(self) -> bool:
        try:
            if not os.path.exists(THP_ENABLED_PATH):
                return False
            with open(THP_ENABLED_PATH, "r") as f:
                return "[madvise]" in f.read()
        except Exception:
            return False

    def _kernel_params_active(self) -> bool:
        try:
            with open("/proc/cmdline", "r") as f:
                cmdline = f.read()
            return all(param in cmdline for param in GRUB_KERNEL_PARAMS)
        except Exception:
            return False

    def _grub_params_configured(self) -> bool:
        return self._file_contains_all(GRUB_DEFAULT_PATH, GRUB_KERNEL_PARAMS)

    def _update_grub_params(self, enabled: bool) -> str:
        if not os.path.exists(GRUB_DEFAULT_PATH):
            return "GRUB config not found"

        try:
            with open(GRUB_DEFAULT_PATH, "r") as f:
                contents = f.read()

            params = " ".join(GRUB_KERNEL_PARAMS)
            lines = []
            changed = False

            for line in contents.splitlines():
                if line.startswith("GRUB_CMDLINE_LINUX_DEFAULT="):
                    prefix, value = line.split("=", 1)
                    quote = '"' if value.startswith('"') else ""
                    raw = value.strip('"')
                    parts = [part for part in raw.split() if part not in GRUB_KERNEL_PARAMS]

                    if enabled:
                        parts.extend(param for param in GRUB_KERNEL_PARAMS if param not in parts)

                    new_value = " ".join(parts).strip()
                    line = f'{prefix}="{new_value}"' if quote else f"{prefix}={new_value}"
                    changed = True
                lines.append(line)

            if not changed and enabled:
                lines.append(f'GRUB_CMDLINE_LINUX_DEFAULT="{params}"')

            with open(GRUB_DEFAULT_PATH, "w") as f:
                f.write("\n".join(lines) + "\n")

            if self._command_exists("update-grub"):
                return self._run_optional_command(["update-grub"])
            return "update-grub is not installed"
        except Exception as e:
            return str(e)

    def _optimization_state(
        self,
        key: str,
        name: str,
        description: str,
        enabled: bool,
        active: bool,
        available: bool = True,
        needs_reboot: bool = False,
        details: str = "",
        risk_note: str = "",
    ) -> dict:
        status = "unavailable"
        if available:
            if needs_reboot:
                status = "reboot-required"
            elif enabled and active:
                status = "active"
            elif enabled:
                status = "configured"
            elif active:
                status = "active"
            else:
                status = "off"

        return {
            "key": key,
            "name": name,
            "description": description,
            "enabled": enabled,
            "active": active,
            "available": available,
            "needs_reboot": needs_reboot,
            "details": details,
            "risk_note": risk_note,
            "status": status,
        }

    def _get_lavd_state(self) -> dict:
        configured = self._file_contains_all(
            SCX_DEFAULT_PATH,
            ['SCX_SCHEDULER="scx_lavd"', 'SCX_FLAGS="--performance"'],
        )
        atomic = self._atomic_manifest_contains([SCX_DEFAULT_PATH])
        service_active = self._service_active("scx.service")
        service_enabled = self._service_enabled("scx.service")
        enabled = configured and atomic and service_enabled

        return self._optimization_state(
            "lavd",
            "LAVD Scheduler",
            "Switch SteamOS scheduling to scx_lavd for smoother frame delivery.",
            enabled,
            service_active,
            available=self._command_exists("systemctl"),
            details="Configured" if configured else "Not configured",
            risk_note="Touches a system service.",
        )

    def _get_memory_state(self) -> dict:
        configured = self._file_contains_all(
            MEMORY_SYSCTL_PATH,
            ["vm.swappiness = 10", "vm.min_free_kbytes = 524288", "vm.dirty_ratio = 5"],
        )
        thp_configured = self._file_contains_all(THP_TMPFILES_PATH, ["madvise"])
        atomic = self._atomic_manifest_contains(
            [MEMORY_SYSCTL_PATH, THP_TMPFILES_PATH],
        )
        enabled = configured and thp_configured and atomic
        runtime = (
            self._read_sysctl("vm.swappiness") == "10"
            and self._read_sysctl("vm.min_free_kbytes") == "524288"
            and self._read_sysctl("vm.dirty_ratio") == "5"
            and self._thp_is_madvise()
        )

        return self._optimization_state(
            "memory",
            "Memory + THP",
            "Applies memory sysctl tuning and sets Transparent Huge Pages to madvise.",
            enabled,
            runtime,
            available=self._command_exists("sysctl") and os.path.exists(THP_ENABLED_PATH),
            needs_reboot=(enabled and not runtime) or (not enabled and runtime),
            details="swappiness 10, THP madvise",
            risk_note="Some changes only fully settle after reboot.",
        )

    def _get_power_state(self) -> dict:
        npu_configured = self._file_contains_all(NPU_BLACKLIST_PATH, ["blacklist amdxdna"])
        service_configured = os.path.exists(USB_WAKE_SERVICE_PATH)
        atomic = self._atomic_manifest_contains(
            [NPU_BLACKLIST_PATH, USB_WAKE_SERVICE_PATH],
        )
        service_enabled = self._service_enabled("xbox-companion-disable-usb-wake.service")
        service_active = self._service_active("xbox-companion-disable-usb-wake.service")
        enabled = npu_configured and service_configured and atomic and service_enabled

        return self._optimization_state(
            "power",
            "NPU + USB Wake",
            "Disables background wake sources and blacklists the AMD NPU module.",
            enabled,
            service_active,
            available=self._command_exists("systemctl") and self._is_amd_platform(),
            needs_reboot=enabled and os.path.exists("/sys/module/amdxdna"),
            details="NPU blacklist, USB wake service",
            risk_note="Touches a boot module and a system service.",
        )

    def _get_grub_healer_state(self) -> dict:
        script_configured = self._file_contains_all(
            GRUB_HEALER_SCRIPT_PATH,
            ["amd_pstate=active", "amdgpu.abmlevel=0", "pcie_aspm=force"],
        )
        service_configured = os.path.exists(GRUB_HEALER_SERVICE_PATH)
        atomic = self._atomic_manifest_contains(
            [GRUB_HEALER_SCRIPT_PATH, GRUB_HEALER_SERVICE_PATH],
        )
        service_enabled = self._service_enabled("xbox-companion-grub-healer.service")
        configured = script_configured and service_configured and atomic and service_enabled
        enabled = configured and self._grub_params_configured()
        active = self._kernel_params_active()

        return self._optimization_state(
            "grub_healer",
            "Kernel Params",
            "Maintains recommended kernel parameters after SteamOS updates.",
            enabled,
            active,
            available=os.path.exists(GRUB_DEFAULT_PATH) and self._is_amd_platform(),
            needs_reboot=(enabled and not active) or (not enabled and active),
            details="amd_pstate, ABM off, ASPM",
            risk_note="Modifies boot configuration.",
        )

    async def get_optimization_states(self) -> dict:
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            return {
                "states": [
                    self._optimization_state(
                        "platform_guard",
                        "Platform Guard",
                        support.get("reason", "Platform is not supported"),
                        False,
                        False,
                        available=False,
                    )
                ],
            }

        self._migrate_atomic_manifest_if_needed()

        states = [
            self._get_lavd_state(),
            self._get_memory_state(),
            self._get_power_state(),
            self._get_grub_healer_state(),
        ]

        return {
            "states": states,
        }

    async def set_optimization_enabled(self, key: str, enabled: bool) -> bool:
        try:
            support = self._get_current_platform_support()
            if not support.get("supported", False):
                decky.logger.warning(support.get("reason", "Platform is not supported"))
                return False

            handlers = {
                "lavd": self._set_lavd_enabled,
                "memory": self._set_memory_enabled,
                "power": self._set_power_enabled,
                "grub_healer": self._set_grub_healer_enabled,
            }
            states = {
                "lavd": self._get_lavd_state,
                "memory": self._get_memory_state,
                "power": self._get_power_state,
                "grub_healer": self._get_grub_healer_state,
            }

            handler = handlers.get(key)
            state_reader = states.get(key)
            if handler is None or state_reader is None:
                decky.logger.error(f"Unknown optimization: {key}")
                return False

            handler(enabled)
            state = state_reader()
            if enabled:
                return state.get("enabled", False)
            return not state.get("enabled", False) and not state.get("active", False)
        except Exception as e:
            decky.logger.error(f"Failed to toggle optimization {key}: {e}")
            return False

    def _set_lavd_enabled(self, enabled: bool):
        if enabled:
            self._write_managed_file(SCX_DEFAULT_PATH, SCX_DEFAULT_CONTENT)
            self._refresh_atomic_manifest()
            if self._command_exists("steamosctl"):
                self._run_optional_command(["steamosctl", "set-cpu-scheduler", "lavd"])
            self._systemctl("enable", "--now", "scx.service")
        else:
            self._systemctl("disable", "--now", "scx.service")
            removed_files = []
            skipped_files = []
            errors = []
            self._remove_managed_file(
                SCX_DEFAULT_PATH,
                removed_files,
                skipped_files,
                errors,
                ['SCX_SCHEDULER="scx_lavd"', 'SCX_FLAGS="--performance"'],
            )
            for error in errors:
                decky.logger.warning(f"Failed to clean LAVD file: {error}")
            self._refresh_atomic_manifest()

    def _set_memory_enabled(self, enabled: bool):
        if enabled:
            self._write_managed_file(MEMORY_SYSCTL_PATH, MEMORY_SYSCTL_CONTENT)
            self._write_managed_file(THP_TMPFILES_PATH, THP_TMPFILES_CONTENT)
            self._refresh_atomic_manifest()
            self._run_optional_command(["sysctl", "--system"])
            self._run_optional_command(["systemd-tmpfiles", "--create", THP_TMPFILES_PATH])
        else:
            self._remove_file(MEMORY_SYSCTL_PATH)
            self._remove_file(THP_TMPFILES_PATH)
            self._refresh_atomic_manifest()
            self._run_optional_command(["sysctl", "--system"])
            self._run_optional_command(["systemd-tmpfiles", "--create"])

    def _set_power_enabled(self, enabled: bool):
        if enabled and not self._is_amd_platform():
            decky.logger.warning("Power optimization requires an AMD platform")
            return

        service_name = "xbox-companion-disable-usb-wake.service"
        if enabled:
            self._write_managed_file(NPU_BLACKLIST_PATH, NPU_BLACKLIST_CONTENT)
            self._write_managed_file(USB_WAKE_SERVICE_PATH, USB_WAKE_SERVICE_CONTENT)
            self._refresh_atomic_manifest()
            self._systemctl("daemon-reload")
            self._systemctl("enable", "--now", service_name)
        else:
            self._systemctl("disable", "--now", service_name)
            self._remove_file(NPU_BLACKLIST_PATH)
            self._remove_file(USB_WAKE_SERVICE_PATH)
            self._refresh_atomic_manifest()
            self._systemctl("daemon-reload")

    def _set_grub_healer_enabled(self, enabled: bool):
        if enabled and not self._is_amd_platform():
            decky.logger.warning("Kernel parameter optimization requires an AMD platform")
            return

        service_name = "xbox-companion-grub-healer.service"
        if enabled:
            self._write_managed_file(GRUB_HEALER_SCRIPT_PATH, GRUB_HEALER_SCRIPT_CONTENT, 0o755)
            self._write_managed_file(GRUB_HEALER_SERVICE_PATH, GRUB_HEALER_SERVICE_CONTENT)
            self._refresh_atomic_manifest()
            self._update_grub_params(True)
            self._systemctl("daemon-reload")
            self._systemctl("enable", service_name)
        else:
            self._systemctl("disable", "--now", service_name)
            self._update_grub_params(False)
            self._remove_file(GRUB_HEALER_SCRIPT_PATH)
            self._remove_file(GRUB_HEALER_SERVICE_PATH)
            self._refresh_atomic_manifest()
            self._systemctl("daemon-reload")

    async def get_performance_profiles(self) -> dict:
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            return {
                "profiles": {
                    profile_id: {**profile, "available": False}
                    for profile_id, profile in NATIVE_PERFORMANCE_PROFILES.items()
                },
                "current": "",
                "suggested_default": "",
                "available": False,
                "available_native": [],
                "status": support.get("reason", "Platform is not supported"),
            }

        if self.steamos_manager is None:
            self.steamos_manager = SteamOsManagerClient(decky.logger)

        native_state = self.steamos_manager.get_performance_state()
        available_native = native_state.get("available_native", [])
        current = native_state.get("current") or ""
        profiles = {}

        for profile_id, profile in NATIVE_PERFORMANCE_PROFILES.items():
            profiles[profile_id] = {
                **profile,
                "available": native_state.get("available", False) and profile_id in available_native
            }

        return {
            "profiles": profiles,
            "current": current,
            "suggested_default": native_state.get("suggested_default", ""),
            "available": native_state.get("available", False),
            "available_native": available_native,
            "status": native_state.get("status", "SteamOS native profiles unavailable")
        }

    async def get_performance_modes(self) -> dict:
        profiles_data = await self.get_performance_profiles()
        active_native = profiles_data.get("current", "")
        active_mode = active_native if active_native in NATIVE_PERFORMANCE_PROFILES else ""

        modes = []
        for profile_id, profile in NATIVE_PERFORMANCE_PROFILES.items():
            native_profile = profiles_data["profiles"].get(profile_id, {})
            modes.append({
                "id": profile_id,
                "label": profile["name"],
                "native_id": profile_id,
                "description": profile["description"],
                "available": native_profile.get("available", False),
                "active": active_mode == profile_id and native_profile.get("available", False),
            })

        return {
            "modes": modes,
            "active_mode": active_mode,
            "native_active": active_native,
            "available": profiles_data.get("available", False),
            "status": profiles_data.get("status", "SteamOS native profiles unavailable"),
        }

    async def set_performance_profile(self, profile_id: str) -> bool:
        try:
            support = self._get_current_platform_support()
            if not support.get("supported", False):
                decky.logger.warning(support.get("reason", "Platform is not supported"))
                return False

            if profile_id not in NATIVE_PERFORMANCE_PROFILES:
                decky.logger.error(f"Unknown profile: {profile_id}")
                return False

            if self.steamos_manager is None:
                self.steamos_manager = SteamOsManagerClient(decky.logger)

            native_state = self.steamos_manager.get_performance_state()
            if not native_state.get("available", False):
                decky.logger.warning(native_state.get("status", "SteamOS native profiles unavailable"))
                return False

            if profile_id not in native_state.get("available_native", []):
                decky.logger.warning(f"SteamOS performance profile is not available: {profile_id}")
                return False

            success, error = self.steamos_manager.set_performance_profile(profile_id)
            if not success:
                decky.logger.error(f"Failed to set SteamOS performance profile: {error}")
                return False
            
            profile_name = NATIVE_PERFORMANCE_PROFILES[profile_id]["name"]
            decky.logger.info(f"Applied SteamOS performance profile: {profile_name} ({profile_id})")
            return True
            
        except Exception as e:
            decky.logger.error(f"Failed to set performance profile: {e}")
            return False

    async def get_display_sync_state(self) -> dict:
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            reason = support.get("reason", "Platform is not supported")
            return {
                "backend": "platform-guard",
                "display": "",
                "vrr": {
                    "available": False,
                    "capable": False,
                    "enabled": False,
                    "active": False,
                    "status": reason,
                    "details": reason,
                },
                "vsync": {
                    "available": False,
                    "enabled": False,
                    "allow_tearing": False,
                    "status": reason,
                    "details": reason,
                },
            }

        if self.gamescope_settings is None:
            self.gamescope_settings = GamescopeSettingsClient(decky.logger)

        return self.gamescope_settings.get_display_sync_state()

    async def set_display_sync_setting(self, key: str, enabled: bool) -> bool:
        try:
            support = self._get_current_platform_support()
            if not support.get("supported", False):
                decky.logger.warning(support.get("reason", "Platform is not supported"))
                return False

            if self.gamescope_settings is None:
                self.gamescope_settings = GamescopeSettingsClient(decky.logger)

            if key == "vrr":
                success, error = self.gamescope_settings.set_vrr_enabled(enabled)
            elif key == "vsync":
                success, error = self.gamescope_settings.set_vsync_enabled(enabled)
            else:
                decky.logger.error(f"Unknown display sync setting: {key}")
                return False

            if not success:
                decky.logger.warning(f"Failed to set display sync setting {key}: {error}")
                return False

            decky.logger.info(
                f"Set display sync setting {key} to {'enabled' if enabled else 'disabled'}"
            )
            return True
        except Exception as e:
            decky.logger.error(f"Failed to set display sync setting {key}: {e}")
            return False

    async def get_fps_limit_state(self) -> dict:
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            return {
                "available": False,
                "current": 0,
                "requested": 0,
                "is_live": False,
                "presets": self._get_fps_presets(),
                "status": support.get("reason", "Platform is not supported"),
                "details": support.get("reason", "Platform is not supported"),
            }

        available = self._command_exists("gamescopectl")
        live_value = None

        if available:
            success, output = self._run_command_output(["gamescopectl", "debug_get_fps_limit"])
            if success:
                try:
                    live_value = int((output or "0").splitlines()[-1])
                except Exception as exc:
                    decky.logger.warning(f"Could not parse live gamescope fps limit: {exc}")
            elif output:
                decky.logger.warning(f"Could not read live gamescope fps limit: {output}")

        current = 0 if live_value is None else live_value
        return {
            "available": available,
            "current": current,
            "requested": current,
            "is_live": live_value is not None,
            "presets": self._get_fps_presets(),
            "status": "available" if available else "gamescopectl is not installed",
            "details": (
                "Uses live gamescope framerate control"
                if live_value is not None
                else "Live gamescope framerate control is available, but the current limit cannot be read"
                if available
                else "Live framerate control is unavailable on this system"
            ),
        }

    async def set_fps_limit(self, value: int) -> bool:
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            decky.logger.warning(support.get("reason", "Platform is not supported"))
            return False

        value = max(0, int(value))
        if not self._command_exists("gamescopectl"):
            decky.logger.warning("gamescopectl is not installed")
            return False

        if value not in self._get_fps_presets():
            decky.logger.warning(f"Unsupported framerate preset: {value}")
            return False

        success, error = self._run_command([
            "gamescopectl",
            "debug_set_fps_limit",
            str(value),
        ])
        if not success:
            decky.logger.error(f"Failed to set framerate limit: {error}")
            return False

        decky.logger.info(
            "Applied gamescope framerate limit: unlimited"
            if value == 0
            else f"Applied gamescope framerate limit: {value}"
        )
        return True

    async def get_charge_limit_state(self) -> dict:
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            return {
                "available": False,
                "enabled": False,
                "limit": STEAMOS_CHARGE_FULL_PERCENT,
                "status": support.get("reason", "Platform is not supported"),
                "details": support.get("reason", "Platform is not supported"),
            }

        if self.steamos_manager is None:
            self.steamos_manager = SteamOsManagerClient(decky.logger)

        return self.steamos_manager.get_charge_limit_state()

    async def set_charge_limit_enabled(self, enabled: bool) -> bool:
        try:
            support = self._get_current_platform_support()
            if not support.get("supported", False):
                decky.logger.warning(support.get("reason", "Platform is not supported"))
                return False

            if self.steamos_manager is None:
                self.steamos_manager = SteamOsManagerClient(decky.logger)

            success, error = self.steamos_manager.set_charge_limit_enabled(enabled)
            if not success:
                decky.logger.warning(f"Failed to set SteamOS charge limit: {error}")
                return False

            decky.logger.info(
                f"SteamOS charge limit {'enabled' if enabled else 'disabled'}"
            )
            return True
        except Exception as e:
            decky.logger.error(f"Failed to set SteamOS charge limit: {e}")
            return False

    async def get_smt_state(self) -> dict:
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            return {
                "available": False,
                "enabled": False,
                "status": support.get("reason", "Platform is not supported"),
                "details": support.get("reason", "Platform is not supported"),
            }

        if self.steamos_manager is None:
            self.steamos_manager = SteamOsManagerClient(decky.logger)

        steamos_state = self.steamos_manager.get_smt_state()
        if steamos_state.get("available", False):
            return steamos_state

        if not os.path.exists(SMT_CONTROL_PATH):
            return steamos_state

        try:
            with open(SMT_CONTROL_PATH, "r") as f:
                smt_state = f.read().strip()
            return {
                "available": True,
                "enabled": smt_state == "on",
                "status": "available",
                "details": "Controls SMT through the kernel SMT interface",
            }
        except Exception as e:
            return {
                "available": False,
                "enabled": False,
                "status": str(e),
                "details": "SMT control unavailable",
            }

    async def set_smt_enabled(self, enabled: bool) -> bool:
        try:
            support = self._get_current_platform_support()
            if not support.get("supported", False):
                decky.logger.warning(support.get("reason", "Platform is not supported"))
                return False

            if self.steamos_manager is None:
                self.steamos_manager = SteamOsManagerClient(decky.logger)

            steamos_state = self.steamos_manager.get_smt_state()
            if steamos_state.get("available", False):
                success, error = self.steamos_manager.set_smt_enabled(enabled)
                if not success:
                    decky.logger.warning(f"Failed to set SteamOS SMT: {error}")
                    return False
            elif os.path.exists(SMT_CONTROL_PATH):
                with open(SMT_CONTROL_PATH, "w") as f:
                    f.write("on" if enabled else "off")
            else:
                decky.logger.warning("SMT control unavailable")
                return False

            decky.logger.info(f"SMT {'enabled' if enabled else 'disabled'}")
            return True
        except PermissionError:
            decky.logger.error("Permission denied setting SMT - requires root")
            return False
        except Exception as e:
            decky.logger.error(f"Failed to set SMT: {e}")
            return False

    async def get_current_tdp(self) -> dict:
        result = {
            "tdp": 0,
            "gpu_clock": 0,
            "cpu_temp": 0,
            "gpu_temp": 0
        }
        
        try:
            # Try to read from hwmon
            hwmon_base = "/sys/class/hwmon"
            if os.path.exists(hwmon_base):
                for hwmon in os.listdir(hwmon_base):
                    hwmon_path = os.path.join(hwmon_base, hwmon)
                    name_path = os.path.join(hwmon_path, "name")
                    
                    if os.path.exists(name_path):
                        with open(name_path, 'r') as f:
                            name = f.read().strip()
                        
                        # AMD CPU/APU temps
                        if name in ["k10temp", "zenpower"]:
                            temp_path = os.path.join(hwmon_path, "temp1_input")
                            if os.path.exists(temp_path):
                                with open(temp_path, 'r') as f:
                                    result["cpu_temp"] = int(f.read().strip()) / 1000
                        
                        # AMD GPU temps
                        if name == "amdgpu":
                            for power_file in ("power1_average", "power1_input"):
                                power_path = os.path.join(hwmon_path, power_file)
                                if os.path.exists(power_path):
                                    with open(power_path, 'r') as f:
                                        result["tdp"] = round(int(f.read().strip()) / 1000000, 1)
                                    break

                            temp_path = os.path.join(hwmon_path, "temp1_input")
                            if os.path.exists(temp_path):
                                with open(temp_path, 'r') as f:
                                    result["gpu_temp"] = int(f.read().strip()) / 1000
                            
                            # GPU clock
                            freq_path = os.path.join(hwmon_path, "freq1_input")
                            if os.path.exists(freq_path):
                                with open(freq_path, 'r') as f:
                                    result["gpu_clock"] = int(f.read().strip()) / 1000000  # MHz
        
        except Exception as e:
            decky.logger.error(f"Failed to get TDP info: {e}")
        
        return result

    async def get_cpu_settings(self) -> dict:
        """Get current SMT and CPU boost settings"""
        support = self._get_current_platform_support()
        if not support.get("supported", False):
            return {
                "smt_enabled": False,
                "smt_available": False,
                "boost_enabled": False,
                "boost_available": False,
                "status": support.get("reason", "Platform is not supported"),
            }

        smt = await self.get_smt_state()
        result = {
            "smt_enabled": smt.get("enabled", False),
            "smt_available": smt.get("available", False),
            "smt_status": smt.get("status", ""),
            "smt_details": smt.get("details", ""),
            "boost_enabled": True,
            "boost_available": os.path.exists(CPU_BOOST_PATH)
        }
        
        try:
            if os.path.exists(CPU_BOOST_PATH):
                with open(CPU_BOOST_PATH, 'r') as f:
                    boost_state = f.read().strip()
                result["boost_enabled"] = boost_state == "1"
        except Exception as e:
            decky.logger.error(f"Failed to read CPU settings: {e}")
        
        return result

    async def set_cpu_boost_enabled(self, enabled: bool) -> bool:
        """Enable or disable CPU boost"""
        try:
            support = self._get_current_platform_support()
            if not support.get("supported", False):
                decky.logger.warning(support.get("reason", "Platform is not supported"))
                return False

            if not os.path.exists(CPU_BOOST_PATH):
                decky.logger.warning("CPU boost control not available")
                return False
            
            value = "1" if enabled else "0"
            with open(CPU_BOOST_PATH, 'w') as f:
                f.write(value)
            
            decky.logger.info(f"CPU boost {'enabled' if enabled else 'disabled'}")
            return True
            
        except PermissionError:
            decky.logger.error("Permission denied setting CPU boost - requires root")
            return False
        except Exception as e:
            decky.logger.error(f"Failed to set CPU boost: {e}")
            return False

    async def get_dashboard_state(self) -> dict:
        performance_modes = await self.get_performance_modes()
        cpu = await self.get_cpu_settings()
        rgb = await self.get_rgb_state()
        sync = await self.get_display_sync_state()
        fps_limit = await self.get_fps_limit_state()
        charge_limit = await self.get_charge_limit_state()

        return {
            "performance_modes": performance_modes.get("modes", []),
            "active_mode": performance_modes.get("active_mode", ""),
            "profiles_available": performance_modes.get("available", False),
            "profiles_status": performance_modes.get("status", ""),
            "cpu_boost": {
                "available": cpu.get("boost_available", False),
                "enabled": cpu.get("boost_enabled", False),
                "status": "available" if cpu.get("boost_available", False) else "CPU boost control unavailable",
                "details": (
                    "Boosts CPU clocks for heavier games"
                    if cpu.get("boost_available", False)
                    else cpu.get("status", "CPU boost control unavailable")
                ),
            },
            "smt": {
                "available": cpu.get("smt_available", False),
                "enabled": cpu.get("smt_enabled", False),
                "status": "available" if cpu.get("smt_available", False) else "SMT control unavailable",
                "details": (
                    cpu.get("smt_details")
                    if cpu.get("smt_available", False)
                    else cpu.get("smt_status", "SMT control unavailable")
                ),
            },
            "rgb": rgb,
            "vrr": sync.get("vrr", {}),
            "vsync": sync.get("vsync", {}),
            "fps_limit": fps_limit,
            "charge_limit": charge_limit,
        }

    async def get_information_state(self) -> dict:
        device = await self.get_device_info()
        battery = await self.get_battery_info()
        profiles = await self.get_performance_profiles()
        sync = await self.get_display_sync_state()
        temps = await self.get_current_tdp()
        cpu = await self.get_cpu_settings()
        rgb = await self.get_rgb_state()
        optimizations = await self.get_optimization_states()
        fps_limit = await self.get_fps_limit_state()
        charge_limit = await self.get_charge_limit_state()
        platform_supported = device.get("platform_supported", device.get("supported", False))

        hardware_controls = {
            "performance_profiles": platform_supported and profiles.get("available", False),
            "cpu_boost": platform_supported and cpu.get("boost_available", False),
            "smt": platform_supported and cpu.get("smt_available", False),
            "charge_limit": platform_supported and charge_limit.get("available", False),
            "rgb": platform_supported and rgb.get("available", False),
            "vrr": platform_supported and sync.get("vrr", {}).get("available", False),
            "vsync": platform_supported and sync.get("vsync", {}).get("available", False),
            "fps_limit": platform_supported and fps_limit.get("available", False),
            "optimizations": platform_supported and any(
                state.get("available", False)
                for state in optimizations.get("states", [])
            ),
        }

        return {
            "device": device,
            "battery": battery,
            "performance": {
                "current_profile": profiles.get("current", ""),
                "available_native": profiles.get("available_native", []),
                "status": profiles.get("status", ""),
            },
            "display": sync,
            "temperatures": {
                "tdp": temps.get("tdp", 0),
                "cpu": temps.get("cpu_temp", 0),
                "gpu": temps.get("gpu_temp", 0),
                "gpu_clock": temps.get("gpu_clock", 0),
            },
            "optimizations": optimizations.get("states", []),
            "hardware_controls": hardware_controls,
            "fps_limit": fps_limit,
        }
