# Documentation index

## Getting started

- [../README.md](../README.md) — what Ventilastation is, repo layout
- [emulator-setup.Linux.md](emulator-setup.Linux.md) /
  [emulator-setup.macOS.md](emulator-setup.macOS.md) /
  [emulator-setup.Windows.md](emulator-setup.Windows.md) — desktop emulator setup
- [developers-guide.md](developers-guide.md) — writing games
- [../BUILDING.md](../BUILDING.md) — building and flashing firmware
- [../AGENTS.md](../AGENTS.md) — contributor/agent guidance

## Design documents (current)

- [../ARCHITECTURE.md](../ARCHITECTURE.md) — web emulator architecture and
  the pointer-posting memory rule
- [../DESIGN.md](../DESIGN.md) — on-device design: flash layout, MicroPython
  + retro-go coexistence, launch flows
- [../WORKBENCH.md](../WORKBENCH.md) — the hardware test workbench
- [../OTA.md](../OTA.md) — the three-tier OTA update system
- [../DEPLOY.md](../DEPLOY.md) — publishing the web emulator
- [emulator-audio.md](emulator-audio.md) — streaming console audio
  register writes to the host synth
- [input-protocol-v2.md](input-protocol-v2.md) — the joystick/command wire
  protocol (normative spec for all parser implementations)
- [rom-format.md](rom-format.md) — the sprite ROM container format
- [native-app-handoff.md](native-app-handoff.md) — launching native apps
  from the MicroPython launcher
- [web-ide-integration.md](web-ide-integration.md) — browser IDE hooks
- [emulator.md](emulator.md) — desktop emulator notes

## Historical

Documents kept for context; they describe plans that have since shipped or
changed. Don't code against them.

- [history/game-layout-migration.md](history/game-layout-migration.md)
- [history/design-notes.md](history/design-notes.md)
