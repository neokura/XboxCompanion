import asyncio
import importlib
import os
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


class FakeLogger:
    def info(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass

    def error(self, *_args, **_kwargs):
        pass


fake_decky = types.SimpleNamespace(
    DECKY_PLUGIN_SETTINGS_DIR=tempfile.gettempdir(),
    logger=FakeLogger(),
)
sys.modules.setdefault("decky", fake_decky)
main = importlib.import_module("main")

SUPPORTED_PLATFORM = {
    "supported": True,
    "support_level": "supported",
    "reason": "Supported ASUS/Lenovo handheld on SteamOS 3.8 or newer.",
}


class SteamOsManagerClientTest(unittest.TestCase):
    def test_reads_native_performance_state(self):
        def fake_run(cmd, **_kwargs):
            prop = cmd[-1]
            if prop == "AvailablePerformanceProfiles":
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    'as 3 "low-power" "balanced" "performance"\n',
                    "",
                )
            if prop == "PerformanceProfile":
                return subprocess.CompletedProcess(cmd, 0, 's "balanced"\n', "")
            if prop == "SuggestedDefaultPerformanceProfile":
                return subprocess.CompletedProcess(cmd, 0, 's "performance"\n', "")
            return subprocess.CompletedProcess(cmd, 1, "", "unknown property")

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.SteamOsManagerClient(FakeLogger())
            state = client.get_performance_state()

        self.assertTrue(state["available"])
        self.assertEqual(state["current"], "balanced")
        self.assertEqual(state["suggested_default"], "performance")
        self.assertEqual(
            state["available_native"],
            ["low-power", "balanced", "performance"],
        )

    def test_reports_unavailable_when_dbus_fails(self):
        def fake_run(cmd, **_kwargs):
            return subprocess.CompletedProcess(cmd, 1, "", "service not found")

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.SteamOsManagerClient(FakeLogger())
            state = client.get_performance_state()

        self.assertFalse(state["available"])
        self.assertEqual(state["available_native"], [])
        self.assertIn("SteamOS native profiles unavailable", state["status"])

    def test_sets_native_performance_profile(self):
        calls = []

        def fake_run(cmd, **_kwargs):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.SteamOsManagerClient(FakeLogger())
            success, error = client.set_performance_profile("low-power")

        self.assertTrue(success)
        self.assertEqual(error, "")
        self.assertIn("set-property", calls[0])
        self.assertEqual(calls[0][-1], "low-power")

    def test_reads_steamos_charge_limit_state(self):
        def fake_run(cmd, **_kwargs):
            if "get-property" in cmd and cmd[-1] == "ChargeLimit":
                return subprocess.CompletedProcess(cmd, 0, "u 80\n", "")
            return subprocess.CompletedProcess(cmd, 1, "", "unknown property")

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.SteamOsManagerClient(FakeLogger())
            state = client.get_charge_limit_state()

        self.assertTrue(state["available"])
        self.assertTrue(state["enabled"])
        self.assertEqual(state["limit"], 80)

    def test_sets_steamos_charge_limit_to_80_or_100(self):
        calls = []

        def fake_run(cmd, **_kwargs):
            calls.append(cmd)
            if "get-property" in cmd and cmd[-1] == "ChargeLimit":
                return subprocess.CompletedProcess(cmd, 0, "u 100\n", "")
            if "set-property" in cmd:
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return subprocess.CompletedProcess(cmd, 1, "", "unknown property")

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.SteamOsManagerClient(FakeLogger())
            enabled, enabled_error = client.set_charge_limit_enabled(True)
            disabled, disabled_error = client.set_charge_limit_enabled(False)

        self.assertTrue(enabled)
        self.assertEqual(enabled_error, "")
        self.assertTrue(disabled)
        self.assertEqual(disabled_error, "")
        set_calls = [call for call in calls if "set-property" in call]
        self.assertEqual(set_calls[0][-1], "80")
        self.assertEqual(set_calls[1][-1], "100")

    def test_reads_steamos_smt_state(self):
        def fake_run(cmd, **_kwargs):
            if "get-property" in cmd and cmd[-1] == "SMT":
                return subprocess.CompletedProcess(cmd, 0, "b true\n", "")
            return subprocess.CompletedProcess(cmd, 1, "", "unknown property")

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.SteamOsManagerClient(FakeLogger())
            state = client.get_smt_state()

        self.assertTrue(state["available"])
        self.assertTrue(state["enabled"])

    def test_sets_steamos_smt_state(self):
        calls = []

        def fake_run(cmd, **_kwargs):
            calls.append(cmd)
            if "get-property" in cmd and cmd[-1] == "SMT":
                return subprocess.CompletedProcess(cmd, 0, "b true\n", "")
            if "set-property" in cmd:
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return subprocess.CompletedProcess(cmd, 1, "", "unknown property")

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.SteamOsManagerClient(FakeLogger())
            enabled, enabled_error = client.set_smt_enabled(True)
            disabled, disabled_error = client.set_smt_enabled(False)

        self.assertTrue(enabled)
        self.assertEqual(enabled_error, "")
        self.assertTrue(disabled)
        self.assertEqual(disabled_error, "")
        set_calls = [call for call in calls if "set-property" in call]
        self.assertEqual(set_calls[0][-1], "true")
        self.assertEqual(set_calls[1][-1], "false")


