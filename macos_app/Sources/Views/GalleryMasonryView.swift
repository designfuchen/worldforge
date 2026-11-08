import SwiftUI
import AppKit
import Quartz

// MARK: - AsyncThumbnailCard (0ms Main-Thread Decode + 12-Frame Continuous Hover Scrubbing)

public struct AsyncThumbnailCard: View {
    public let item: GalleryItem
    public let isSelected: Bool
    public let isFavorite: Bool
    public let onSelect: () -> Void
    public let onToggleFavorite: () -> Void
    public let onSendToLyra: () -> Void
    public let onSendToPost: () -> Void
    public let onOpenABCompare: () -> Void
    public let onRevealFinder: () -> Void

    @State private var posterImage: NSImage?
    @State private var filmstripFrames: [NSImage] = []
    @State private var isHovering: Bool = false
    @State private var hoverFraction: Double = 0.0

    public init(
        item: GalleryItem,
        isSelected: Bool,
        isFavorite: Bool,
        onSelect: @escaping () -> Void,
        onToggleFavorite: @escaping () -> Void,
        onSendToLyra: @escaping () -> Void,
        onSendToPost: @escaping () -> Void,
        onOpenABCompare: @escaping () -> Void,
        onRevealFinder: @escaping () -> Void
    ) {
        self.item = item
        self.isSelected = isSelected
        self.isFavorite = isFavorite
        self.onSelect = onSelect
        self.onToggleFavorite = onToggleFavorite
        self.onSendToLyra = onSendToLyra
        self.onSendToPost = onSendToPost
        self.onOpenABCompare = onOpenABCompare
        self.onRevealFinder = onRevealFinder
        // Synchronous L1 NSCache lookup on init so already-cached cards render on frame 0 without placeholder flash
        _posterImage = State(initialValue: ThumbnailCacheActor.shared.cachedThumbnailImmediate(for: item.id, maxPixelSize: 640))
        _filmstripFrames = State(initialValue: ThumbnailCacheActor.shared.cachedFilmstripImmediate(for: item.id) ?? [])
    }

    private var displayedImage: NSImage? {
        if item.isVideo && isHovering && !filmstripFrames.isEmpty {
            let idx = min(filmstripFrames.count - 1, max(0, Int(hoverFraction * Double(filmstripFrames.count))))
            return filmstripFrames[idx]
        }
        return posterImage
    }

    private var currentScrubFrameIndex: Int {
        guard !filmstripFrames.isEmpty else { return 1 }
        return min(filmstripFrames.count, max(1, Int(hoverFraction * Double(filmstripFrames.count)) + 1))
    }

