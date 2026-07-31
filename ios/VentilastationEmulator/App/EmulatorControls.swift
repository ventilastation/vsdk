import SwiftUI
import UIKit

@MainActor
final class NativeInputController: ObservableObject {
    @Published private(set) var joy1: UInt8 = 0
    @Published private(set) var extra: UInt8 = 0
    @Published var exitRequested = false
    var onChange: ((UInt8, UInt8) -> Void)?
    private var pressCounts: [VentilastationEngine.Control: Int] = [:]

    /// Return the current held state.  The desktop emulator is level-triggered:
    /// Director derives press/release edges by comparing this state with the
    /// previous game tick, so releases must never retain a pending press bit.
    func sampleForRuntime() -> (joy1: UInt8, extra: UInt8) {
        (joy1, extra)
    }

    func press(_ control: VentilastationEngine.Control) {
        let count = pressCounts[control, default: 0]
        pressCounts[control] = count + 1
        // Multiple input sources can hold the same logical control (for
        // example, keyboard Right plus the on-screen Right button).  Keep the
        // bit down until the final source releases it, just like the desktop
        // emulator's OR of its independent input masks.
        guard count == 0 else { return }
        switch control {
        case .left: pressJoy1(0x01)
        case .right: pressJoy1(0x02)
        case .up: pressJoy1(0x04)
        case .down: pressJoy1(0x08)
        case .a: pressJoy1(0x10)
        case .b: pressJoy1(0x20)
        case .c: pressJoy1(0x40)
        case .d: extra |= 0x01
        case .start: extra |= 0x04
        case .back: extra |= 0x08
        }
        notifyRuntime()
        NSLog("Ventilastation input press %@ joy1=%02x extra=%02x", control.rawValue, joy1, extra)
    }

    func release(_ control: VentilastationEngine.Control) {
        guard let count = pressCounts[control], count > 0 else { return }
        if count == 1 {
            pressCounts.removeValue(forKey: control)
        } else {
            pressCounts[control] = count - 1
            return
        }
        switch control {
        case .left: joy1 &= ~0x01
        case .right: joy1 &= ~0x02
        case .up: joy1 &= ~0x04
        case .down: joy1 &= ~0x08
        case .a: joy1 &= ~0x10
        case .b: joy1 &= ~0x20
        case .c: joy1 &= ~0x40
        case .d: extra &= ~0x01
        case .start: extra &= ~0x04
        case .back: extra &= ~0x08
        }
        notifyRuntime()
        NSLog("Ventilastation input release %@ joy1=%02x extra=%02x", control.rawValue, joy1, extra)
    }

    func clearHeldInput() {
        guard !pressCounts.isEmpty || joy1 != 0 || extra != 0 else { return }
        pressCounts.removeAll()
        joy1 = 0
        extra = 0
        notifyRuntime()
    }

    private func pressJoy1(_ bit: UInt8) {
        joy1 |= bit
    }

    private func notifyRuntime() {
        // Push the same level-triggered state that the desktop emulator sends.
        onChange?(joy1, extra)
    }
}

struct GameLibrary: View {
    @ObservedObject var engine: VentilastationEngine
    let compact: Bool

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(VentilastationEngine.Game.allCases) { game in
                    Button {
                        engine.select(game)
                    } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(game.rawValue)
                                .font(.caption.weight(.bold))
                            Text(game.subtitle)
                                .font(.caption2)
                                .lineLimit(1)
                                .foregroundStyle(.white.opacity(0.6))
                        }
                        .frame(width: compact ? 150 : 176, alignment: .leading)
                        .padding(compact ? 9 : 12)
                        .background(engine.selectedGame == game ? game.color.opacity(0.24) : Color.white.opacity(0.07), in: RoundedRectangle(cornerRadius: 12))
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(engine.selectedGame == game ? game.color : .clear, lineWidth: 1))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(.horizontal, 22)
    }
}

struct EmulatorControls: View {
    @ObservedObject var engine: VentilastationEngine
    @ObservedObject var input: NativeInputController

    var body: some View {
        GeometryReader { proxy in
            let controlsWidth: CGFloat = 410
            let scale = min(1, (proxy.size.width - 4) / controlsWidth)
            HStack(alignment: .center, spacing: 30) {
                DPad(engine: engine, input: input)
                Spacer(minLength: 0)
                HStack(spacing: 13) {
                    ControlButton(title: "C", tint: .purple, control: .c, engine: engine, input: input)
                    ControlButton(title: "D", tint: .pink, control: .d, engine: engine, input: input)
                    ControlButton(title: "B", tint: .orange, control: .b, engine: engine, input: input)
                    ControlButton(title: "A", tint: .cyan, control: .a, engine: engine, input: input)
                }
            }
            .frame(width: controlsWidth, height: 154)
            .scaleEffect(scale)
            .frame(width: proxy.size.width, height: 154)
        }
        .frame(height: 154)
    }
}

private struct DPad: View {
    @ObservedObject var engine: VentilastationEngine
    @ObservedObject var input: NativeInputController