class GamescopeSettingsClientTest(unittest.TestCase):
    def test_reads_gamescope_display_sync_state(self):
        outputs = {
            main.GAMESCOPE_VRR_CAPABLE_ATOM: "GAMESCOPE_VRR_CAPABLE(CARDINAL) = 1\n",
            main.GAMESCOPE_VRR_ENABLED_ATOM: "GAMESCOPE_VRR_ENABLED(CARDINAL) = 1\n",
            main.GAMESCOPE_VRR_FEEDBACK_ATOM: "GAMESCOPE_VRR_FEEDBACK(CARDINAL) = 0\n",
            main.GAMESCOPE_ALLOW_TEARING_ATOM: "GAMESCOPE_ALLOW_TEARING(CARDINAL) = 0\n",
        }

        def fake_run(cmd, **_kwargs):
            return subprocess.CompletedProcess(cmd, 0, outputs[cmd[-1]], "")

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.GamescopeSettingsClient(FakeLogger(), display=":0")
            state = client.get_display_sync_state()

        self.assertTrue(state["vrr"]["available"])
        self.assertTrue(state["vrr"]["enabled"])
        self.assertFalse(state["vrr"]["active"])
        self.assertTrue(state["vsync"]["available"])
        self.assertTrue(state["vsync"]["enabled"])
        self.assertFalse(state["vsync"]["allow_tearing"])

    def test_sets_vsync_as_inverse_allow_tearing(self):
        calls = []

        def fake_run(cmd, **_kwargs):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.GamescopeSettingsClient(FakeLogger(), display=":0")
            enabled, enabled_error = client.set_vsync_enabled(True)
            disabled, disabled_error = client.set_vsync_enabled(False)

        self.assertTrue(enabled)
        self.assertEqual(enabled_error, "")
        self.assertTrue(disabled)
        self.assertEqual(disabled_error, "")
        self.assertEqual(calls[0][-2], main.GAMESCOPE_ALLOW_TEARING_ATOM)
        self.assertEqual(calls[0][-1], "0")
        self.assertEqual(calls[1][-2], main.GAMESCOPE_ALLOW_TEARING_ATOM)
        self.assertEqual(calls[1][-1], "1")

    def test_rejects_vrr_when_display_is_not_capable(self):
        def fake_run(cmd, **_kwargs):
            return subprocess.CompletedProcess(
                cmd,
                0,
                "GAMESCOPE_VRR_CAPABLE(CARDINAL) = 0\n",
                "",
            )

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.GamescopeSettingsClient(FakeLogger(), display=":0")
            success, error = client.set_vrr_enabled(True)

        self.assertFalse(success)
        self.assertIn("not VRR capable", error)

    def test_falls_back_to_secondary_display_when_primary_is_unavailable(self):
        outputs = {
            main.GAMESCOPE_VRR_CAPABLE_ATOM: "GAMESCOPE_VRR_CAPABLE(CARDINAL) = 1\n",
            main.GAMESCOPE_VRR_ENABLED_ATOM: "GAMESCOPE_VRR_ENABLED(CARDINAL) = 0\n",
            main.GAMESCOPE_VRR_FEEDBACK_ATOM: "GAMESCOPE_VRR_FEEDBACK(CARDINAL) = 0\n",
            main.GAMESCOPE_ALLOW_TEARING_ATOM: "GAMESCOPE_ALLOW_TEARING(CARDINAL) = 0\n",
        }

        def fake_run(cmd, **kwargs):
            display = kwargs.get("env", {}).get("DISPLAY")
            if display == ":0":
                return subprocess.CompletedProcess(cmd, 1, "", "unable to open display :0")
            return subprocess.CompletedProcess(cmd, 0, outputs[cmd[-1]], "")

        with patch("main.subprocess.run", side_effect=fake_run):
            client = main.GamescopeSettingsClient(FakeLogger(), display=":0")
            state = client.get_display_sync_state()

        self.assertEqual(state["display"], ":1")
        self.assertTrue(state["vrr"]["available"])