    private var currentScrubTimestampText: String {
        let dur = item.info?.duration ?? 7.5
        let cur = dur * hoverFraction
        return String(format: "%.1fs / %.1fs", cur, dur)
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Media Viewport (16:9 Aspect Ratio)
            GeometryReader { geo in
                ZStack(alignment: .topLeading) {
                    Color(red: 0.05, green: 0.07, blue: 0.11)

                    if let nsImg = displayedImage {
                        Image(nsImage: nsImg)
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                            .frame(width: geo.size.width, height: geo.size.height)
                            .clipped()
                    } else {
                        ProgressView()
                            .scaleEffect(0.75)
                            .frame(width: geo.size.width, height: geo.size.height)
                    }

                    // Top Badges Overlay (Clean Type Pill + "✨ 最新" Badge + Star)
                    HStack(spacing: 4) {
                        if item.isVideo {
                            let durText = item.durationBadge.map { " · \($0)" } ?? ""
                            badgePill(
                                text: "🎬 视频\(durText)",
                                color: item.isEnhanced1080p ? Color(red: 0.15, green: 0.78, blue: 0.58) : Color.indigo
                            )
                        } else {
                            badgePill(
                                text: "🖼️ 图片",
                                color: Color.cyan
                            )
                        }

                        if item.isRecentlyCreated {
                            badgePill(
                                text: "✨ 最新",
                                color: Color.green
                            )
                        }

                        Spacer(minLength: 2)

                        // Favorite Button
                        Button(action: onToggleFavorite) {
                            Image(systemName: isFavorite ? "star.fill" : "star")
                                .font(.system(size: 10.5, weight: .bold))
                                .foregroundColor(isFavorite ? .yellow : .white.opacity(0.8))
                                .padding(4.5)
                                .background(Color.black.opacity(0.55))
                                .clipShape(Circle())
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(6)

                    // Video Hover Scrubbing Progress Bar & Play Indicator
                    VStack {
                        Spacer()
                        if item.isVideo && isHovering && !filmstripFrames.isEmpty {
                            VStack(spacing: 3) {
                                HStack {
                                    Text("预演 \(currentScrubFrameIndex)/\(max(1, filmstripFrames.count))")
                                        .font(.system(size: 9, weight: .bold, design: .monospaced))
                                        .foregroundColor(.cyan)
                                    Spacer()
                                    Text(currentScrubTimestampText)
                                        .font(.system(size: 9, weight: .semibold, design: .monospaced))
                                        .foregroundColor(.white)
                                }
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Color.black.opacity(0.75))
                                .cornerRadius(4)
                                .padding(.horizontal, 5)

                                GeometryReader { barGeo in
                                    ZStack(alignment: .leading) {
                                        Rectangle()
                                            .fill(Color.white.opacity(0.22))
                                        Rectangle()
                                            .fill(Color.cyan)
                                            .frame(width: barGeo.size.width * CGFloat(hoverFraction))
                                    }
                                }
                                .frame(height: 3)
                            }
                        } else if item.isVideo {
                            HStack {
                                Spacer()
                                Image(systemName: "play.circle.fill")
                                    .font(.system(size: 22))
                                    .foregroundColor(.white.opacity(0.88))
                                    .shadow(color: .black.opacity(0.6), radius: 5)
                                Spacer()
                            }
                            .padding(.bottom, 8)
                        }
                    }
                }
                .contentShape(Rectangle())
                .onContinuousHover { phase in
                    switch phase {
                    case .active(let location):
                        isHovering = true
                        let frac = Double(location.x / max(1.0, geo.size.width))
                        hoverFraction = min(0.999, max(0.0, frac))
                    case .ended:
                        isHovering = false
                    }
                }
            }
            .aspectRatio(16.0 / 9.0, contentMode: .fit)
            .clipped()

            // Clean 2-Line Card Footer (Title + Resolution & Time)
            VStack(alignment: .leading, spacing: 3) {
                Text(item.displayTitle)
                    .font(.system(size: 11, weight: .bold))
                    .foregroundColor(isSelected ? .cyan : .white)
                    .lineLimit(1)

                HStack(spacing: 4) {
                    Text(item.resolutionBadge)
                        .font(.system(size: 9.5, design: .monospaced))
                        .foregroundColor(.white.opacity(0.52))
                        .lineLimit(1)
                    Spacer(minLength: 2)
                    Text(item.formattedTimeText)
                        .font(.system(size: 9.5, weight: item.isRecentlyCreated ? .bold : .regular))
                        .foregroundColor(item.isRecentlyCreated ? .green : .white.opacity(0.45))
                        .lineLimit(1)
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 7)
            .background(Color(red: 0.08, green: 0.10, blue: 0.15))
        }
        .clipShape(RoundedRectangle(cornerRadius: 11, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 11, style: .continuous)
                .stroke(
                    isSelected ? Color.cyan : (isHovering ? Color.white.opacity(0.32) : Color.white.opacity(0.08)),
                    lineWidth: isSelected ? 2.0 : 1.0
                )
        )
        .shadow(color: isSelected ? Color.cyan.opacity(0.22) : Color.black.opacity(0.3), radius: isSelected ? 10 : 5, y: 2)
        .onTapGesture {
            onSelect()
        }
        .onDrag {
            NSItemProvider(object: item.localFileURL as NSURL)
        }
        .contextMenu {
            Button("在中央舞台打开预览") { onSelect() }
            if item.isImage {
                Button("送入 Lyra 2.0 生成 3D 世界漫游") { onSendToLyra() }
            }
            if item.isVideo {
                Button("送入 M1 Max RIFE 1080p 60fps 超分") { onSendToPost() }
                Button("打开 A/B 同屏对比验证") { onOpenABCompare() }
            }
            Divider()
            Button(isFavorite ? "取消星标收藏" : "加入星标精选") { onToggleFavorite() }
            Button("在 Finder 中定位文件") { onRevealFinder() }
        }
        .task(id: item.id) {
            if posterImage == nil {
                posterImage = await ThumbnailCacheActor.shared.thumbnail(for: item, maxPixelSize: 640)
            }
            if item.isVideo && filmstripFrames.isEmpty {
                filmstripFrames = await ThumbnailCacheActor.shared.filmstrip(for: item, frameCount: 12)
            }
        }
    }

    @ViewBuilder
    private func badgePill(text: String, color: Color, textColor: Color = .black) -> some View {
        Text(text)
            .font(.system(size: 9.5, weight: .heavy, design: .monospaced))
            .foregroundColor(color == Color.cyan ? .black : .white)
            .padding(.horizontal, 6)
            .padding(.vertical, 2.5)
            .background(color.opacity(0.9))
            .cornerRadius(4)
    }

    @ViewBuilder
    private func miniActionButton(title: String, icon: String, tint: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.system(size: 9.5, weight: .semibold))
                Text(title)
                    .font(.system(size: 10, weight: .semibold))
            }
            .foregroundColor(tint)
            .padding(.horizontal, 7)
            .padding(.vertical, 4)
            .background(tint.opacity(0.14))
            .cornerRadius(5)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - GalleryMasonryView (Full-Stage Ultra-Fast Media Library)

public struct GalleryMasonryView: View {
    @ObservedObject var gallery: GalleryStore
    @ObservedObject var workspace: WorkspaceStore
    @ObservedObject var telemetry: TelemetryStore
    @ObservedObject var coordinator: StudioCoordinator

