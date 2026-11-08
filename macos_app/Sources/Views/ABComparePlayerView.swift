import SwiftUI
import AVKit
import AVFoundation
import AppKit

// MARK: - Split Mode Enum (Vertical vs NVIDIA Official Diagonal 3DGS/Video Split)

public enum ABSplitStyle: String, CaseIterable, Identifiable, Sendable {
    case diagonal3DGS = "diagonal"
    case vertical = "vertical"

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .diagonal3DGS: return "╱ 官方 3DGS 斜切分屏"
        case .vertical: return "┃ 垂直同屏对比"
        }
    }
}

// MARK: - Custom Clip Shapes for Vertical & NVIDIA Diagonal `/` Split

private struct LeftOrTopLeftClipShape: Shape {
    var splitFraction: CGFloat
    var style: ABSplitStyle
    var slantWidthRatio: CGFloat = 0.24

    func path(in rect: CGRect) -> Path {
        var p = Path()
        switch style {
        case .vertical:
            let splitX = rect.width * splitFraction
            p.addRect(CGRect(x: 0, y: 0, width: max(0, splitX), height: rect.height))
        case .diagonal3DGS:
            // Diagonal `/` line from top (splitX + slant) to bottom (splitX - slant)
            // Top-Left region is 3DGS / Raw
            let centerX = rect.width * splitFraction
            let slant = rect.width * slantWidthRatio
            let topX = min(rect.width * 1.35, max(-rect.width * 0.35, centerX + slant))
            let bottomX = min(rect.width * 1.35, max(-rect.width * 0.35, centerX - slant))

            p.move(to: CGPoint(x: 0, y: 0))
            p.addLine(to: CGPoint(x: topX, y: 0))
            p.addLine(to: CGPoint(x: bottomX, y: rect.height))
            p.addLine(to: CGPoint(x: 0, y: rect.height))
            p.closeSubpath()
        }
        return p
    }
}

// MARK: - Borderless Synchronized AVPlayerLayer NSViewRepresentable

public struct BareAVPlayerLayerView: NSViewRepresentable {
    public let player: AVPlayer

    public init(player: AVPlayer) {
        self.player = player
    }

    public func makeNSView(context: Context) -> PlayerContainerNSView {
        let view = PlayerContainerNSView()
        view.playerLayer.player = player
        view.playerLayer.videoGravity = .resizeAspect
        return view
    }

    public func updateNSView(_ nsView: PlayerContainerNSView, context: Context) {
        if nsView.playerLayer.player !== player {
            nsView.playerLayer.player = player
        }
    }

    public final class PlayerContainerNSView: NSView {
        public let playerLayer = AVPlayerLayer()

        override init(frame frameRect: NSRect) {
            super.init(frame: frameRect)
            wantsLayer = true
            layer?.backgroundColor = NSColor.black.cgColor
            layer?.addSublayer(playerLayer)
        }

        required init?(coder: NSCoder) {
            fatalError("init(coder:) has not been implemented")
        }

        public override func layout() {
            super.layout()
            CATransaction.begin()
            CATransaction.setDisableActions(true)
            playerLayer.frame = bounds
            CATransaction.commit()
        }
    }
}

// MARK: - Dual Synchronized Video Controller

@MainActor
public final class DualSyncVideoController: ObservableObject {
    public let rawPlayer = AVPlayer()
    public let enhancedPlayer = AVPlayer()

    @Published public var isPlaying: Bool = true
    @Published public var playbackRate: Float = 1.0
    @Published public var normalizedProgress: Double = 0.0
    @Published public var currentTimeSeconds: Double = 0.0
    @Published public var durationSeconds: Double = 7.5
    @Published public var rawPosterImage: NSImage?
    @Published public var enhancedPosterImage: NSImage?

    private var timeObserver: Any?
    private var endObserverA: NSObjectProtocol?
    private var endObserverB: NSObjectProtocol?
    private var currentPairId: String?
    private var speedRatio: Double = 2.0

    public init() {
        rawPlayer.isMuted = true
        enhancedPlayer.isMuted = true
        setupPeriodicObserver()
    }

