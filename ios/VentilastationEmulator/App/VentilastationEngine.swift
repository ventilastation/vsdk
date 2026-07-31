import Foundation
import SwiftUI

@MainActor
final class VentilastationEngine: ObservableObject {
    enum Mode: Equatable {
        case library
        case playing
    }

    enum Game: String, CaseIterable, Identifiable, Hashable {
        case orbitDefender = "Orbit Defender"
        case pulseRunner = "Pulse Runner"
        case prismShift = "Prism Shift"

        var id: Self { self }

        var subtitle: String {
            switch self {
            case .orbitDefender: "Protect the inner ring"
            case .pulseRunner: "Ride the rotating light lane"
            case .prismShift: "Match the changing spectrum"
            }
        }

        var color: Color {
            switch self {
            case .orbitDefender: .cyan
            case .pulseRunner: .orange
            case .prismShift: .pink
            }
        }
    }

    enum Control: String, Hashable {
        case up, down, left, right, a, b, c, d, start, back
    }

    @Published private(set) var mode: Mode = .library
    @Published private(set) var selectedGame: Game = .orbitDefender
    @Published private(set) var score = 0
    @Published private(set) var wave = 1
    @Published private(set) var playerAngle = -Double.pi / 2
    @Published private(set) var playerRing = 0.78
    @Published private(set) var elapsed = 0.0
    @Published private(set) var flash = 0.0

    private var heldControls: Set<Control> = []
    private var lastTick = Date()
    private var timer: Timer?

    init() {
        timer = Timer.scheduledTimer(withTimeInterval: 1.0 / 60.0, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.tick()
            }
        }
    }

    deinit {
        timer?.invalidate()
    }

    func select(_ game: Game) {
        selectedGame = game
        flash = 1
    }

    func start() {
        score = 0
        wave = 1
        elapsed = 0
        playerAngle = -Double.pi / 2
        playerRing = 0.78
        mode = .playing
        flash = 1
    }

    func reset() {
        heldControls.removeAll()
        mode = .library
        score = 0
        wave = 1
        elapsed = 0
        playerAngle = -Double.pi / 2
        playerRing = 0.78
        flash = 0
    }

    func press(_ control: Control) {
        if mode == .library {
            switch control {
            case .up, .left: cycleGame(by: -1)
            case .down, .right: cycleGame(by: 1)
            case .a, .c: start()
            default: break
            }
            return
        }

        if control == .b {
            reset()
            return
        }
        if control == .d {
            start()
            return
        }
        if control == .a || control == .c {
            score += control == .c ? 50 : 25
            flash = 1
        }
        heldControls.insert(control)
    }

    func release(_ control: Control) {
        heldControls.remove(control)
    }

    private func cycleGame(by delta: Int) {
        let games = Game.allCases
        guard let current = games.firstIndex(of: selectedGame) else { return }
        selectedGame = games[(current + delta + games.count) % games.count]
        flash = 1
    }

    private func tick() {
        let now = Date()
        let delta = min(now.timeIntervalSince(lastTick), 0.05)
        lastTick = now
        guard mode == .playing else {
            flash = max(0, flash - delta * 2)
            return
        }

        elapsed += delta
        flash = max(0, flash - delta * 3)
        let speed = 2.3 * delta
        if heldControls.contains(.left) { playerAngle -= speed }
        if heldControls.contains(.right) { playerAngle += speed }
        if heldControls.contains(.up) { playerRing = min(0.92, playerRing + delta * 0.75) }
        if heldControls.contains(.down) { playerRing = max(0.3, playerRing - delta * 0.75) }
        if Int(elapsed) > wave * 12 {
            wave += 1
            flash = 1
        }
    }
}
