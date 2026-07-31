import SwiftUI

@main
struct VentilastationEmulatorApp: App {
    var body: some Scene {
        WindowGroup {
            EmulatorScreen()
                .preferredColorScheme(.dark)
        }
    }
}