    public func loadPair(_ pair: ABComparePair) {
        guard currentPairId != pair.id else { return }
        currentPairId = pair.id
        speedRatio = max(1.0, pair.speedFactor)

        rawPlayer.pause()
        enhancedPlayer.pause()

        let rawURL = pair.rawItem.localFileURL
        let enhURL = pair.enhancedItem.localFileURL

        if FileManager.default.fileExists(atPath: rawURL.path) {
            rawPlayer.replaceCurrentItem(with: AVPlayerItem(url: rawURL))
        }
        if FileManager.default.fileExists(atPath: enhURL.path) {
            enhancedPlayer.replaceCurrentItem(with: AVPlayerItem(url: enhURL))
        }

        durationSeconds = pair.enhancedItem.info?.duration ?? 7.53

        // Load high-res poster thumbnails for instant 0ms preview before video frame decode
        Task {
            self.rawPosterImage = await ThumbnailCacheActor.shared.thumbnail(for: pair.rawItem, maxPixelSize: 960)
            self.enhancedPosterImage = await ThumbnailCacheActor.shared.thumbnail(for: pair.enhancedItem, maxPixelSize: 1280)
        }

        installLoopObservers()
        playSynchronized()
    }

    public func togglePlayPause() {
        if isPlaying {
            pauseSynchronized()
        } else {
            playSynchronized()
        }
    }

    public func setRate(_ rate: Float) {
        playbackRate = rate
        if isPlaying {
            playSynchronized()
        }
    }

    public func playSynchronized() {
        isPlaying = true
        enhancedPlayer.playImmediately(atRate: playbackRate)
        // Raw Lyra video is 1x duration (e.g. 15.06s) while enhanced 2x video is 7.53s;
        // scale rawPlayer rate by speedRatio so both traverse the exact same 3D space position simultaneously!
        rawPlayer.playImmediately(atRate: playbackRate * Float(speedRatio))
    }

    public func pauseSynchronized() {
        isPlaying = false
        rawPlayer.pause()
        enhancedPlayer.pause()
    }

    public func seek(toNormalized fraction: Double) {
        let clamped = min(1.0, max(0.0, fraction))
        normalizedProgress = clamped

        let enhDur = max(0.5, enhancedPlayer.currentItem?.duration.seconds ?? durationSeconds)
        let rawDur = max(0.5, rawPlayer.currentItem?.duration.seconds ?? (enhDur * speedRatio))

        if enhDur.isFinite {
            let targetEnh = CMTime(seconds: enhDur * clamped, preferredTimescale: 600)
            enhancedPlayer.seek(to: targetEnh, toleranceBefore: .zero, toleranceAfter: .zero)
            currentTimeSeconds = enhDur * clamped
        }
        if rawDur.isFinite {
            let targetRaw = CMTime(seconds: rawDur * clamped, preferredTimescale: 600)
            rawPlayer.seek(to: targetRaw, toleranceBefore: .zero, toleranceAfter: .zero)
        }
    }

    private func setupPeriodicObserver() {
        let interval = CMTime(seconds: 1.0 / 30.0, preferredTimescale: 600)
        timeObserver = enhancedPlayer.addPeriodicTimeObserver(forInterval: interval, queue: .main) { [weak self] time in
            Task { @MainActor [weak self] in
                guard let self else { return }
                let sec = time.seconds
                let dur = self.enhancedPlayer.currentItem?.duration.seconds ?? self.durationSeconds
                if sec.isFinite && dur.isFinite && dur > 0.1 {
                    self.durationSeconds = dur
                    self.currentTimeSeconds = sec
                    self.normalizedProgress = min(1.0, max(0.0, sec / dur))
                }
            }
        }
    }

    private func installLoopObservers() {
        if let endObserverB {
            NotificationCenter.default.removeObserver(endObserverB)
        }
        endObserverB = NotificationCenter.default.addObserver(
            forName: .AVPlayerItemDidPlayToEndTime,
            object: enhancedPlayer.currentItem,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor [weak self] in
                guard let self else { return }
                self.seek(toNormalized: 0.0)
                if self.isPlaying {
                    self.playSynchronized()
                }
            }
        }
    }

    deinit {
        if let obs = timeObserver {
            enhancedPlayer.removeTimeObserver(obs)
        }
        if let endObserverA {
            NotificationCenter.default.removeObserver(endObserverA)
        }
        if let endObserverB {
            NotificationCenter.default.removeObserver(endObserverB)
        }
    }
}

// MARK: - ABComparePlayerView (Interactive Split-Screen Video Comparison)

public struct ABComparePlayerView: View {
    @ObservedObject var galleryStore: GalleryStore
    @ObservedObject var coordinator: StudioCoordinator

    @StateObject private var syncController = DualSyncVideoController()
    @State private var splitStyle: ABSplitStyle = .diagonal3DGS
    @State private var splitFraction: CGFloat = 0.50
    @State private var show3DGSSimulationTint: Bool = true
    @State private var isHoveringDivider: Bool = false