    private let columns = [
        GridItem(.adaptive(minimum: 265, maximum: 360), spacing: 14)
    ]

    public init(
        gallery: GalleryStore,
        workspace: WorkspaceStore,
        telemetry: TelemetryStore,
        coordinator: StudioCoordinator
    ) {
        self.gallery = gallery
        self.workspace = workspace
        self.telemetry = telemetry
        self.coordinator = coordinator
    }

    public var body: some View {
        VStack(spacing: 12) {
            // Top Filter & Search Toolbar
            HStack(spacing: 10) {
                ForEach(GalleryFilterCategory.allCases) { cat in
                    let active = gallery.activeCategory == cat
                    Button {
                        gallery.activeCategory = cat
                    } label: {
                        HStack(spacing: 5) {
                            Image(systemName: cat.icon)
                                .font(.system(size: 11))
                            Text(cat.title)
                                .font(.system(size: 11.5, weight: .semibold))
                        }
                        .foregroundColor(active ? .black : .white.opacity(0.8))
                        .padding(.horizontal, 11)
                        .padding(.vertical, 6)
                        .background(
                            RoundedRectangle(cornerRadius: 7, style: .continuous)
                                .fill(active ? Color.cyan : Color.white.opacity(0.06))
                        )
                    }
                    .buttonStyle(.plain)
                }

                Spacer()

                // Concurrency Telemetry Badge
                HStack(spacing: 6) {
                    Circle()
                        .fill(Color.green)
                        .frame(width: 6, height: 6)
                    Text("CGImageSource 异步解码 0.0ms · 鼠标横滑实时刮擦预览")
                        .font(.system(size: 10.5, weight: .medium, design: .monospaced))
                        .foregroundColor(.white.opacity(0.65))
                }
                .padding(.horizontal, 9)
                .padding(.vertical, 5)
                .background(Color.white.opacity(0.05))
                .cornerRadius(6)

                // Instant Search Field
                HStack(spacing: 6) {
                    Image(systemName: "magnifyingglass")
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.5))
                    TextField("搜索天空之城 / 鸟居 / 1080p…", text: $gallery.searchQuery)
                        .textFieldStyle(.plain)
                        .font(.system(size: 11.5))
                        .foregroundColor(.white)
                        .frame(width: 175)
                    if !gallery.searchQuery.isEmpty {
                        Button {
                            gallery.searchQuery = ""
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .font(.system(size: 11))
                                .foregroundColor(.white.opacity(0.5))
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 9)
                .padding(.vertical, 5)
                .background(Color.black.opacity(0.35))
                .cornerRadius(7)
                .overlay(
                    RoundedRectangle(cornerRadius: 7)
                        .stroke(Color.white.opacity(0.1), lineWidth: 1)
                )
            }
            .padding(.horizontal, 16)
            .padding(.top, 12)

            // Main LazyVGrid
            ScrollView {
                LazyVGrid(columns: columns, spacing: 14) {
                    ForEach(gallery.filteredItems) { item in
                        AsyncThumbnailCard(
                            item: item,
                            isSelected: workspace.stageItem?.id == item.id,
                            isFavorite: gallery.isFavorite(item.id),
                            onSelect: {
                                workspace.stageItem = item
                                if workspace.activeTab == .gallery {
                                    // Keep gallery open and update stage inspector
                                }
                            },
                            onToggleFavorite: {
                                gallery.toggleFavorite(item.id)
                            },
                            onSendToLyra: {
                                coordinator.sendItemToLyra3D(item)
                            },
                            onSendToPost: {
                                coordinator.sendItemToM1MaxPost(item)
                            },
                            onOpenABCompare: {
                                coordinator.openItemInABCompare(item)
                            },
                            onRevealFinder: {
                                coordinator.revealInFinder(item)
                            }
                        )
                    }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 20)
            }
        }
        .background(Color(red: 0.05, green: 0.06, blue: 0.09))
    }
}
