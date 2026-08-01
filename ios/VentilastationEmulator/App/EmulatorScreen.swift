import SwiftUI

struct EmulatorScreen: View {
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var emulator = VentilastationEngine()
    @StateObject private var runtimeFilesystem = RuntimeFilesystem()
    @StateObject private var frameStore = NativeFrameStore()
    @StateObject private var input = NativeInputController()
    @State private var microPython = NativeMicroPythonRuntime()
    @State private var microPythonStatus = "WAITING FOR RUNTIME FILES"

    var body: some View {
        GeometryReader { proxy in
            // The display is the primary surface: use the complete phone
            // width, with no side gutters.  Its square frame still leaves
            // ample room for the controls below on a portrait iPhone.
            let displayWidth = proxy.size.width

            VStack(spacing: 4) {
                ZStack(alignment: .topTrailing) {
                    NativeMetalRingView(frameStore: frameStore)
                        .frame(width: displayWidth, height: displayWidth)
                        // The original Ventilastation ring is mounted with its
                        // zero-angle LED at the opposite side from the phone's
                        // portrait coordinate system.  Rotate only the display;
                        // the native controls remain upright.
                        .rotationEffect(.degrees(180))

                    Button {
                        // This is a soft exit: it asks the running MicroPython
                        // director to return to its launcher scene. It does not
                        // terminate the VM or erase the installed runtime.
                        emulator.reset()
                        input.clearHeldInput()
                        input.exitRequested = true
                    } label: {
                        Image(systemName: "arrow.uturn.backward")
                            .font(.title3.weight(.bold))
                            .frame(width: 56, height: 56)
                            .background(Color.black.opacity(0.72), in: Circle())
                            .overlay(Circle().stroke(Color.white.opacity(0.18), lineWidth: 1))
                    }
                    .padding(12)
                    .accessibilityLabel("Return to launcher")
                    .accessibilityHint("Stops the current game and returns to the MicroPython launcher")
                }
                .frame(width: displayWidth, height: displayWidth)

                EmulatorControls(engine: emulator, input: input)
                    .padding(.horizontal, 6)
                    // The full-width ring consumes the upper game area; lift
                    // the controls into the remaining visible portion so the
                    // larger D-pad and the lower A/D buttons are not clipped.
                    .offset(y: -80)
            }
            .padding(.top, 0)
            .padding(.bottom, 8)
            .frame(width: proxy.size.width, height: proxy.size.height, alignment: .top)
            .background(Color.black.ignoresSafeArea())
            .foregroundStyle(.white)
        }
        .onAppear {
            input.onChange = { [weak microPython] joy1, extra in
                // Press/release events are delivered immediately.  The regular
                // timer still sends exitRequested and refreshes held state, so
                // this callback need not retain the input controller.
                microPython?.setJoy1(joy1, joy2: 0, extra: extra, exitRequested: false)
            }
            microPython.commandHandler = { [weak frameStore] line, payload in
                frameStore?.consumeCommand(line: line, payload: payload)
            }
            microPython.frameHandler = { [weak frameStore] sprites, metadata in
                frameStore?.consumeFrame(sprites: sprites, metadata: metadata)
            }
            startMicroPythonIfReady()
        }
        .onChange(of: runtimeFilesystem.state) { _ in
            startMicroPythonIfReady()
        }
        .onChange(of: scenePhase) { phase in
            // Match the desktop window blur handler: losing focus releases
            // every held source so a suspended app cannot leave a game button
            // stuck down when it resumes.
            if phase != .active {
                input.clearHeldInput()
            }
        }
        .onReceive(Timer.publish(every: 1.0 / 60.0, on: .main, in: .common).autoconnect()) { _ in
            guard microPython.isRunning else { return }
            let sample = input.sampleForRuntime()
            let exitRequested = input.exitRequested
            microPython.setJoy1(sample.joy1, joy2: 0, extra: sample.extra, exitRequested: exitRequested)
            // The host latches the request until its next VM tick, so a
            // single timer sample is enough and avoids repeatedly re-entering
            // the launcher every frame.
            if exitRequested { input.exitRequested = false }
        }
        .overlay(KeyboardCaptureView(input: input).frame(width: 1, height: 1))
    }

    private func startMicroPythonIfReady() {
        guard !microPython.isRunning, let root = runtimeFilesystem.rootURL else { return }
        let runtimeRoot = root.appendingPathComponent("runtime", isDirectory: true)
        microPythonStatus = "STARTING NATIVE MICROPYTHON…"
        if microPython.start(atRuntimeRoot: runtimeRoot.path) {
            microPythonStatus = "MICROPYTHON VM RUNNING"
            microPython.startTickLoop()
        } else {
            microPythonStatus = "VM ERROR: \(microPython.lastError)"
        }
    }

}