    public init(galleryStore: GalleryStore, coordinator: StudioCoordinator) {
        self.galleryStore = galleryStore
        self.coordinator = coordinator
    }

    public var body: some View {
        VStack(spacing: 12) {
            // Top Controls Bar: Preset Pair Switcher & Split Mode Toggle
            headerControlBar

            // Main Split-Screen Synchronized Viewport
            if let pair = galleryStore.selectedABPair ?? galleryStore.abPairs.first {
                GeometryReader { geo in
                    ZStack {
                        // Bottom Layer (Full Rect): AFTER — M1 Max RIFE 1920×1080 @ 60fps Enhanced Video
                        BareAVPlayerLayerView(player: syncController.enhancedPlayer)
                            .frame(width: geo.size.width, height: geo.size.height)

                        // Top Clipped Layer: BEFORE — Raw Lyra 2.0 832×480 @ 16fps / 3DGS Reconstruction
                        ZStack {
                            BareAVPlayerLayerView(player: syncController.rawPlayer)
                                .frame(width: geo.size.width, height: geo.size.height)

                            // Optional 3DGS Point-Cloud / Wireframe Overlay to mirror @NVIDIAAI's 3DGS vs Video split
                            if show3DGSSimulationTint && splitStyle == .diagonal3DGS {
                                GaussianPointCloudOverlay()
                                    .allowsHitTesting(false)
                            }
                        }
                        .clipShape(
                            LeftOrTopLeftClipShape(
                                splitFraction: splitFraction,
                                style: splitStyle
                            )
                        )

                        // Interactive Split Divider Line + Handle
                        splitDividerOverlay(in: geo.size)

                        // Top-Left & Bottom-Right Official Cinema HUD Badges
                        hudCornerBadges(pair: pair)
                    }
                    .background(Color.black)
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .stroke(Color.white.opacity(0.12), lineWidth: 1)
                    )
                    .contentShape(Rectangle())
                    .gesture(
                        DragGesture(minimumDistance: 0)
                            .onChanged { value in
                                let frac = value.location.x / max(1, geo.size.width)
                                splitFraction = min(0.92, max(0.08, frac))
                            }
                    )
                }
                .onAppear {
                    syncController.loadPair(pair)
                }
                .onChange(of: pair.id) {
                    syncController.loadPair(pair)
                }

                // Bottom Synchronized Timeline & Slow-Motion Frame Verification Bar
                playbackTransportBar(pair: pair)
            } else {
                emptyABCompareState
            }
        }
        .padding(14)
        .background(Color(red: 0.05, green: 0.06, blue: 0.09))
    }

    // MARK: - Subviews

    private var headerControlBar: some View {
        HStack(spacing: 10) {
            // Pair Selector Pills
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(galleryStore.abPairs) { pair in
                        let isSelected = (galleryStore.selectedABPair?.id ?? galleryStore.abPairs.first?.id) == pair.id
                        Button {
                            galleryStore.selectedABPair = pair
                        } label: {
                            HStack(spacing: 6) {
                                Image(systemName: pair.title.contains("天空之城") ? "cloud.sun.fill" : "building.columns.fill")
                                    .font(.system(size: 11))
                                Text(pair.title)
                                    .font(.system(size: 11.5, weight: .semibold))
                            }
                            .foregroundColor(isSelected ? .white : .white.opacity(0.7))
                            .padding(.horizontal, 11)
                            .padding(.vertical, 6)
                            .background(
                                RoundedRectangle(cornerRadius: 8, style: .continuous)
                                    .fill(isSelected ? Color.cyan.opacity(0.26) : Color.white.opacity(0.06))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                                            .stroke(isSelected ? Color.cyan.opacity(0.7) : Color.white.opacity(0.08), lineWidth: 1)
                                    )
                            )
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            Spacer()

            // Toggle 3DGS Point-Cloud Grid Overlay
            if splitStyle == .diagonal3DGS {
                Toggle(isOn: $show3DGSSimulationTint) {
                    Text("3DGS 高斯网格")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(.white.opacity(0.8))
                }
                .toggleStyle(.checkbox)
            }

            // Split Style Segmented Picker (Diagonal 3DGS `/` vs Vertical `┃`)
            HStack(spacing: 4) {
                ForEach(ABSplitStyle.allCases) { style in
                    let active = splitStyle == style
                    Button {
                        withAnimation(.spring(response: 0.28, dampingFraction: 0.82)) {
                            splitStyle = style
                        }
                    } label: {
                        Text(style.title)
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundColor(active ? .black : .white.opacity(0.8))
                            .padding(.horizontal, 10)
                            .padding(.vertical, 5)
                            .background(
                                RoundedRectangle(cornerRadius: 6, style: .continuous)
                                    .fill(active ? Color.cyan : Color.clear)
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(3)
            .background(Color.white.opacity(0.08))
            .cornerRadius(8)
        }
    }

    @ViewBuilder
    private func splitDividerOverlay(in size: CGSize) -> some View {
        let centerX = size.width * splitFraction
        let centerY = size.height * 0.5

        ZStack {
            // Line Path
            Canvas { context, canvasSize in
                var line = Path()
                switch splitStyle {
                case .vertical:
                    line.move(to: CGPoint(x: centerX, y: 0))
                    line.addLine(to: CGPoint(x: centerX, y: canvasSize.height))
                case .diagonal3DGS:
                    let slant = canvasSize.width * 0.24
                    let topX = centerX + slant
                    let bottomX = centerX - slant
                    line.move(to: CGPoint(x: topX, y: 0))
                    line.addLine(to: CGPoint(x: bottomX, y: canvasSize.height))
                }
                context.stroke(
                    line,
                    with: .color(Color.white.opacity(0.92)),
                    style: StrokeStyle(lineWidth: 2.5, lineCap: .round)
                )
            }
            .allowsHitTesting(false)

            // Center Grab Handle Pill
            ZStack {
                Circle()
                    .fill(Color.black.opacity(0.78))
                    .frame(width: 38, height: 38)
                    .overlay(
                        Circle()
                            .stroke(Color.white, lineWidth: 2)
                    )
                    .shadow(color: .black.opacity(0.6), radius: 8)

                Image(systemName: splitStyle == .diagonal3DGS ? "arrow.up.left.and.arrow.down.right" : "arrow.left.and.right")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(.cyan)
            }
            .position(x: centerX, y: centerY)
            .allowsHitTesting(false)
        }
    }

    @ViewBuilder
    private func hudCornerBadges(pair: ABComparePair) -> some View {
        VStack {
            HStack(alignment: .top) {
                // Top-Left Badge: 3DGS / Raw 832×480 @ 16fps
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 6) {
                        Text(splitStyle == .diagonal3DGS ? "3DGS" : "RAW 原始流")
                            .font(.system(size: 13, weight: .heavy, design: .rounded))
                            .foregroundColor(.white)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(Color.orange.opacity(0.85))
                            .cornerRadius(5)

                        Text("832×480 · 16 fps")
                            .font(.system(size: 11, weight: .bold, design: .monospaced))
                            .foregroundColor(.white.opacity(0.9))
                    }
                    Text("DA3 + MoGe 深度点云 · 未插帧原片 (\(pair.rawItem.fileSizeBadge))")
                        .font(.system(size: 10))
                        .foregroundColor(.white.opacity(0.68))
                }
                .padding(10)
                .background(.ultraThinMaterial)
                .background(Color.black.opacity(0.55))
                .cornerRadius(9)

                Spacer()

                // Quality Jump Summary Pill in Top-Right
                HStack(spacing: 8) {
                    Label("3.75× 帧率跃升 (16→60fps)", systemImage: "Waveform.path.ecg")
                        .font(.system(size: 10.5, weight: .bold))
                        .foregroundColor(.cyan)
                    Text("·")
                        .foregroundColor(.white.opacity(0.4))
                    Text("5.2× 像素密度 (1080p)")
                        .font(.system(size: 10.5, weight: .bold))
                        .foregroundColor(.green)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Color.black.opacity(0.68))
                .cornerRadius(8)
            }

            Spacer()

            HStack(alignment: .bottom) {
                Text("💡 左右拖动画面任意位置可实时移动分屏切线")
                    .font(.system(size: 10.5, weight: .medium))
                    .foregroundColor(.white.opacity(0.65))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(Color.black.opacity(0.55))
                    .cornerRadius(6)

                Spacer()

                // Bottom-Right Badge: Video / M1 Max RIFE 1080p 60fps
                VStack(alignment: .trailing, spacing: 3) {
                    HStack(spacing: 6) {
                        Text("1920×1080 · 60 fps")
                            .font(.system(size: 11, weight: .bold, design: .monospaced))
                            .foregroundColor(.cyan)

                        Text(splitStyle == .diagonal3DGS ? "Video" : "M1 Max 精修")
                            .font(.system(size: 13, weight: .heavy, design: .rounded))
                            .foregroundColor(.black)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(Color.cyan)
                            .cornerRadius(5)
                    }
                    Text("Lyra 2.0 + Apple Silicon RIFE ×\(pair.interpFactor) · \(Int(pair.speedFactor))× 丝滑穿梭 (\(pair.enhancedItem.fileSizeBadge))")
                        .font(.system(size: 10))
                        .foregroundColor(.white.opacity(0.75))
                }
                .padding(10)
                .background(.ultraThinMaterial)
                .background(Color.black.opacity(0.6))
                .cornerRadius(9)
            }
        }
        .padding(14)
        .allowsHitTesting(false)
    }

    @ViewBuilder
    private func playbackTransportBar(pair: ABComparePair) -> some View {
        HStack(spacing: 14) {
            Button {
                syncController.togglePlayPause()
            } label: {
                Image(systemName: syncController.isPlaying ? "pause.fill" : "play.fill")
                    .font(.system(size: 14, weight: .bold))
                    .foregroundColor(.black)
                    .frame(width: 34, height: 34)
                    .background(Color.cyan)
                    .clipShape(Circle())
            }
            .buttonStyle(.plain)
            .keyboardShortcut(.space, modifiers: [])

            // Timecode Readout
            Text(
                String(
                    format: "%05.2fs / %05.2fs",
                    syncController.currentTimeSeconds,
                    syncController.durationSeconds
                )
            )
            .font(.system(size: 11, weight: .semibold, design: .monospaced))
            .foregroundColor(.white.opacity(0.85))
            .frame(width: 115, alignment: .leading)

            // Scrubber Slider
            Slider(
                value: Binding(
                    get: { syncController.normalizedProgress },
                    set: { newVal in syncController.seek(toNormalized: newVal) }
                ),
                in: 0.0...1.0
            )
            .tint(.cyan)

            // Slow-Motion Frame Verification Rate Picker
            HStack(spacing: 4) {
                Text("慢放验帧:")
                    .font(.system(size: 10.5))
                    .foregroundColor(.white.opacity(0.6))

                ForEach([Float(0.25), Float(0.5), Float(1.0)], id: \.self) { rate in
                    let active = abs(syncController.playbackRate - rate) < 0.05
                    Button {
                        syncController.setRate(rate)
                    } label: {
                        Text(rate == 0.25 ? "0.25× 逐帧" : (rate == 0.5 ? "0.5× 慢放" : "1.0× 原速"))
                            .font(.system(size: 10.5, weight: .semibold, design: .monospaced))
                            .foregroundColor(active ? .black : .white.opacity(0.8))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(active ? Color.cyan : Color.white.opacity(0.08))
                            .cornerRadius(5)
                    }
                    .buttonStyle(.plain)
                }
            }

            Button {
                coordinator.revealInFinder(pair.enhancedItem)
            } label: {
                Label("Finder 定位成片", systemImage: "folder.fill")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.white.opacity(0.85))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(Color.white.opacity(0.08))
                    .cornerRadius(7)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(Color(red: 0.08, green: 0.10, blue: 0.15))
                .overlay(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .stroke(Color.white.opacity(0.08), lineWidth: 1)
                )
        )
    }

    private var emptyABCompareState: some View {
        VStack(spacing: 12) {
            Image(systemName: "rectangle.split.2x1.slash.fill")
                .font(.system(size: 40))
                .foregroundColor(.cyan.opacity(0.6))
            Text("暂无可对比的 Raw vs 1080p60 视频对")
                .font(.system(size: 15, weight: .bold))
                .foregroundColor(.white)
            Text("请先在「M1 Max 超分」页对任意 Lyra 3D 视频执行 RIFE 60fps 超分，系统将自动配对。")
                .font(.system(size: 12))
                .foregroundColor(.white.opacity(0.6))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - Subtle 3DGS Point-Cloud / Splat Lattice Visual Overlay for Top-Left Split

private struct GaussianPointCloudOverlay: View {
    var body: some View {
        Canvas { context, size in
            let step: CGFloat = 22
            var y: CGFloat = 10
            while y < size.height {
                var x: CGFloat = 10
                while x < size.width {
                    let rect = CGRect(x: x - 1.2, y: y - 1.2, width: 2.4, height: 1.5)
                    context.fill(Path(ellipseIn: rect), with: .color(Color.cyan.opacity(0.18)))
                    x += step
                }
                y += step
            }
        }
    }
}
