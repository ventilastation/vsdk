import MetalKit
import SwiftUI

private struct RingUniforms {
    var drawableCount: UInt32 = 0
    var columnOffset: UInt32 = 0
    var starCount: UInt32 = 0
    var spriteCount: UInt32 = 0
    var viewport = SIMD2<Float>(repeating: 0)
    var padding = SIMD2<Float>(repeating: 0)
}

final class NativeMetalRingRenderer: NSObject, MTKViewDelegate {
    private let device: MTLDevice
    private let queue: MTLCommandQueue
    private let pipeline: MTLRenderPipelineState
    private var store: NativeFrameStore?
    private var uploadedAssetRevision: UInt64 = .max
    private var uploadedSceneRevision: UInt64 = .max
    private var strips: MTLTexture?
    private var stripMeta: MTLTexture?
    private var palette: MTLTexture?
    private var scene: MTLTexture?
    private var cells: MTLTexture?
    private var stars: MTLTexture?
    private var deepspace: MTLTexture
    private var uploadedStarFrame = Int.min
    private var uniforms = RingUniforms()

    init?(view: MTKView, store: NativeFrameStore) {
        guard let device = MTLCreateSystemDefaultDevice(),
              let queue = device.makeCommandQueue(),
              let library = device.makeDefaultLibrary(),
              let vertex = library.makeFunction(name: "ringVertex"),
              let fragment = library.makeFunction(name: "ringFragment") else { return nil }
        self.device = device
        self.queue = queue
        let descriptor = MTLRenderPipelineDescriptor()
        descriptor.vertexFunction = vertex
        descriptor.fragmentFunction = fragment
        descriptor.colorAttachments[0].pixelFormat = view.colorPixelFormat
        descriptor.colorAttachments[0].isBlendingEnabled = false
        guard let pipeline = try? device.makeRenderPipelineState(descriptor: descriptor),
              let deepspace = Self.makeDeepspaceTexture(device: device) else { return nil }
        self.pipeline = pipeline
        self.deepspace = deepspace
        self.store = store
        super.init()
    }

    func setStore(_ store: NativeFrameStore) {
        self.store = store
    }

    func mtkView(_ view: MTKView, drawableSizeWillChange size: CGSize) {}

    func draw(in view: MTKView) {
        guard let store, let pass = view.currentRenderPassDescriptor,
              let drawable = view.currentDrawable,
              let commandBuffer = queue.makeCommandBuffer(),
              let encoder = commandBuffer.makeRenderCommandEncoder(descriptor: pass) else { return }
        let snapshot = store.snapshot()
        uploadIfNeeded(snapshot)
        if snapshot.frameNumber != uploadedStarFrame {
            stars = makeStarTexture(frameNumber: snapshot.frameNumber)
            uploadedStarFrame = snapshot.frameNumber
        }

        uniforms.drawableCount = UInt32(snapshot.drawableCount)
        uniforms.columnOffset = UInt32(snapshot.columnOffset & 255)
        uniforms.starCount = UInt32(Self.starCount)
        uniforms.spriteCount = UInt32(snapshot.spriteCount)
        uniforms.viewport = SIMD2<Float>(Float(view.drawableSize.width), Float(view.drawableSize.height))

        encoder.setRenderPipelineState(pipeline)
        encoder.setFragmentBytes(&uniforms, length: MemoryLayout<RingUniforms>.stride, index: 0)
        encoder.setFragmentTexture(strips, index: 0)
        encoder.setFragmentTexture(stripMeta, index: 1)
        encoder.setFragmentTexture(palette, index: 2)
        encoder.setFragmentTexture(scene, index: 3)
        encoder.setFragmentTexture(deepspace, index: 4)
        encoder.setFragmentTexture(cells, index: 5)
        encoder.setFragmentTexture(stars, index: 6)
        encoder.drawPrimitives(type: .triangle, vertexStart: 0, vertexCount: 3)
        encoder.endEncoding()
        commandBuffer.present(drawable)
        commandBuffer.commit()
    }

    private func uploadIfNeeded(_ snapshot: NativeMetalFrameSnapshot) {
        if snapshot.assetRevision != uploadedAssetRevision {
            strips = makeByteTexture(bytes: snapshot.stripAtlas, width: 2048, height: snapshot.stripAtlasHeight, pixelFormat: .r8Uint)
            stripMeta = makeUIntTexture(values: snapshot.stripMeta, width: 256, height: 1, pixelFormat: .rgba32Uint)
            palette = makeByteTexture(bytes: snapshot.palette, width: 256, height: snapshot.paletteHeight, pixelFormat: .rgba8Unorm)
            uploadedAssetRevision = snapshot.assetRevision
        }
        if snapshot.sceneRevision != uploadedSceneRevision {
            let values = snapshot.scene.isEmpty ? [UInt32](repeating: 0, count: 16) : snapshot.scene
            scene = makeUIntTexture(values: values, width: 4, height: max(1, snapshot.drawableCount), pixelFormat: .rgba32Uint)
            cells = makeByteTexture(bytes: snapshot.cells, width: 2048, height: snapshot.cellsHeight, pixelFormat: .r8Uint)
            uploadedSceneRevision = snapshot.sceneRevision
        }
    }

