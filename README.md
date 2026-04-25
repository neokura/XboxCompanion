# Xbox Companion

Xbox Companion is an early alpha Decky Loader plugin for current and future ASUS/Lenovo handhelds running SteamOS 3.8 or newer. It focuses on SteamOS-native controls first, with hardware-specific features enabled only when the running device exposes the required system interfaces.

This repository starts at `0.1.1`.

## Status

Xbox Companion is experimental software for ASUS/Lenovo SteamOS handhelds. It is intended for testing on devices that expose SteamOS Manager, gamescope, and compatible Linux hardware controls.

Use it only if you are comfortable with Decky plugins that run with root permissions. System optimizations are optional and visible in the UI before they are enabled.

## Supported Platform

Xbox Companion uses the same behavior across supported handheld consoles instead of maintaining per-model support tiers. It is enabled only when runtime checks detect:

- SteamOS 3.8 or newer
- ASUS or Lenovo handheld hardware
- Non-Steam Deck hardware
- Required system interfaces for each individual feature

Steam Deck is intentionally blocked to avoid interfering with Valve hardware defaults. Other distributions such as Bazzite and ChimeraOS are also blocked because the system optimizations and SteamOS assumptions are tuned for SteamOS on ASUS/Lenovo handhelds.

## Features

- SteamOS native performance profiles through SteamOS Manager over DBus.
- SteamOS performance profiles mapped directly to `low-power`, `balanced`, and `performance`.
- VRR and V-Sync controls through gamescope root properties when available.
- Live FPS limit control through `gamescopectl` when installed.
- CPU boost control when the kernel exposes it.
- Battery diagnostics and charge limit discovery when supported by the device.
- RGB control for compatible handheld LED sysfs paths.
- Device, BIOS, kernel, CPU, GPU, memory, temperature, and display diagnostics.
- Optional system optimizations for scheduler, memory, power, and AMD kernel parameters.

## Requirements

- SteamOS 3.8 or newer.
- Decky Loader 3.2 or newer.
- SteamOS Manager DBus service for native performance profile control.
- `xprop` for gamescope display sync controls.
- `gamescopectl` for live FPS limit control.
- Root plugin permission, declared through `_root` in `plugin.json`.

Features are gated at runtime. Unsupported platforms, missing tools, or missing hardware interfaces should result in disabled controls rather than hard failures.

## Install

Open Konsole on SteamOS and run:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/neokura/XboxCompanion/main/install.sh)
```

The installer checks that Decky Loader is installed before touching the plugin directory. If Decky is missing, it offers to open <https://decky.xyz/> so you can install Decky first, then rerun the command.

The installer downloads the latest GitHub release zip, extracts it to `$HOME/homebrew/plugins/Xbox Companion`, and restarts Decky Loader when possible. The plugin should then appear in the Decky quick access menu.

## Development

Install dependencies:

```bash
pnpm install
```

Run checks:

```bash
pnpm run typecheck
pnpm test
pnpm run build
```

Build output is written to `dist/`.

## Release

GitHub Actions runs on pull requests, pushes to `main`, manual dispatches, and version tags. The workflow installs dependencies, runs type checks, runs Python unit tests, builds the frontend, and uploads a downloadable release zip as a workflow artifact.

When a tag named `v*` is pushed, the same zip is also attached to the GitHub Release.

The release package contains:

- `dist/`
- `main.py`
- `plugin.json`
- `package.json`
- `README.md`
- `LICENSE`
- `icons/`

To create a tagged release:

```bash
git tag v0.1.1
git push origin v0.1.1
```

## Safety

Xbox Companion avoids direct manual TDP writes and prefers SteamOS-native APIs. Optional system optimizations write managed files under known paths, register them through one consolidated atomic manifest at `/etc/atomic-update.conf.d/xbox-companion.conf`, and report their active/configured state in the UI.

AMD-specific optimization toggles are gated to AMD platforms. Device-specific controls are discovered dynamically and remain unavailable when the current handheld does not expose the expected Linux interfaces. Steam Deck, Bazzite, ChimeraOS, non-SteamOS environments, and non-ASUS/Lenovo hardware are blocked before system-level controls are exposed.

## Thanks

Xbox Companion builds on ideas, tooling, and platform work from the wider handheld Linux community. Thanks especially to:

- [Ally Center](https://github.com/PixelAddictUnlocked/allycenter) by PixelAddictUnlocked for inspiration around handheld control-center workflows.
- [Decky Loader](https://decky.xyz/) and the Decky plugin ecosystem.
- SteamOS and the SteamOS Manager interfaces that make native system control possible.
- The Steam Deck, ASUS ROG Ally, Lenovo Legion Go, and broader SteamOS handheld communities for documentation, testing, and shared discoveries.

## License

MIT. See [LICENSE](LICENSE).
