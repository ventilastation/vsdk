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
            let compact = proxy.size.height < 900 || proxy.size.width < 500
            let displayWidth = min(
                proxy.size.width - (compact ? 56 : 36),
                compact ? 220 : 560
            )

            VStack(spacing: compact ? 10 : 18) {
                header

                NativeMetalRingView(frameStore: frameStore)
                    .frame(width: displayWidth, height: displayWidth)
                    // The original Ventilastation ring is mounted with its
                    // zero-angle LED at the opposite side from the phone's
                    // portrait coordinate system.  Rotate only the display;
                    // the native controls and status UI remain upright.
                    .rotationEffect(.degrees(180))

                statusBar

                EmulatorControls(engine: emulator, input: input)
                    .padding(.horizontal, 22)
                    // Leave room for the home-indicator safe area on the
                    // compact iPhone simulator.  Without this small lift the
                    // lower D-pad and face-button halves are outside the
                    // visible safe region.
                    .offset(y: compact ? -42 : 0)
            }
            .padding(.top, compact ? 8 : 20)
            .padding(.bottom, compact ? 8 : 18)
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
            microPython.setJoy1(sample.joy1, joy2: 0, extra: sample.extra, exitRequested: input.exitRequested)
        }
        .overlay(KeyboardCaptureView(input: input).frame(width: 1, height: 1))
    }

    private var header: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text("VENTILASTATION")
                    .font(.caption.weight(.black))
                    .tracking(2)
                Text("VYRUSS VS2 • NATIVE GAME")
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(.white.opacity(0.55))
                Text(runtimeStatus)
                    .font(.caption2.monospaced().weight(.medium))
                    .foregroundStyle(runtimeStatusColor)
            }
            Spacer()
            Button {
                emulator.reset()
                input.clearHeldInput()
                input.exitRequested = true
            } label: {
                Image(systemName: "arrow.counterclockwise")
                    .font(.body.weight(.bold))
                    .padding(10)
                    .background(Color.white.opacity(0.1), in: Circle())
            }
            .accessibilityLabel("Reset console")
        }
        .padding(.horizontal, 22)
    }

    private var runtimeStatus: String {
        if microPython.isRunning { return "MICROPYTHON VM RUNNING" }
        if microPythonStatus.hasPrefix("VM ERROR") { return microPythonStatus }
        switch runtimeFilesystem.state {
        case .staging: return "STAGING ORIGINAL RUNTIME…"
        case .ready: return "ORIGINAL RUNTIME FILES READY"
        case .failed: return "RUNTIME FILESYSTEM ERROR"
        }
    }

    private var runtimeStatusColor: Color {
        if microPython.isRunning { return .green }
        if microPythonStatus.hasPrefix("VM ERROR") { return .red }
        switch runtimeFilesystem.state {
        case .staging: return .orange
        case .ready: return .green
        case .failed: return .red
        }
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

    private var statusBar: some View {
        HStack(spacing: 8) {
            StatusPill(label: "SCORE \(emulator.score.formatted())")
            StatusPill(label: "WAVE \(emulator.wave)")
            StatusPill(label: "33 HZ")
            StatusPill(label: String(format: "IN %02X/%02X", input.joy1, input.extra))
                .layoutPriority(1)
            Spacer(minLength: 0)
            Text("V: BACK TO MENU")
                .font(.caption2.weight(.bold))
                .foregroundStyle(.white.opacity(0.55))
        }
        .padding(.horizontal, 22)
    }
}

private struct StatusPill: View {
    let label: String

    var body: some View {
        Text(label)
            .font(.caption2.monospaced().weight(.bold))
            .padding(.horizontal, 9)
            .padding(.vertical, 6)
            .background(Color.white.opacity(0.1), in: Capsule())
    }
}