    private func makeByteTexture(bytes: [UInt8], width: Int, height: Int, pixelFormat: MTLPixelFormat) -> MTLTexture? {
        let descriptor = MTLTextureDescriptor.texture2DDescriptor(pixelFormat: pixelFormat, width: width, height: height, mipmapped: false)
        descriptor.usage = [.shaderRead]
        guard let texture = device.makeTexture(descriptor: descriptor) else { return nil }
        bytes.withUnsafeBytes { raw in
            texture.replace(region: MTLRegionMake2D(0, 0, width, height), mipmapLevel: 0, withBytes: raw.baseAddress!, bytesPerRow: width * (pixelFormat == .rgba8Unorm ? 4 : 1))
        }
        return texture
    }

    private func makeUIntTexture(values: [UInt32], width: Int, height: Int, pixelFormat: MTLPixelFormat) -> MTLTexture? {
        let descriptor = MTLTextureDescriptor.texture2DDescriptor(pixelFormat: pixelFormat, width: width, height: height, mipmapped: false)
        descriptor.usage = [.shaderRead]
        guard let texture = device.makeTexture(descriptor: descriptor) else { return nil }
        values.withUnsafeBytes { raw in
            let channels = pixelFormat == .rgba32Uint ? 4 : 1
            texture.replace(region: MTLRegionMake2D(0, 0, width, height), mipmapLevel: 0, withBytes: raw.baseAddress!, bytesPerRow: width * channels * MemoryLayout<UInt32>.size)
        }
        return texture
    }

    private static let starCount = 128

    private struct StarSeed {
        let x0: Int
        let y0: Int
        let wraps: [Int]
    }

    private lazy var starSeeds: [StarSeed] = {
        var state: UInt32 = 0x1badf00d
        func nextInt() -> Int {
            state = state &* 1664525 &+ 1013904223
            return Int((Double(state) / 4294967296.0) * 256.0)
        }
        return (0..<Self.starCount).map { _ in
            StarSeed(x0: nextInt(), y0: nextInt(), wraps: (0..<8).map { _ in nextInt() })
        }
    }()

    private func makeStarTexture(frameNumber: Int) -> MTLTexture? {
        let ticks = max(0, frameNumber)
        let values = starSeeds.map { star -> UInt32 in
            let total = star.y0 - ticks
            let wrappedY = ((total % 256) + 256) % 256
            let wrapCount = (ticks + (255 - star.y0)) / 256
            let x = wrapCount <= 0 ? star.x0 : star.wraps[(wrapCount - 1) % star.wraps.count]
            return UInt32((x & 255) | ((wrappedY & 255) << 8))
        }
        return makeUIntTexture(values: values, width: Self.starCount, height: 1, pixelFormat: .r32Uint)
    }

    private static func makeDeepspaceTexture(device: MTLDevice) -> MTLTexture? {
        var values = [UInt32](repeating: 0, count: 256 * 4)
        var forwardLegacy = [UInt32](repeating: 54, count: 256)
        var forwardVS2 = [UInt32](repeating: 54, count: 256)
        for y in 16..<256 {
            let n = 240 - 1 - (y - 16)
            forwardLegacy[y] = UInt32((54.0 * pow(Double(n) / 240.0, 1.0 / 0.28)).rounded())
        }
        for y in 0..<256 {
            forwardVS2[y] = UInt32((53.0 * pow(Double(255 - y) / 255.0, 1.0 / 0.28)).rounded())
        }
        func pack(_ projection: [UInt32], forwardRow: Int, inverseRow: Int) {
            for y in 0..<256 { values[forwardRow * 256 + y] = projection[y] }
            for led in 0..<54 {
                var lo: UInt32 = 255
                var hi: UInt32 = 0
                for y in 0..<256 where projection[y] == UInt32(led) {
                    lo = min(lo, UInt32(y)); hi = max(hi, UInt32(y))
                }
                values[inverseRow * 256 + led] = lo | (hi << 8)
            }
        }
        pack(forwardLegacy, forwardRow: 0, inverseRow: 1)
        pack(forwardVS2, forwardRow: 2, inverseRow: 3)
        let descriptor = MTLTextureDescriptor.texture2DDescriptor(pixelFormat: .r32Uint, width: 256, height: 4, mipmapped: false)
        descriptor.usage = [.shaderRead]
        guard let texture = device.makeTexture(descriptor: descriptor) else { return nil }
        values.withUnsafeBytes { raw in
            texture.replace(region: MTLRegionMake2D(0, 0, 256, 4), mipmapLevel: 0, withBytes: raw.baseAddress!, bytesPerRow: 256 * MemoryLayout<UInt32>.size)
        }
        return texture
    }
}

struct NativeMetalRingView: UIViewRepresentable {
    @ObservedObject var frameStore: NativeFrameStore

    final class Coordinator {
        var renderer: NativeMetalRingRenderer?
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> MTKView {
        let view = MTKView(frame: .zero)
        view.device = MTLCreateSystemDefaultDevice()
        // The Metal surface is display-only.  Keep it out of the hit-test
        // chain so it can never intercept taps intended for the SwiftUI game
        // controls below it.
        view.isUserInteractionEnabled = false
        view.colorPixelFormat = .bgra8Unorm
        view.clearColor = MTLClearColor(red: 0, green: 0, blue: 0, alpha: 1)
        view.preferredFramesPerSecond = 60
        view.enableSetNeedsDisplay = false
        guard let renderer = NativeMetalRingRenderer(view: view, store: frameStore) else { return view }
        context.coordinator.renderer = renderer
        view.delegate = renderer
        return view
    }

    func updateUIView(_ view: MTKView, context: Context) {
        if let renderer = context.coordinator.renderer {
            renderer.setStore(frameStore)
        }
    }
}
