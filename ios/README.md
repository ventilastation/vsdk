# Ventilastation iOS

This is a self-contained, native SwiftUI implementation of the Ventilastation
experience. It does not embed or load the browser emulator. The LED display,
game library, input handling, animation loop, and built-in games are all native
Swift code and have no third-party dependencies.

## Run

1. From the `vsdk` checkout, publish the emulator runtime payloads:

   ```sh
   tools/update-ios-runtime.sh
   ```

2. Install the full Xcode app (Command Line Tools alone do not include iOS
   Simulator), then select it with:

   ```sh
   sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
   ```

3. Open `ios/VentilastationEmulator.xcodeproj` in Xcode.
4. Choose an iPhone simulator with iOS 16 or later and press Run.

The initial game library includes three native LED-ring modes: Orbit Defender,
Pulse Runner, and Prism Shift. Choose a game and press A (or C) to start; the
D-pad moves the player, A/C score a pulse, B returns to the library, and D
restarts the current game.