    var body: some View {
        // Explicit offsets keep all four directions inside the control
        // surface.  The former nested VStack/HStack could place the bottom
        // button outside the GeometryReader's clipped bounds on the compact
        // simulator layout.
        ZStack {
            Color.white.opacity(0.1)
                .frame(width: 44, height: 44)
                .clipShape(RoundedRectangle(cornerRadius: 11))
            ControlButton(title: "▲", tint: .white, control: .up, engine: engine, input: input, small: true)
                .offset(y: -49)
            ControlButton(title: "▼", tint: .white, control: .down, engine: engine, input: input, small: true)
                .offset(y: 49)
            ControlButton(title: "◀", tint: .white, control: .left, engine: engine, input: input, small: true)
                .offset(x: -49)
            ControlButton(title: "▶", tint: .white, control: .right, engine: engine, input: input, small: true)
                .offset(x: 49)
        }
        .frame(width: 150, height: 150)
    }
}

private struct ControlButton: View {
    let title: String
    let tint: Color
    let control: VentilastationEngine.Control
    @ObservedObject var engine: VentilastationEngine
    @ObservedObject var input: NativeInputController
    var small = false
    @State private var pressed = false

    private func beginPress() {
        guard !pressed else { return }
        pressed = true
        engine.press(control)
        input.press(control)
    }

    private func endPress() {
        guard pressed else { return }
        pressed = false
        engine.release(control)
        input.release(control)
    }

    var body: some View {
        Text(title)
            .font(.system(size: small ? 17 : 19, weight: .black, design: .rounded))
            .frame(width: small ? 44 : 48, height: small ? 44 : 48)
            .foregroundStyle(tint)
            .background(tint.opacity(pressed ? 0.42 : 0.18), in: Circle())
            .overlay(Circle().stroke(tint.opacity(0.8), lineWidth: 1.5))
            .contentShape(Circle())
            // DragGesture with a zero threshold gives us reliable touch-down and
            // touch-up events for both taps and held controls.  Long-press
            // gestures can fail to deliver the initial pressing callback on the
            // simulator when the view is inside a scaled SwiftUI layout.
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { _ in beginPress() }
                    .onEnded { _ in endPress() }
            )
            .onDisappear { endPress() }
            .accessibilityAddTraits(.isButton)
            .accessibilityLabel("Button \(title)")
    }
}

struct KeyboardCaptureView: UIViewRepresentable {
    @ObservedObject var input: NativeInputController

    func makeUIView(context: Context) -> KeyboardCaptureUIView {
        let view = KeyboardCaptureUIView(input: input)
        DispatchQueue.main.async { view.becomeFirstResponder() }
        return view
    }

    func updateUIView(_ view: KeyboardCaptureUIView, context: Context) {
        view.input = input
    }
}

final class KeyboardCaptureUIView: UIView {
    var input: NativeInputController
    private var pressedKeys: Set<UIKeyboardHIDUsage> = []

    init(input: NativeInputController) {
        self.input = input
        super.init(frame: .zero)
        alpha = 0.01
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    override var canBecomeFirstResponder: Bool { true }

    override func didMoveToWindow() {
        super.didMoveToWindow()
        guard window != nil else {
            clearPressedKeys()
            return
        }
        // A one-point invisible responder is intentional: it keeps the native
        // app focused on the game while still accepting simulator hardware
        // keyboard events without presenting an on-screen keyboard.
        DispatchQueue.main.async { [weak self] in
            _ = self?.becomeFirstResponder()
        }
    }

    override func pressesBegan(_ presses: Set<UIPress>, with event: UIPressesEvent?) {
        for press in presses {
            guard let key = press.key?.keyCode, pressedKeys.insert(key).inserted else { continue }
            if let control = control(for: press) { input.press(control) }
        }
        super.pressesBegan(presses, with: event)
    }

    override func pressesEnded(_ presses: Set<UIPress>, with event: UIPressesEvent?) {
        for press in presses {
            guard let key = press.key?.keyCode, pressedKeys.remove(key) != nil else { continue }
            if let control = control(for: press) { input.release(control) }
        }
        super.pressesEnded(presses, with: event)
    }

    override func pressesCancelled(_ presses: Set<UIPress>, with event: UIPressesEvent?) {
        for press in presses {
            guard let key = press.key?.keyCode, pressedKeys.remove(key) != nil else { continue }
            if let control = control(for: press) { input.release(control) }
        }
        super.pressesCancelled(presses, with: event)
    }

    private func clearPressedKeys() {
        for key in pressedKeys {
            if let control = control(for: key) { input.release(control) }
        }
        pressedKeys.removeAll()
    }

    private func control(for key: UIKeyboardHIDUsage) -> VentilastationEngine.Control? {
        switch key {
        case .keyboardUpArrow, .keyboardW: return .up
        case .keyboardDownArrow, .keyboardS: return .down
        case .keyboardLeftArrow, .keyboardA: return .left
        case .keyboardRightArrow, .keyboardD: return .right
        case .keyboardSpacebar: return .a
        case .keyboardO: return .b
        case .keyboardP: return .c
        case .keyboardY: return .d
        case .keyboardPageUp: return .start
        case .keyboardPageDown: return .back
        default: return nil
        }
    }

    private func control(for press: UIPress) -> VentilastationEngine.Control? {
        guard let key = press.key else { return nil }
        return control(for: key.keyCode)
    }
}
