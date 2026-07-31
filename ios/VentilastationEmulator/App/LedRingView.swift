import SwiftUI

struct LedRingView: View {
    @ObservedObject var engine: VentilastationEngine

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0)) { _ in
            Canvas { context, size in
                let center = CGPoint(x: size.width / 2, y: size.height / 2)
                let radius = min(size.width, size.height) / 2
                let gameColor = engine.selectedGame.color

                context.fill(Path(ellipseIn: CGRect(x: center.x - radius * 0.94, y: center.y - radius * 0.94, width: radius * 1.88, height: radius * 1.88)), with: .radialGradient(
                    Gradient(colors: [Color(white: 0.08), .black]),
                    center: center,
                    startRadius: 0,
                    endRadius: radius
                ))

                drawLeds(context: &context, center: center, radius: radius, gameColor: gameColor)
                drawHud(context: &context, center: center, radius: radius, gameColor: gameColor)
            }
        }
        .drawingGroup()
        .accessibilityLabel("Native Ventilastation LED display")
    }

    private func drawLeds(context: inout GraphicsContext, center: CGPoint, radius: CGFloat, gameColor: Color) {
        let rings: [(CGFloat, Int)] = [(0.31, 20), (0.54, 32), (0.77, 48), (0.91, 64)]
        let time = engine.elapsed
        for (ring, count) in rings {
            for index in 0..<count {
                let angle = Double(index) / Double(count) * 2 * .pi - .pi / 2
                let point = polar(center, radius * ring, angle)
                let glow = ledGlow(angle: angle, ring: ring, time: time)
                let ledRadius = max(2.5, radius * (ring > 0.8 ? 0.013 : 0.016))
                let color = glow > 0.01 ? gameColor.opacity(0.22 + glow * 0.78) : Color.white.opacity(0.045)
                context.fill(Path(ellipseIn: CGRect(x: point.x - ledRadius, y: point.y - ledRadius, width: ledRadius * 2, height: ledRadius * 2)), with: .color(color))
            }
        }

        if engine.mode == .playing {
            let player = polar(center, radius * engine.playerRing, engine.playerAngle)
            let beamEnd = polar(center, radius * 0.96, engine.playerAngle)
            var beam = Path()
            beam.move(to: player)
            beam.addLine(to: beamEnd)
            context.stroke(beam, with: .color(gameColor.opacity(0.65)), lineWidth: max(2, radius * 0.018))
            context.fill(Path(ellipseIn: CGRect(x: player.x - radius * 0.055, y: player.y - radius * 0.055, width: radius * 0.11, height: radius * 0.11)), with: .color(.white))
            context.fill(Path(ellipseIn: CGRect(x: player.x - radius * 0.034, y: player.y - radius * 0.034, width: radius * 0.068, height: radius * 0.068)), with: .color(gameColor))
        }
    }

    private func drawHud(context: inout GraphicsContext, center: CGPoint, radius: CGFloat, gameColor: Color) {
        let title = engine.mode == .library ? "SELECT GAME" : engine.selectedGame.rawValue.uppercased()
        context.draw(Text(title).font(.system(size: radius * 0.075, weight: .black, design: .rounded)).foregroundColor(.white), at: CGPoint(x: center.x, y: center.y - radius * 0.07))
        let subtitle = engine.mode == .library ? "A  START     ◀ ▶  CHOOSE" : "\(engine.score.formatted())  •  WAVE \(engine.wave)"
        context.draw(Text(subtitle).font(.system(size: radius * 0.038, weight: .bold, design: .monospaced)).foregroundColor(gameColor.opacity(0.9)), at: CGPoint(x: center.x, y: center.y + radius * 0.07))

        if engine.flash > 0 {
            context.stroke(Path(ellipseIn: CGRect(x: center.x - radius * 0.965, y: center.y - radius * 0.965, width: radius * 1.93, height: radius * 1.93)), with: .color(gameColor.opacity(engine.flash)), lineWidth: radius * 0.02)
        }
    }

    private func ledGlow(angle: Double, ring: CGFloat, time: Double) -> Double {
        let chase = sin(angle * 4 + time * 3.4) * 0.5 + 0.5
        if engine.mode == .library {
            return ring > 0.74 ? chase * 0.55 : 0.04
        }
        let enemyAngle = time * (0.7 + Double(engine.wave) * 0.06) + Double(ring) * 3
        let distance = abs(atan2(sin(angle - enemyAngle), cos(angle - enemyAngle)))
        let enemy = max(0, 1 - distance * 5.5)
        return max(chase * 0.14, enemy)
    }

    private func polar(_ center: CGPoint, _ radius: CGFloat, _ angle: Double) -> CGPoint {
        CGPoint(x: center.x + cos(angle) * radius, y: center.y + sin(angle) * radius)
    }
}

struct NativeLedRingView: View {
    @ObservedObject var frameStore: NativeFrameStore

    var body: some View {
        Canvas { context, size in
            let center = CGPoint(x: size.width / 2, y: size.height / 2)
            let radius = min(size.width, size.height) / 2
            context.fill(Path(ellipseIn: CGRect(x: center.x - radius * 0.95, y: center.y - radius * 0.95, width: radius * 1.9, height: radius * 1.9)), with: .radialGradient(Gradient(colors: [.black, Color(white: 0.04)]), center: center, startRadius: 0, endRadius: radius))
            for column in 0..<256 {
                let angle = Double(column) / 256.0 * 2.0 * .pi - .pi / 2.0
                for led in 0..<54 {
                    let ring = 0.20 + CGFloat(led) / 54.0 * 0.72
                    let point = CGPoint(x: center.x + cos(angle) * radius * ring, y: center.y + sin(angle) * radius * ring)
                    let color = frameStore.color(at: column * 54 + led)
                    let diameter = max(1.5, radius * 0.012)
                    context.fill(Path(ellipseIn: CGRect(x: point.x - diameter, y: point.y - diameter, width: diameter * 2, height: diameter * 2)), with: .color(color))
                }
            }
        }
        .drawingGroup()
        .accessibilityLabel("Native MicroPython LED display")
    }
}