class PluginPerformanceProfileTest(unittest.TestCase):
    def test_device_metadata_uses_uniform_handheld_support(self):
        plugin = main.Plugin()

        first = plugin._get_device_metadata("BOARD-A", "Generic Handheld A", "ASUS")
        second = plugin._get_device_metadata("BOARD-B", "Generic Handheld B", "LENOVO")

        self.assertEqual(first["device_family"], "steamos_handheld")
        self.assertEqual(first["support_level"], "supported")
        self.assertEqual(second["device_family"], "steamos_handheld")
        self.assertEqual(second["support_level"], "supported")

    def test_platform_support_allows_asus_and_lenovo_on_steamos_38_or_newer(self):
        plugin = main.Plugin()
        asus = plugin._get_platform_support(
            "RC7A",
            "ASUS Handheld",
            "ASUS",
            "",
            {
                "ID": "steamos",
                "VERSION_ID": "3.8.0",
                "PRETTY_NAME": "SteamOS 3.8",
            },
        )
        lenovo_future = plugin._get_platform_support(
            "BOARD-B",
            "Lenovo Handheld",
            "LENOVO",
            "Legion",
            {
                "ID": "steamos",
                "VERSION_ID": "3.9.1",
                "PRETTY_NAME": "SteamOS 3.9.1",
            },
        )

        self.assertTrue(asus["supported"])
        self.assertEqual(asus["support_level"], "supported")
        self.assertTrue(lenovo_future["supported"])

    def test_platform_support_blocks_steam_deck(self):
        plugin = main.Plugin()
        support = plugin._get_platform_support(
            "Jupiter",
            "Steam Deck",
            "Valve",
            "",
            {
                "ID": "steamos",
                "VERSION_ID": "3.8.0",
                "PRETTY_NAME": "SteamOS 3.8",
            },
        )

        self.assertFalse(support["supported"])
        self.assertEqual(support["support_level"], "blocked")
        self.assertIn("Steam Deck", support["reason"])

    def test_platform_support_blocks_non_steamos_distributions(self):
        plugin = main.Plugin()

        bazzite = plugin._get_platform_support(
            "BOARD-A",
            "Generic Handheld",
            "ASUS",
            "",
            {"ID": "bazzite", "VERSION_ID": "42", "PRETTY_NAME": "Bazzite"},
        )
        chimera = plugin._get_platform_support(
            "BOARD-A",
            "Generic Handheld",
            "ASUS",
            "",
            {"ID": "chimeraos", "VERSION_ID": "48", "PRETTY_NAME": "ChimeraOS"},
        )

        self.assertFalse(bazzite["supported"])
        self.assertFalse(chimera["supported"])

    def test_platform_support_blocks_other_steamos_versions(self):
        plugin = main.Plugin()
        support = plugin._get_platform_support(
            "BOARD-A",
            "ASUS Handheld",
            "ASUS",
            "",
            {
                "ID": "steamos",
                "VERSION_ID": "3.7.0",
                "PRETTY_NAME": "SteamOS 3.7",
            },
        )

        self.assertFalse(support["supported"])

    def test_platform_support_blocks_non_asus_lenovo_handhelds(self):
        plugin = main.Plugin()
        support = plugin._get_platform_support(
            "BOARD-A",
            "Generic Handheld",
            "VENDOR-A",
            "",
            {
                "ID": "steamos",
                "VERSION_ID": "3.9.0",
                "PRETTY_NAME": "SteamOS 3.9",
            },
        )

        self.assertFalse(support["supported"])
        self.assertIn("ASUS and Lenovo", support["reason"])

    def test_plugin_instances_do_not_share_settings(self):
        first = main.Plugin()
        second = main.Plugin()

        first.settings["example"] = "value"

        self.assertNotIn("example", second.settings)

    def test_plugin_rejects_unknown_profile(self):
        plugin = main.Plugin()
        plugin.steamos_manager = object()
        result = asyncio.run(plugin.set_performance_profile("turbo"))
        self.assertFalse(result)

    def test_plugin_rejects_unknown_display_sync_setting(self):
        plugin = main.Plugin()
        result = asyncio.run(plugin.set_display_sync_setting("hdr", True))
        self.assertFalse(result)

    def test_plugin_uses_steamos_manager_without_manual_tdp(self):
        class FakeSteamOsManager:
            def __init__(self):
                self.set_calls = []

            def get_performance_state(self):
                return {
                    "available": True,
                    "available_native": ["low-power", "balanced", "performance"],
                    "current": "performance",
                    "suggested_default": "performance",
                    "status": "available",
                }

            def set_performance_profile(self, profile_id):
                self.set_calls.append(profile_id)
                return True, ""

        async def fail_if_called(_tdp):
            raise AssertionError("manual TDP fallback should not be used")

        with tempfile.TemporaryDirectory() as tmpdir:
            plugin = main.Plugin()
            plugin.settings_path = os.path.join(tmpdir, "settings.json")
            plugin.settings = {}
            plugin.steamos_manager = FakeSteamOsManager()
            plugin.set_tdp = fail_if_called

            with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM):
                result = asyncio.run(plugin.set_performance_profile("balanced"))

        self.assertTrue(result)
        self.assertNotIn("current_profile", plugin.settings)
        self.assertEqual(plugin.steamos_manager.set_calls, ["balanced"])

    def test_load_settings_does_not_create_default_settings_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin = main.Plugin()
            plugin.settings_path = os.path.join(tmpdir, "settings.json")

            settings = asyncio.run(plugin.load_settings())

            self.assertEqual(settings, {})
            self.assertFalse(os.path.exists(plugin.settings_path))

    def test_performance_modes_surface_native_steamos_modes(self):
        plugin = main.Plugin()

        with patch.object(
            plugin,
            "get_performance_profiles",
            return_value={
                "profiles": {
                    "low-power": {"available": True},
                    "balanced": {"available": True},
                    "performance": {"available": True},
                },
                "current": "balanced",
                "available": True,
                "status": "available",
            },
        ):
            state = asyncio.run(plugin.get_performance_modes())

        self.assertEqual(state["active_mode"], "balanced")
        self.assertEqual(len(state["modes"]), 3)
        self.assertEqual(
            [mode["id"] for mode in state["modes"]],
            ["low-power", "balanced", "performance"],
        )

    def test_dashboard_state_contains_cpu_sync_and_fps(self):
        plugin = main.Plugin()

        with patch.object(
            plugin,
            "get_performance_modes",
            return_value={
                "modes": [{"id": "performance", "label": "Performance", "available": True, "active": True}],
                "active_mode": "performance",
                "available": True,
                "status": "available",
            },
        ), patch.object(
            plugin,
            "get_cpu_settings",
            return_value={
                "boost_available": True,
                "boost_enabled": True,
                "smt_available": True,
                "smt_enabled": False,
                "smt_details": "smt",
            },
        ), patch.object(
            plugin,
            "get_display_sync_state",
            return_value={
                "vrr": {"available": True, "enabled": True, "details": "VRR"},
                "vsync": {"available": True, "enabled": False, "details": "VSync"},
            },
        ), patch.object(
            plugin,
            "get_fps_limit_state",
            return_value={"available": True, "current": 40, "details": "fps", "status": "available"},
        ):
            state = asyncio.run(plugin.get_dashboard_state())

        self.assertEqual(state["active_mode"], "performance")
        self.assertTrue(state["cpu_boost"]["enabled"])
        self.assertTrue(state["smt"]["available"])
        self.assertFalse(state["smt"]["enabled"])
        self.assertEqual(state["fps_limit"]["current"], 40)

    def test_fps_presets_use_native_modes_without_high_refresh_by_default(self):
        plugin = main.Plugin()
        plugin.settings = {"fps_limit": 0}

        with patch.object(plugin, "_get_supported_high_refresh_rates", return_value=[]):
            presets = plugin._get_fps_presets()

        self.assertEqual(presets, [30, 40, 60, 0])

    def test_fps_presets_include_supported_high_refresh_modes(self):
        plugin = main.Plugin()
        plugin.settings = {"fps_limit": 0}

        with patch.object(plugin, "_get_supported_high_refresh_rates", return_value=[90, 120, 144]):
            presets = plugin._get_fps_presets()

        self.assertEqual(presets, [30, 40, 60, 90, 120, 144, 0])

    def test_supported_high_refresh_rates_are_read_from_xrandr(self):
        plugin = main.Plugin()
        output = """
Screen 0: minimum 16 x 16, current 1920 x 1080, maximum 32767 x 32767
eDP-1 connected primary 1920x1080+0+0
   1920x1080     143.86*+ 120.00 90.00 60.00
   1280x720      165.00 75.00 59.94
"""

        with patch.object(plugin, "_command_exists", return_value=True), patch.object(
            plugin,
            "_run_command_output",
            return_value=(True, output),
        ):
            rates = plugin._get_supported_high_refresh_rates()

        self.assertEqual(rates, [90, 120, 144, 165])

    def test_fps_limit_rejects_values_outside_supported_presets(self):
        plugin = main.Plugin()
        plugin.settings = {"fps_limit": 0}

        with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM), patch.object(
            plugin,
            "_command_exists",
            return_value=True,
        ), patch.object(plugin, "_get_fps_presets", return_value=[30, 40, 60, 0]):
            result = asyncio.run(plugin.set_fps_limit(45))

        self.assertFalse(result)

    def test_charge_limit_returns_false_when_control_is_unavailable(self):
        plugin = main.Plugin()

        device = {"supported": True}

        with patch.object(plugin, "get_device_info", return_value=device), patch.object(
            plugin,
            "get_cpu_settings",
            return_value={"boost_available": False, "smt_available": False},
        ), patch.object(
            plugin,
            "get_rgb_state",
            return_value={"available": True},
        ), patch.object(
            plugin,
            "get_performance_profiles",
            return_value={"current": "", "available_native": [], "status": ""},
        ), patch.object(
            plugin,
            "get_display_sync_state",
            return_value={"vrr": {}, "vsync": {}},
        ), patch.object(
            plugin,
            "get_current_tdp",
            return_value={"cpu_temp": 0, "gpu_temp": 0, "gpu_clock": 0},
        ), patch.object(
            plugin,
            "get_optimization_states",
            return_value={"states": []},
        ), patch.object(
            plugin,
            "get_fps_limit_state",
            return_value={"available": False, "current": 0},
        ), patch.object(
            plugin,
            "get_charge_limit_state",
            return_value={"available": False, "enabled": False, "limit": 100},
        ), patch("main.os.path.exists", side_effect=lambda path: path == main.ALLY_LED_PATH), patch(
            "main.glob.glob",
            return_value=[],
        ):
            state = asyncio.run(plugin.get_information_state())

        self.assertFalse(state["hardware_controls"]["charge_limit"])
        self.assertTrue(state["hardware_controls"]["rgb"])

    def test_charge_limit_uses_steamos_manager_state(self):
        plugin = main.Plugin()
        plugin.steamos_manager = types.SimpleNamespace(
            get_charge_limit_state=lambda: {
                "available": True,
                "enabled": True,
                "limit": 80,
                "status": "available",
                "details": "charge",
            }
        )

        with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM):
            state = asyncio.run(plugin.get_charge_limit_state())

        self.assertTrue(state["available"])
        self.assertTrue(state["enabled"])
        self.assertEqual(state["limit"], 80)

    def test_rgb_state_is_exposed_in_dashboard(self):
        plugin = main.Plugin()
        plugin.settings = {"rgb_enabled": True, "rgb_color": "#00B7FF", "fps_limit": 0}

        with patch.object(
            plugin,
            "get_performance_modes",
            return_value={
                "modes": [],
                "active_mode": "",
                "available": True,
                "status": "available",
            },
        ), patch.object(
            plugin,
            "get_cpu_settings",
            return_value={"boost_available": True, "boost_enabled": True},
        ), patch.object(
            plugin,
            "get_display_sync_state",
            return_value={
                "vrr": {"available": False, "enabled": False, "details": "vrr"},
                "vsync": {"available": True, "enabled": True, "details": "vsync"},
            },
        ), patch.object(
            plugin,
            "get_fps_limit_state",
            return_value={"available": False, "current": 0, "details": "fps", "status": "unavailable"},
        ), patch.object(
            plugin,
            "get_rgb_state",
            return_value={
                "available": True,
                "enabled": True,
                "color": "#00B7FF",
                "presets": main.RGB_COLOR_PRESETS,
                "details": "rgb",
            },
        ):
            state = asyncio.run(plugin.get_dashboard_state())

        self.assertTrue(state["rgb"]["available"])
        self.assertEqual(state["rgb"]["color"], "#00B7FF")


