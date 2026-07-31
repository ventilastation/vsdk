import Foundation

/// Installs the unmodified Ventilastation filesystem supplied with the app.
///
/// MicroPython expects normal, writable paths (for settings and saves), while
/// iOS application resources are read-only.  This stage intentionally copies
/// source, ROM, image, and sound files as-is; it does not parse, transform, or
/// regenerate any game content.
@MainActor
final class RuntimeFilesystem: ObservableObject {
    enum State: Equatable {
        case staging
        case ready(URL)
        case failed(String)
    }

    @Published private(set) var state: State = .staging

    private let payloads = [
        (bundleDirectory: "micropython", destination: "runtime"),
        (bundleDirectory: "system", destination: "runtime/system"),
        (bundleDirectory: "vyruss_vs2", destination: "runtime/games/alecu/vyruss_vs2"),
        (bundleDirectory: "vixeous", destination: "runtime/games/alecu/vixeous"),
        (bundleDirectory: "2bam_sencom", destination: "runtime/games/vsjam-oct25/2bam_sencom"),
        (bundleDirectory: "tincho_vrunner", destination: "runtime/games/vsjam-oct25/tincho_vrunner"),
        (bundleDirectory: "vasura_espacial", destination: "runtime/games/vsjam-may25/vasura_espacial"),
    ]

    init() {
        installIfNeeded()
    }

    var rootURL: URL? {
        if case let .ready(url) = state { return url }
        return nil
    }

    private func installIfNeeded() {
        do {
            let fileManager = FileManager.default
            let supportDirectory = try fileManager.url(
                for: .applicationSupportDirectory,
                in: .userDomainMask,
                appropriateFor: nil,
                create: true
            )
            let root = supportDirectory.appendingPathComponent("VentilastationRuntime", isDirectory: true)
            let completionMarker = root.appendingPathComponent(".ios-runtime-v5")

            if fileManager.fileExists(atPath: completionMarker.path) {
                state = .ready(root)
                return
            }

            if fileManager.fileExists(atPath: root.path) {
                try fileManager.removeItem(at: root)
            }
            try fileManager.createDirectory(at: root, withIntermediateDirectories: true)

            for payload in payloads {
                guard let source = Bundle.main.url(forResource: payload.bundleDirectory, withExtension: nil) else {
                    throw RuntimeFilesystemError.missingPayload(payload.bundleDirectory)
                }
                let destination = root.appendingPathComponent(payload.destination, isDirectory: true)
                try fileManager.createDirectory(
                    at: destination.deletingLastPathComponent(),
                    withIntermediateDirectories: true
                )
                try fileManager.copyItem(at: source, to: destination)
            }

            try Data("Ventilastation iOS runtime v5\n".utf8).write(to: completionMarker, options: .atomic)
            state = .ready(root)
        } catch {
            state = .failed(error.localizedDescription)
        }
    }
}

private enum RuntimeFilesystemError: LocalizedError {
    case missingPayload(String)

    var errorDescription: String? {
        switch self {
        case let .missingPayload(name):
            "Missing bundled runtime payload: \(name)"
        }
    }
}