class OptimizationStateTest(unittest.TestCase):
    def test_grub_healer_script_does_not_lock_cpu_boost(self):
        self.assertNotIn("cpufreq/boost", main.GRUB_HEALER_SCRIPT_CONTENT)
        self.assertNotIn("echo 0", main.GRUB_HEALER_SCRIPT_CONTENT)

    def test_memory_state_reports_configured_and_active(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sysctl_path = os.path.join(tmpdir, "memory.conf")
            thp_config_path = os.path.join(tmpdir, "thp.conf")
            atomic_path = os.path.join(tmpdir, "atomic.conf")
            thp_enabled_path = os.path.join(tmpdir, "thp_enabled")

            with open(sysctl_path, "w") as f:
                f.write(main.MEMORY_SYSCTL_CONTENT)
            with open(thp_config_path, "w") as f:
                f.write(main.THP_TMPFILES_CONTENT)
            with open(atomic_path, "w") as f:
                f.write(f"{sysctl_path}\n{thp_config_path}\n")
            with open(thp_enabled_path, "w") as f:
                f.write("always [madvise] never")

            plugin = main.Plugin()

            def fake_read_sysctl(key):
                return {
                    "vm.swappiness": "10",
                    "vm.min_free_kbytes": "524288",
                    "vm.dirty_ratio": "5",
                }.get(key, "")

            with patch("main.MEMORY_SYSCTL_PATH", sysctl_path), patch(
                "main.THP_TMPFILES_PATH", thp_config_path
            ), patch("main.ATOMIC_MANIFEST_PATH", atomic_path), patch(
                "main.THP_ENABLED_PATH", thp_enabled_path
            ), patch.object(plugin, "_read_sysctl", side_effect=fake_read_sysctl), patch.object(
                plugin, "_command_exists", return_value=True
            ):
                state = plugin._get_memory_state()

        self.assertTrue(state["enabled"])
        self.assertTrue(state["active"])
        self.assertFalse(state["needs_reboot"])
        self.assertEqual(state["status"], "active")
        self.assertIn("Transparent Huge Pages", state["description"])

    def test_atomic_manifest_is_single_file_and_cleans_legacy_manifests(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scx_path = os.path.join(tmpdir, "scx")
            memory_path = os.path.join(tmpdir, "memory.conf")
            thp_path = os.path.join(tmpdir, "thp.conf")
            manifest_path = os.path.join(tmpdir, "xbox-companion.conf")
            legacy_paths = [
                os.path.join(tmpdir, "xbox-companion-scx.conf"),
                os.path.join(tmpdir, "xbox-companion-memory.conf"),
            ]

            with open(scx_path, "w") as f:
                f.write(main.SCX_DEFAULT_CONTENT)
            with open(memory_path, "w") as f:
                f.write(main.MEMORY_SYSCTL_CONTENT)
            with open(thp_path, "w") as f:
                f.write(main.THP_TMPFILES_CONTENT)
            for path in legacy_paths:
                with open(path, "w") as f:
                    f.write("legacy\n")

            plugin = main.Plugin()

            with patch("main.SCX_DEFAULT_PATH", scx_path), patch(
                "main.MEMORY_SYSCTL_PATH", memory_path
            ), patch("main.THP_TMPFILES_PATH", thp_path), patch(
                "main.NPU_BLACKLIST_PATH", os.path.join(tmpdir, "npu.conf")
            ), patch(
                "main.USB_WAKE_SERVICE_PATH", os.path.join(tmpdir, "usb.service")
            ), patch(
                "main.GRUB_HEALER_SCRIPT_PATH", os.path.join(tmpdir, "grub.sh")
            ), patch(
                "main.GRUB_HEALER_SERVICE_PATH", os.path.join(tmpdir, "grub.service")
            ), patch(
                "main.ATOMIC_MANIFEST_PATH", manifest_path
            ), patch(
                "main.LEGACY_ATOMIC_PATHS", legacy_paths
            ):
                plugin._refresh_atomic_manifest()

            with open(manifest_path, "r") as f:
                manifest = f.read()
            legacy_removed = not any(os.path.exists(path) for path in legacy_paths)

        self.assertIn(scx_path, manifest)
        self.assertIn(memory_path, manifest)
        self.assertIn(thp_path, manifest)
        self.assertNotIn("xbox-companion-scx.conf", manifest)
        self.assertTrue(legacy_removed)

    def test_disabling_optimization_removes_only_its_atomic_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scx_path = os.path.join(tmpdir, "scx")
            memory_path = os.path.join(tmpdir, "memory.conf")
            thp_path = os.path.join(tmpdir, "thp.conf")
            manifest_path = os.path.join(tmpdir, "xbox-companion.conf")

            with open(scx_path, "w") as f:
                f.write(main.SCX_DEFAULT_CONTENT)
            with open(memory_path, "w") as f:
                f.write(main.MEMORY_SYSCTL_CONTENT)
            with open(thp_path, "w") as f:
                f.write(main.THP_TMPFILES_CONTENT)

            plugin = main.Plugin()

            with patch("main.SCX_DEFAULT_PATH", scx_path), patch(
                "main.MEMORY_SYSCTL_PATH", memory_path
            ), patch("main.THP_TMPFILES_PATH", thp_path), patch(
                "main.NPU_BLACKLIST_PATH", os.path.join(tmpdir, "npu.conf")
            ), patch(
                "main.USB_WAKE_SERVICE_PATH", os.path.join(tmpdir, "usb.service")
            ), patch(
                "main.GRUB_HEALER_SCRIPT_PATH", os.path.join(tmpdir, "grub.sh")
            ), patch(
                "main.GRUB_HEALER_SERVICE_PATH", os.path.join(tmpdir, "grub.service")
            ), patch(
                "main.ATOMIC_MANIFEST_PATH", manifest_path
            ), patch(
                "main.LEGACY_ATOMIC_PATHS", []
            ), patch.object(
                plugin, "_run_optional_command", return_value=""
            ):
                plugin._refresh_atomic_manifest()
                plugin._set_memory_enabled(False)

                with open(manifest_path, "r") as f:
                    manifest = f.read()
                memory_exists = os.path.exists(memory_path)
                thp_exists = os.path.exists(thp_path)

        self.assertIn(scx_path, manifest)
        self.assertNotIn(memory_path, manifest)
        self.assertNotIn(thp_path, manifest)
        self.assertFalse(memory_exists)
        self.assertFalse(thp_exists)

    def test_atomic_manifest_is_removed_when_last_optimization_is_disabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_path = os.path.join(tmpdir, "memory.conf")
            thp_path = os.path.join(tmpdir, "thp.conf")
            manifest_path = os.path.join(tmpdir, "xbox-companion.conf")

            with open(memory_path, "w") as f:
                f.write(main.MEMORY_SYSCTL_CONTENT)
            with open(thp_path, "w") as f:
                f.write(main.THP_TMPFILES_CONTENT)

            plugin = main.Plugin()

            with patch("main.SCX_DEFAULT_PATH", os.path.join(tmpdir, "scx")), patch(
                "main.MEMORY_SYSCTL_PATH", memory_path
            ), patch("main.THP_TMPFILES_PATH", thp_path), patch(
                "main.NPU_BLACKLIST_PATH", os.path.join(tmpdir, "npu.conf")
            ), patch(
                "main.USB_WAKE_SERVICE_PATH", os.path.join(tmpdir, "usb.service")
            ), patch(
                "main.GRUB_HEALER_SCRIPT_PATH", os.path.join(tmpdir, "grub.sh")
            ), patch(
                "main.GRUB_HEALER_SERVICE_PATH", os.path.join(tmpdir, "grub.service")
            ), patch(
                "main.ATOMIC_MANIFEST_PATH", manifest_path
            ), patch(
                "main.LEGACY_ATOMIC_PATHS", []
            ), patch.object(
                plugin, "_run_optional_command", return_value=""
            ):
                plugin._refresh_atomic_manifest()
                plugin._set_memory_enabled(False)
                manifest_exists = os.path.exists(manifest_path)

        self.assertFalse(manifest_exists)

    def test_memory_state_reports_reboot_required_when_runtime_tuning_remains_after_disable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_path = os.path.join(tmpdir, "memory.conf")
            thp_path = os.path.join(tmpdir, "thp.conf")
            manifest_path = os.path.join(tmpdir, "xbox-companion.conf")
            thp_enabled_path = os.path.join(tmpdir, "thp_enabled")

            with open(thp_enabled_path, "w") as f:
                f.write("always [madvise] never")

            plugin = main.Plugin()

            def fake_read_sysctl(key):
                return {
                    "vm.swappiness": "10",
                    "vm.min_free_kbytes": "524288",
                    "vm.dirty_ratio": "5",
                }.get(key, "")

            with patch("main.MEMORY_SYSCTL_PATH", memory_path), patch(
                "main.THP_TMPFILES_PATH", thp_path
            ), patch("main.ATOMIC_MANIFEST_PATH", manifest_path), patch(
                "main.THP_ENABLED_PATH", thp_enabled_path
            ), patch.object(plugin, "_read_sysctl", side_effect=fake_read_sysctl), patch.object(
                plugin, "_command_exists", return_value=True
            ):
                state = plugin._get_memory_state()

        self.assertFalse(state["enabled"])
        self.assertTrue(state["active"])
        self.assertTrue(state["needs_reboot"])
        self.assertEqual(state["status"], "reboot-required")

    def test_unknown_optimization_is_rejected(self):
        plugin = main.Plugin()
        result = asyncio.run(plugin.set_optimization_enabled("unknown", True))
        self.assertFalse(result)

    def test_power_optimization_is_gated_on_non_amd_platform(self):
        plugin = main.Plugin()

        with patch.object(plugin, "_command_exists", return_value=True), patch.object(
            plugin,
            "_is_amd_platform",
            return_value=False,
        ):
            state = plugin._get_power_state()

        self.assertFalse(state["available"])

    def test_optimization_toggle_verifies_resulting_state(self):
        plugin = main.Plugin()

        with patch.object(plugin, "_set_memory_enabled", return_value=None), patch.object(
            plugin,
            "_get_memory_state",
            return_value={"enabled": False},
        ):
            result = asyncio.run(plugin.set_optimization_enabled("memory", True))

        self.assertFalse(result)

    def test_optimization_disable_rejects_when_runtime_is_still_active(self):
        plugin = main.Plugin()

        with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM), patch.object(
            plugin, "_set_memory_enabled", return_value=None
        ), patch.object(
            plugin,
            "_get_memory_state",
            return_value={"enabled": False, "active": True},
        ):
            result = asyncio.run(plugin.set_optimization_enabled("memory", False))

        self.assertFalse(result)

    def test_optimization_disable_accepts_only_clean_rollback(self):
        plugin = main.Plugin()

        with patch.object(plugin, "_get_current_platform_support", return_value=SUPPORTED_PLATFORM), patch.object(
            plugin, "_set_memory_enabled", return_value=None
        ), patch.object(
            plugin,
            "_get_memory_state",
            return_value={"enabled": False, "active": False},
        ):
            result = asyncio.run(plugin.set_optimization_enabled("memory", False))

        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
