import SwiftUI
import AVKit
import AVFoundation
import WebKit
import AppKit

// MARK: - Native AVPlayerView Wrapper for Center Stage Video Playback

public struct NativeStageVideoPlayer: NSViewRepresentable {
    public let url: URL

    public init(url: URL) {
        self.url = url
    }

    public func makeNSView(context: Context) -> AVPlayerView {
        let pv = AVPlayerView()
        pv.controlsStyle = .floating
        pv.videoGravity = .resizeAspect
        pv.allowsPictureInPicturePlayback = true
        let player = AVPlayer(url: url)
        player.isMuted = true
        pv.player = player
        context.coordinator.bindPlayer(player, url: url)
        player.play()
        return pv
    }

    public func updateNSView(_ nsView: AVPlayerView, context: Context) {
        if context.coordinator.currentURL != url {
            nsView.player?.pause()
            let player = AVPlayer(url: url)
            player.isMuted = true
            nsView.player = player
            context.coordinator.bindPlayer(player, url: url)
            player.play()
        }
    }

    public func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    public final class Coordinator {
        var currentURL: URL?
        private var loopObserver: NSObjectProtocol?

        func bindPlayer(_ player: AVPlayer, url: URL) {
            currentURL = url
            if let loopObserver {
                NotificationCenter.default.removeObserver(loopObserver)
            }
            loopObserver = NotificationCenter.default.addObserver(
                forName: .AVPlayerItemDidPlayToEndTime,
                object: player.currentItem,
                queue: .main
            ) { _ in
                player.seek(to: .zero)
                player.play()
            }
        }

        deinit {
            if let loopObserver {
                NotificationCenter.default.removeObserver(loopObserver)
            }
        }
    }
}

// MARK: - Embedded WebKit Studio View (127.0.0.1:7788)

public struct EmbeddedWebStudioView: NSViewRepresentable {
    public let url: URL

    public func makeNSView(context: Context) -> WKWebView {
        let cfg = WKWebViewConfiguration()
        let wv = WKWebView(frame: .zero, configuration: cfg)
        wv.setValue(false, forKey: "drawsBackground")
        wv.load(URLRequest(url: url))
        return wv
    }

    public func updateNSView(_ nsView: WKWebView, context: Context) {}
}

// MARK: - MainStudioWindow (Ultra-Clean 3-Zone Pro Studio: Left Creation | Center Stage | Right Unified Media Library)

public struct MainStudioWindow: View {
    @ObservedObject var coordinator: StudioCoordinator
    @ObservedObject var telemetry: TelemetryStore
    @ObservedObject var modelCenter: ModelCenterStore
    @ObservedObject var workspace: WorkspaceStore
    @ObservedObject var gallery: GalleryStore
    @ObservedObject var jobQueue: JobQueueStore

    @State private var stageDecodedImage: NSImage?
    @State private var showInlineImageAddField: Bool = false
    @State private var showInlineVideoAddField: Bool = false
    @State private var inlineImageRepoInput: String = ""
    @State private var inlineVideoRepoInput: String = ""

    public init(coordinator: StudioCoordinator) {
        self.coordinator = coordinator
        self.telemetry = coordinator.telemetry
        self.modelCenter = coordinator.modelCenter
        self.workspace = coordinator.workspace
        self.gallery = coordinator.gallery
        self.jobQueue = coordinator.jobQueue
    }

    public var body: some View {
        ZStack(alignment: .top) {
            Color(red: 0.04, green: 0.05, blue: 0.08)
                .ignoresSafeArea()

            VStack(spacing: 0) {
                // 1. Ultra-Clean Top Header Bar (Zero Text Wrapping, 4 Spacious Modes)
                topStudioHeaderBar

                Divider().background(Color.white.opacity(0.08))

                // 2. Clean 3-Zone Main Layout:
                //    [Left: Creation Studio 340px] | [Center: Full-Height Stage] | [Right: 🗂️ Unified Media Library 390px]
                HStack(spacing: 0) {
                    leftCreationColumn
                        .frame(width: 340)

                    Divider().background(Color.white.opacity(0.08))

                    centerStageColumn
                        .frame(maxWidth: .infinity, maxHeight: .infinity)

                    Divider().background(Color.white.opacity(0.08))

                    unifiedMediaLibrarySidebar
                        .frame(width: 390)
                }
            }

            // Floating Toast Notification Banner
            if let banner = jobQueue.toastBanner {
                HStack(spacing: 8) {
                    Image(systemName: banner.level == "error" ? "exclamationmark.triangle.fill" : "checkmark.seal.fill")
                        .foregroundColor(banner.level == "error" ? .red : .cyan)
                    Text(banner.text)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(.white)
                        .lineLimit(1)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 9)
                .background(Color(red: 0.10, green: 0.13, blue: 0.20).opacity(0.96))
                .clipShape(Capsule())
                .overlay(Capsule().stroke(Color.cyan.opacity(0.55), lineWidth: 1))
                .shadow(color: .black.opacity(0.5), radius: 12, y: 4)
                .padding(.top, 56)
                .transition(.move(edge: .top).combined(with: .opacity))
            }
        }
        .preferredColorScheme(.dark)
        .sheet(isPresented: $workspace.showModelCenterSheet) {
            ModelCenterSheetView(modelCenter: modelCenter, coordinator: coordinator)
        }
        .sheet(isPresented: $workspace.showHardwareAndLogSheet) {
            HardwareAndLogSheetView(
                telemetry: telemetry,
                modelCenter: modelCenter,
                jobQueue: jobQueue,
                coordinator: coordinator
            )
        }
    }

    // MARK: - 1. Ultra-Clean Top Studio Header Bar (Never Wraps Text!)

    private var topStudioHeaderBar: some View {
        HStack(spacing: 14) {
            // Brand Logo & Title
            HStack(spacing: 9) {
                ZStack {
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .fill(
                            LinearGradient(
                                colors: [Color.cyan, Color(red: 0.39, green: 0.40, blue: 0.95)],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 28, height: 28)
                    Image(systemName: "cube.transparent.fill")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundColor(.black)
                }

                HStack(spacing: 6) {
                    Text("WorldForge 世界工坊")
                        .font(.system(size: 14, weight: .heavy, design: .rounded))
                        .foregroundColor(.white)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                    Text("STUDIO")
                        .font(.system(size: 9, weight: .black, design: .monospaced))
                        .foregroundColor(.black)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 2)
                        .background(Color.cyan)
                        .cornerRadius(4)
                        .fixedSize(horizontal: true, vertical: false)
                }
            }

            Divider()
                .frame(height: 20)
                .background(Color.white.opacity(0.1))

            // 4 Spacious Primary Navigation Tabs (Cmd+1..4) — Guaranteed Single-Line!
            HStack(spacing: 6) {
                ForEach(StudioTab.primaryTabs) { tab in
                    let isSelected = (workspace.activeTab == tab)
                        || (tab == .post && workspace.activeTab == .abCompare)
                    Button {
                        withAnimation(.easeInOut(duration: 0.15)) {
                            workspace.activeTab = tab
                        }
                    } label: {
                        Text(tab.title)
                            .font(.system(size: 12.5, weight: isSelected ? .heavy : .semibold))
                            .foregroundColor(isSelected ? .black : .white.opacity(0.82))
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 6.5)
                            .background(
                                RoundedRectangle(cornerRadius: 8, style: .continuous)
                                    .fill(isSelected ? Color.cyan : Color.white.opacity(0.05))
                            )
                    }
                    .buttonStyle(.plain)
                    .keyboardShortcut(KeyEquivalent(tab.shortcutKey), modifiers: [.command])
                }
            }

            Spacer(minLength: 12)

            // Right Side: Clean Hardware & Terminal Status Button (Opens Sheet)
            Button {
                workspace.showHardwareAndLogSheet = true
            } label: {
                HStack(spacing: 6) {
                    Circle()
                        .fill(telemetry.isRemoteConnected ? Color.green : (telemetry.daemonOnline ? Color.cyan : Color.orange))
                        .frame(width: 7, height: 7)
                    Text(telemetry.isRemoteConnected ? "已连接 \(telemetry.gpuDisplayName) · 算力与终端" : "算力连接与终端日志")
                        .font(.system(size: 11.5, weight: .semibold))
                        .foregroundColor(.white.opacity(0.9))
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                    if jobQueue.activeJobsCount > 0 {
                        Text("\(jobQueue.activeJobsCount) 运行中")
                            .font(.system(size: 9.5, weight: .heavy, design: .monospaced))
                            .foregroundColor(.black)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.cyan)
                            .cornerRadius(4)
                            .fixedSize(horizontal: true, vertical: false)
                    }
                }
                .padding(.horizontal, 11)
                .padding(.vertical, 6)
                .background(Color.white.opacity(0.07))
                .cornerRadius(8)
            }
            .buttonStyle(.plain)

            // Model Center Button
            Button {
                workspace.showModelCenterSheet = true
            } label: {
                HStack(spacing: 5) {
                    Text("📦 模型中心")
                        .font(.system(size: 11.5, weight: .semibold))
                        .foregroundColor(.white.opacity(0.9))
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                }
                .padding(.horizontal, 11)
                .padding(.vertical, 6)
                .background(Color.white.opacity(0.07))
                .cornerRadius(8)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 9)
        .background(Color(red: 0.06, green: 0.08, blue: 0.12))
    }

    // MARK: - 2. Left Column (340px): Clean Creation Panel + Pinned Bottom Generate Bar

    private var leftCreationColumn: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    switch workspace.activeTab {
                    case .image:
                        qwen2KImageInspector
                    case .video:
                        videoGenerationInspector
                    case .world:
                        lyra3DWorldInspector
                    case .post, .abCompare:
                        m1MaxPostInspector
                    default:
                        qwen2KImageInspector
                    }
                }
                .padding(14)
            }

            Divider().background(Color.white.opacity(0.08))

            // Pinned Always-Visible Primary Generate Bar at Bottom of Left Column
            pinnedLeftBottomGenerateBar
        }
        .background(Color(red: 0.06, green: 0.07, blue: 0.11))
    }

    private var pinnedLeftBottomGenerateBar: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Live Job Progress Banner if any task is active
            if workspace.isSubmitting || jobQueue.remoteJobs.contains(where: \.isActive) || jobQueue.localTasks.contains(where: \.isActive) {
                let activeRemote = jobQueue.remoteJobs.first(where: \.isActive)
                let activeLocal = jobQueue.localTasks.first(where: \.isActive)
                let pct = Int(min(1.0, max(0.05, activeRemote?.progress ?? activeLocal?.progress ?? 0.1)) * 100)
                let stage = activeRemote?.stage ?? (activeLocal != nil ? "M1 Max 硬件超分插帧中…" : "正在提交至 GPU…")

                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        ProgressView()
                            .scaleEffect(0.6)
                            .tint(.cyan)
                        Text("⚡ 正在生成 \(pct)% · \(stage)")
                            .font(.system(size: 10.5, weight: .bold))
                            .foregroundColor(.cyan)
                            .lineLimit(1)
                        Spacer()
                    }
                    ProgressView(value: Double(pct) / 100.0)
                        .tint(.cyan)
                }
                .padding(8)
                .background(Color.cyan.opacity(0.1))
                .cornerRadius(7)
            }

            // Huge 46pt Primary Generate Button (Always Visible!)
            Button {
                Task { await coordinator.submitActiveWorkspaceTask() }
            } label: {
                HStack(spacing: 8) {
                    if workspace.isSubmitting {
                        ProgressView()
                            .scaleEffect(0.75)
                            .tint(.black)
                    } else {
                        Image(systemName: "sparkles")
                            .font(.system(size: 14, weight: .black))
                            .foregroundColor(.black)
                    }
                    VStack(alignment: .leading, spacing: 1) {
                        Text(workspace.isSubmitting ? "正在提交生成任务…" : pinnedGenerateButtonTitle)
                            .font(.system(size: 13.5, weight: .heavy))
                            .foregroundColor(.black)
                            .lineLimit(1)
                        Text(pinnedGenerateButtonSubtitle)
                            .font(.system(size: 9.5, weight: .semibold))
                            .foregroundColor(.black.opacity(0.75))
                            .lineLimit(1)
                    }
                    Spacer()
                    Text("⌘↩")
                        .font(.system(size: 11, weight: .black, design: .monospaced))
                        .foregroundColor(.black.opacity(0.75))
                }
                .padding(.horizontal, 14)
                .frame(maxWidth: .infinity)
                .frame(height: 46)
                .background(
                    LinearGradient(
                        colors: [Color.cyan, Color(red: 0.18, green: 0.88, blue: 0.65)],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                )
                .cornerRadius(10)
                .shadow(color: Color.cyan.opacity(0.35), radius: 10, y: 2)
            }
            .buttonStyle(.plain)
            .keyboardShortcut(.return, modifiers: [.command])
            .disabled(workspace.isSubmitting)
        }
        .padding(12)
        .background(Color(red: 0.05, green: 0.06, blue: 0.10))
    }

    private var pinnedGenerateButtonTitle: String {
        switch workspace.activeTab {
        case .image:
            return "⚡ 立即生成图片"
        case .video:
            return workspace.videoModelId == "breeze-tts-2" ? "🎙️ 立即合成双语语音" : "🎬 立即生成视频"
        case .world:
            return "🧊 立即生成 3D 世界"
        case .post, .abCompare:
            return "⚡ 启动 60fps 极速超分"
        default:
            return "⚡ 立即生成"
        }
    }

    private var pinnedGenerateButtonSubtitle: String {
        switch workspace.activeTab {
        case .image:
            return "\(workspace.selectedCinemaCamera.name) · \(workspace.selectedCinemaCamera.cameraSpec)"
        case .video:
            if workspace.videoModelId == "breeze-tts-2" {
                return "Breeze-TTS-2 · 0 MB 显存 · 30TB 谷歌云盘直连"
            }
            return "\(workspace.selectedCinemaCamera.name) · \(workspace.selectedCameraMovement.name)"
        case .world:
            return "NVIDIA Lyra 2.0 · \(workspace.selectedDurationPreset.title)"
        case .post, .abCompare:
            return "Apple Silicon RIFE ×\(workspace.postInterp) · \(workspace.postScale.uppercased())"
        default:
            return "生成结果将自动展示在中央舞台与右侧素材库"
        }
    }

    // MARK: Mode 1 — 🎨 AI 生图 Inspector

    private var qwen2KImageInspector: some View {
        VStack(alignment: .leading, spacing: 14) {
            // ① 选择生图模型
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Label("① 选择生图模型", systemImage: "cpu.fill")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(.cyan)
                    Spacer()
                    Button {
                        withAnimation(.easeInOut(duration: 0.15)) {
                            showInlineImageAddField.toggle()
                        }
                    } label: {
                        Text(showInlineImageAddField ? "收起" : "+ 添加模型")
                            .font(.system(size: 10.5, weight: .bold))
                            .foregroundColor(.cyan)
                    }
                    .buttonStyle(.plain)
                }

                VStack(spacing: 6) {
                    ForEach(modelCenter.imageModels) { model in
                        let isSelected = workspace.imageModelId == model.id
                            || (workspace.imageModelId == "qwen-image" && model.id == "qwen-image-2.1-turbo")
                        compactModelRow(model: model, isSelected: isSelected) {
                            workspace.imageModelId = model.id
                        }
                    }
                }

                if showInlineImageAddField {
                    HStack(spacing: 6) {
                        TextField("输入 HF 仓库 (如 black-forest-labs/FLUX.1-dev)", text: $inlineImageRepoInput)
                            .textFieldStyle(.roundedBorder)
                            .font(.system(size: 11))
                        Button("添加") {
                            let input = inlineImageRepoInput
                            inlineImageRepoInput = ""
                            showInlineImageAddField = false
                            Task {
                                await coordinator.addCustomModelInline(repoInput: input, forTab: .image)
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(.cyan)
                        .controlSize(.small)
                    }
                    .padding(.top, 2)
                }
            }
            .padding(11)
            .background(RoundedRectangle(cornerRadius: 10).fill(Color(red: 0.08, green: 0.10, blue: 0.15)))

            // ② 画面提示词 + ✨ 电影级扩写 + 8 大殿堂级电影片段库
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Label("② 电影级提示词", systemImage: "sparkles")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(.cyan)
                        .lineLimit(1)
                    Spacer()
                    Button {
                        workspace.enhancePromptWithCinemaMasterpiece(forVideo: false)
                        coordinator.jobQueue.showToast("✨ 已注入专业电影机光学参数 (\(workspace.selectedCinemaCamera.cameraSpec))", level: "success")
                    } label: {
                        Text("✨ 电影级扩写")
                            .font(.system(size: 10, weight: .heavy))
                            .foregroundColor(.black)
                            .padding(.horizontal, 7)
                            .padding(.vertical, 3)
                            .background(Color.cyan)
                            .cornerRadius(5)
                            .fixedSize(horizontal: true, vertical: false)
                    }
                    .buttonStyle(.plain)

                    Button("🎲 随机大片") {
                        if let scene = MasterpieceFilmScenePreset.all.randomElement() {
                            workspace.applyMasterpieceFilmScene(scene, forVideo: false)
                        }
                    }
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.cyan)
                    .buttonStyle(.plain)
                    .fixedSize(horizontal: true, vertical: false)

                    Button("清空") {
                        workspace.t2iPrompt = ""
                    }
                    .font(.system(size: 10))
                    .foregroundColor(.white.opacity(0.55))
                    .buttonStyle(.plain)
                }

                TextEditor(text: $workspace.t2iPrompt)
                    .font(.system(size: 12))
                    .frame(height: 108)
                    .padding(7)
                    .background(Color.black.opacity(0.42))
                    .cornerRadius(8)
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(Color.cyan.opacity(0.32), lineWidth: 1)
                    )

                Text("🎬 殿堂级唯美电影片段（点击自动载入大师提示词与对应电影摄影机）：")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.white.opacity(0.65))
                    .lineLimit(1)

                LazyVGrid(columns: [GridItem(.flexible(), spacing: 6), GridItem(.flexible(), spacing: 6)], spacing: 6) {
                    ForEach(MasterpieceFilmScenePreset.all) { scene in
                        promptChipButton(scene.shortTag) {
                            workspace.applyMasterpieceFilmScene(scene, forVideo: false)
                            coordinator.jobQueue.showToast("🎬 已载入《\(scene.shortTag)》电影分镜与 \(scene.directorBadge) 摄影机", level: "info")
                        }
                    }
                }
            }
            .padding(11)
            .background(RoundedRectangle(cornerRadius: 10).fill(Color(red: 0.08, green: 0.10, blue: 0.15)))

            // ③ 🎥 专业级唯美电影摄影机与光学镜头
            cinemaCameraSelectorSection(includeMovement: false)

            // ④ 画幅比例与风格
            VStack(alignment: .leading, spacing: 9) {
                Label("④ 画幅比例与风格", systemImage: "aspectratio.fill")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(.cyan)

                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 6) {
                    ForEach(AspectPreset.all.prefix(4)) { asp in
                        let active = workspace.selectedAspect.id == asp.id
                        Button {
                            workspace.selectedAspect = asp
                        } label: {
                            Text(asp.name)
                                .font(.system(size: 10.5, weight: .semibold))
                                .foregroundColor(active ? .black : .white.opacity(0.85))
                                .lineLimit(1)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 6)
                                .background(active ? Color.cyan : Color.white.opacity(0.05))
                                .cornerRadius(6)
                        }
                        .buttonStyle(.plain)
                    }
                }

                HStack {
                    Text("艺术风格")
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.75))
                    Spacer()
                    Picker("", selection: $workspace.selectedStyle) {
                        ForEach(StylePreset.all) { style in
                            Text(style.name).tag(style)
                        }
                    }
                    .labelsHidden()
                    .frame(width: 160)
                }

                HStack {
                    Stepper("生成张数: \(workspace.t2iCount) 张", value: $workspace.t2iCount, in: 1...4)
                        .font(.system(size: 11))
                    Spacer()
                }
            }
            .padding(11)
            .background(RoundedRectangle(cornerRadius: 10).fill(Color(red: 0.08, green: 0.10, blue: 0.15)))
        }
    }

    // MARK: Mode 2 — 🎬 AI 视频 Inspector

    private var videoGenerationInspector: some View {
        VStack(alignment: .leading, spacing: 14) {
            // ① 选择视频/语音模型
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Label("① 选择视频/语音模型", systemImage: "film.stack.fill")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(.cyan)
                    Spacer()
                    Button {
                        withAnimation(.easeInOut(duration: 0.15)) {
                            showInlineVideoAddField.toggle()
                        }
                    } label: {
                        Text(showInlineVideoAddField ? "收起" : "+ 添加模型")
                            .font(.system(size: 10.5, weight: .bold))
                            .foregroundColor(.cyan)
                    }
                    .buttonStyle(.plain)
                }

                VStack(spacing: 6) {
                    ForEach(modelCenter.videoModels) { model in
                        let isSelected = workspace.videoModelId == model.id
                        compactModelRow(model: model, isSelected: isSelected) {
                            workspace.videoModelId = model.id
                        }
                    }
                }

                if showInlineVideoAddField {
                    HStack(spacing: 6) {
                        TextField("输入 HF 视频仓库 (支持 /tree/main/)", text: $inlineVideoRepoInput)
                            .textFieldStyle(.roundedBorder)
                            .font(.system(size: 11))
                        Button("添加") {
                            let input = inlineVideoRepoInput
                            inlineVideoRepoInput = ""
                            showInlineVideoAddField = false
                            Task {
                                await coordinator.addCustomModelInline(repoInput: input, forTab: .video)
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(.cyan)
                        .controlSize(.small)
                    }
                    .padding(.top, 2)
                }
            }
            .padding(11)
            .background(RoundedRectangle(cornerRadius: 10).fill(Color(red: 0.08, green: 0.10, blue: 0.15)))

            // ② 视频/语音提示词 + ✨ 电影级扩写 + 8 大殿堂级电影片段库
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Label("② 电影级视频描述", systemImage: "video.badge.plus")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(.cyan)
                        .lineLimit(1)
                    Spacer()
                    Button {
                        workspace.enhancePromptWithCinemaMasterpiece(forVideo: true)
                        coordinator.jobQueue.showToast("✨ 已注入专业电影摄影机与 120fps 唯美慢镜光学参数", level: "success")
                    } label: {
                        Text("✨ 电影级扩写")
                            .font(.system(size: 10, weight: .heavy))
                            .foregroundColor(.black)
                            .padding(.horizontal, 7)
                            .padding(.vertical, 3)
                            .background(Color.cyan)
                            .cornerRadius(5)
                            .fixedSize(horizontal: true, vertical: false)
                    }
                    .buttonStyle(.plain)

                    Button("🎲 随机大片") {
                        if let scene = MasterpieceFilmScenePreset.all.randomElement() {
                            workspace.applyMasterpieceFilmScene(scene, forVideo: true)
                        }
                    }
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.cyan)
                    .buttonStyle(.plain)
                    .fixedSize(horizontal: true, vertical: false)

                    Button("清空") {
                        workspace.videoPrompt = ""
                    }
                    .font(.system(size: 10))
                    .foregroundColor(.white.opacity(0.55))
                    .buttonStyle(.plain)
                }

                TextEditor(text: $workspace.videoPrompt)
                    .font(.system(size: 12))
                    .frame(height: 108)
                    .padding(7)
                    .background(Color.black.opacity(0.42))
                    .cornerRadius(8)
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(Color.cyan.opacity(0.32), lineWidth: 1)
                    )

                Text("🎬 殿堂级唯美电影片段（点击自动载入大师镜头与摄影机配置）：")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.white.opacity(0.65))
                    .lineLimit(1)

                LazyVGrid(columns: [GridItem(.flexible(), spacing: 6), GridItem(.flexible(), spacing: 6)], spacing: 6) {
                    ForEach(MasterpieceFilmScenePreset.all) { scene in
                        promptChipButton(scene.shortTag) {
                            workspace.applyMasterpieceFilmScene(scene, forVideo: true)
                            coordinator.jobQueue.showToast("🎬 已载入《\(scene.shortTag)》电影镜头与 \(scene.directorBadge) 摄影机", level: "info")
                        }
                    }
                }

                // Compact 1-Line Optional First-Frame Image Selector
                HStack(spacing: 6) {
                    Image(systemName: "photo.badge.plus")
                        .font(.system(size: 11))
                        .foregroundColor(.cyan)
                    if let uploadedName = workspace.videoUploadedLocalName {
                        Text("首帧图: \(uploadedName)")
                            .font(.system(size: 10.5, weight: .semibold))
                            .foregroundColor(.green)
                            .lineLimit(1)
                        Spacer()
                        Button("清除") {
                            workspace.videoUploadedRemotePath = nil
                            workspace.videoUploadedLocalName = nil
                        }
                        .font(.system(size: 10))
                        .foregroundColor(.orange)
                        .buttonStyle(.plain)
                    } else if let refItem = workspace.videoSourceItem {
                        Text("首帧图: \(refItem.displayTitle)")
                            .font(.system(size: 10.5, weight: .semibold))
                            .foregroundColor(.green)
                            .lineLimit(1)
                        Spacer()
                        Button("清除") {
                            workspace.videoSourceItem = nil
                        }
                        .font(.system(size: 10))
                        .foregroundColor(.orange)
                        .buttonStyle(.plain)
                    } else {
                        Text("可选首帧图：未选（纯文生视频）")
                            .font(.system(size: 10.5))
                            .foregroundColor(.white.opacity(0.62))
                            .lineLimit(1)
                        Spacer()
                        Button("上传首帧图") {
                            coordinator.promptAndUploadVideoFirstFrame()
                        }
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(.cyan)
                        .buttonStyle(.plain)
                    }
                }
                .padding(7)
                .background(Color.white.opacity(0.04))
                .cornerRadius(6)
            }
            .padding(11)
            .background(RoundedRectangle(cornerRadius: 10).fill(Color(red: 0.08, green: 0.10, blue: 0.15)))

            // ③ 🎥 专业级唯美电影摄影机与运镜调度
            cinemaCameraSelectorSection(includeMovement: true)

            // ④ 视频时长与画幅
            VStack(alignment: .leading, spacing: 9) {
                Label("④ 视频时长与比例", systemImage: "timelapse")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(.cyan)

                HStack(spacing: 6) {
                    videoDurationPill(label: "5秒", frames: 81)
                    videoDurationPill(label: "10秒", frames: 161)
                    videoDurationPill(label: "15秒", frames: 241)
                    videoDurationPill(label: "30秒长片", frames: 481)
                }

                HStack(spacing: 6) {
                    videoResolutionPill(label: "16:9 横屏", w: 832, h: 480)
                    videoResolutionPill(label: "16:9 高清", w: 1280, h: 720)
                    videoResolutionPill(label: "9:16 竖屏", w: 480, h: 832)
                }
            }
            .padding(11)
            .background(RoundedRectangle(cornerRadius: 10).fill(Color(red: 0.08, green: 0.10, blue: 0.15)))
        }
    }

    // MARK: - 🎥 Professional Aesthetic Cinema Camera & Lens Selector Card

    @ViewBuilder
    private func cinemaCameraSelectorSection(includeMovement: Bool) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label("③ 🎥 专业级唯美电影摄影机", systemImage: "camera.aperture")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(.cyan)
                Spacer()
                Text("自动注入光学景深与光影")
                    .font(.system(size: 9.5, weight: .semibold))
                    .foregroundColor(.green)
            }

            VStack(spacing: 5) {
                ForEach(CinemaCameraPreset.all) { cam in
                    let isSelected = workspace.selectedCinemaCamera.id == cam.id
                    Button {
                        workspace.selectedCinemaCamera = cam
                    } label: {
                        HStack(spacing: 8) {
                            Image(systemName: isSelected ? "camera.metering.center.weighted" : "circle")
                                .font(.system(size: 12, weight: .bold))
                                .foregroundColor(isSelected ? .cyan : .white.opacity(0.35))

                            VStack(alignment: .leading, spacing: 1.5) {
                                HStack(spacing: 5) {
                                    Text(cam.name)
                                        .font(.system(size: 11, weight: .bold))
                                        .foregroundColor(isSelected ? .white : .white.opacity(0.85))
                                        .lineLimit(1)
                                    Text(cam.badge)
                                        .font(.system(size: 8.5, weight: .heavy))
                                        .foregroundColor(isSelected ? .black : .cyan)
                                        .padding(.horizontal, 5)
                                        .padding(.vertical, 1)
                                        .background(isSelected ? Color.cyan : Color.cyan.opacity(0.14))
                                        .cornerRadius(3)
                                        .fixedSize(horizontal: true, vertical: false)
                                }
                                Text(cam.cameraSpec)
                                    .font(.system(size: 9.5, design: .monospaced))
                                    .foregroundColor(isSelected ? .cyan : .white.opacity(0.48))
                                    .lineLimit(1)
                            }
                            Spacer(minLength: 0)
                        }
                        .padding(.horizontal, 8)
                        .padding(.vertical, 6)
                        .background(
                            RoundedRectangle(cornerRadius: 7, style: .continuous)
                                .fill(isSelected ? Color.cyan.opacity(0.15) : Color.white.opacity(0.04))
                                .overlay(
                                    RoundedRectangle(cornerRadius: 7, style: .continuous)
                                        .stroke(isSelected ? Color.cyan.opacity(0.75) : Color.white.opacity(0.06), lineWidth: isSelected ? 1.4 : 1)
                                )
                        )
                    }
                    .buttonStyle(.plain)
                }
            }

            if includeMovement {
                Divider().background(Color.white.opacity(0.08))

                HStack {
                    Text("电影运镜")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(.white.opacity(0.78))
                    Spacer()
                    Picker("", selection: $workspace.selectedCameraMovement) {
                        ForEach(CinemaMovementPreset.all) { move in
                            Text(move.name).tag(move)
                        }
                    }
                    .labelsHidden()
                    .frame(width: 215)
                }
            }
        }
        .padding(11)
        .background(RoundedRectangle(cornerRadius: 10).fill(Color(red: 0.08, green: 0.10, blue: 0.15)))
    }

    // MARK: Mode 3 — 🧊 3D 世界 Inspector

    private var lyra3DWorldInspector: some View {
        VStack(alignment: .leading, spacing: 14) {
            inspectorSectionCard(title: "① 长镜头时长预设 (@NVIDIAAI 同款)", icon: "film.stack") {
                VStack(spacing: 6) {
                    ForEach(LyraDurationPreset.all) { preset in
                        let active = workspace.selectedDurationPreset.id == preset.id
                        Button {
                            workspace.applyDurationPreset(preset)
                        } label: {
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(preset.title)
                                        .font(.system(size: 11.5, weight: .bold))
                                        .foregroundColor(active ? .cyan : .white)
                                    Text(preset.subtitle)
                                        .font(.system(size: 9.5))
                                        .foregroundColor(.white.opacity(0.55))
                                        .lineLimit(1)
                                }
                                Spacer()
                                Image(systemName: active ? "checkmark.circle.fill" : "circle")
                                    .foregroundColor(active ? .cyan : .white.opacity(0.3))
                            }
                            .padding(8)
                            .background(
                                RoundedRectangle(cornerRadius: 8)
                                    .fill(active ? Color.cyan.opacity(0.14) : Color.white.opacity(0.04))
                            )
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            inspectorSectionCard(title: "② 选择 2K 场景图或上传本地图", icon: "photo.on.rectangle.angled") {
                VStack(alignment: .leading, spacing: 8) {
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 6) {
                        ForEach(ScenePreset.all.prefix(6)) { preset in
                            let selected = workspace.selectedScenePreset.id == preset.id
                            Button {
                                workspace.applyScenePreset(preset, drafts: gallery.draftItems)
                            } label: {
                                Text(preset.name)
                                    .font(.system(size: 10.5, weight: .bold))
                                    .foregroundColor(selected ? .black : .white)
                                    .lineLimit(1)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 6)
                                    .background(selected ? Color.cyan : Color.white.opacity(0.05))
                                    .cornerRadius(6)
                            }
                            .buttonStyle(.plain)
                        }
                    }

                    Button {
                        coordinator.promptAndUploadLocalImage()
                    } label: {
                        Label("上传本地图片作为 3D 世界首帧", systemImage: "arrow.up.doc.fill")
                            .font(.system(size: 10.5, weight: .semibold))
                            .foregroundColor(.cyan)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 6)
                            .background(Color.cyan.opacity(0.12))
                            .cornerRadius(6)
                    }
                    .buttonStyle(.plain)
                }
            }

            inspectorSectionCard(title: "③ 3D 摄像机运镜轨迹", icon: "camera.metering.Matrix") {
                VStack(alignment: .leading, spacing: 8) {
                    Trajectory3DCanvasView(
                        trajectory: workspace.selectedTrajectory,
                        strength: workspace.selectedTrajectory.backendMode == "flythrough" ? workspace.zoomInStrength : workspace.singleStrength,
                        sceneTitle: workspace.selectedScenePreset.name
                    )

                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 5) {
                        ForEach(LyraTrajectoryDescriptor.all) { traj in
                            let active = workspace.selectedTrajectory.id == traj.id
                            Button {
                                workspace.selectedTrajectory = traj
                                workspace.singleStrength = traj.defaultStrength
                            } label: {
                                Text(traj.name)
                                    .font(.system(size: 10, weight: .bold))
                                    .foregroundColor(active ? .black : .white)
                                    .lineLimit(1)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 6)
                                    .background(active ? Color.cyan : Color.white.opacity(0.05))
                                    .cornerRadius(6)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
        }
    }

    // MARK: Mode 4 — ⚡ 画质超分与对比 Inspector

    private var m1MaxPostInspector: some View {
        VStack(alignment: .leading, spacing: 14) {
            // Mode Switcher between 60fps Post and 3DGS Split Compare
            HStack(spacing: 6) {
                Button {
                    workspace.activeTab = .post
                } label: {
                    Text("⚡ 60fps 超分插帧")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundColor(workspace.activeTab == .post ? .black : .white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 7)
                        .background(workspace.activeTab == .post ? Color.cyan : Color.white.opacity(0.06))
                        .cornerRadius(7)
                }
                .buttonStyle(.plain)

                Button {
                    workspace.activeTab = .abCompare
                } label: {
                    Text("╱ 3DGS 分屏对比")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundColor(workspace.activeTab == .abCompare ? .black : .white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 7)
                        .background(workspace.activeTab == .abCompare ? Color.cyan : Color.white.opacity(0.06))
                        .cornerRadius(7)
                }
                .buttonStyle(.plain)
            }

            inspectorSectionCard(title: "① 选择待超分的视频", icon: "film") {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(gallery.videoItems.prefix(6)) { vid in
                        let selected = workspace.postTargetItem?.id == vid.id
                        Button {
                            workspace.postTargetItem = vid
                            workspace.stageItem = vid
                        } label: {
                            HStack {
                                Image(systemName: vid.isEnhanced1080p ? "sparkles.tv.fill" : "video.fill")
                                    .foregroundColor(selected ? .black : .cyan)
                                Text(vid.displayTitle)
                                    .font(.system(size: 11, weight: .semibold))
                                    .foregroundColor(selected ? .black : .white)
                                    .lineLimit(1)
                                Spacer()
                            }
                            .padding(7)
                            .background(selected ? Color.cyan : Color.white.opacity(0.05))
                            .cornerRadius(6)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            inspectorSectionCard(title: "② Apple Silicon RIFE 60fps 超分参数", icon: "bolt.badge.clock.fill") {
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Text("推进速度")
                            .font(.system(size: 11))
                        Spacer()
                        Picker("", selection: $workspace.postSpeed) {
                            Text("1.0× 原速").tag(1.0)
                            Text("2.0× 平滑穿梭").tag(2.0)
                            Text("4.0× 高速穿梭").tag(4.0)
                        }
                        .labelsHidden()
                        .frame(width: 145)
                    }

                    HStack {
                        Text("RIFE 插帧")
                            .font(.system(size: 11))
                        Spacer()
                        Picker("", selection: $workspace.postInterp) {
                            Text("×1 (不插帧)").tag(1)
                            Text("×2 (60fps 丝滑)").tag(2)
                            Text("×4 (极限光流)").tag(4)
                        }
                        .labelsHidden()
                        .frame(width: 145)
                    }

                    HStack {
                        Text("目标画质")
                            .font(.system(size: 11))
                        Spacer()
                        Picker("", selection: $workspace.postScale) {
                            Text("1080p Full HD").tag("1080p")
                            Text("1440p 2.5K").tag("1440p")
                            Text("4K UHD").tag("4k")
                        }
                        .labelsHidden()
                        .frame(width: 145)
                    }
                }
            }
        }
    }

    // MARK: - 3. Center Column (Full Height): Pure Preview Stage + Bottom Quick Workflow Bar

    @ViewBuilder
    private var centerStageColumn: some View {
        if workspace.activeTab == .abCompare {
            ABComparePlayerView(galleryStore: gallery, coordinator: coordinator)
        } else if workspace.activeTab == .webStudio {
            EmbeddedWebStudioView(url: URL(string: "http://127.0.0.1:7788")!)
        } else {
            VStack(spacing: 0) {
                // Top Header of Center Stage
                if let item = workspace.stageItem {
                    HStack(spacing: 8) {
                        Text(item.isVideo ? "🎬 视频预览" : "🖼️ 图片预览")
                            .font(.system(size: 10.5, weight: .heavy))
                            .foregroundColor(.black)
                            .padding(.horizontal, 7)
                            .padding(.vertical, 3)
                            .background(item.isVideo ? Color(red: 0.25, green: 0.85, blue: 0.65) : Color.cyan)
                            .cornerRadius(5)
                            .fixedSize(horizontal: true, vertical: false)

                        Text(item.displayTitle)
                            .font(.system(size: 13, weight: .bold))
                            .foregroundColor(.white)
                            .lineLimit(1)

                        Text(item.resolutionBadge)
                            .font(.system(size: 10.5, weight: .semibold, design: .monospaced))
                            .foregroundColor(.cyan)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.cyan.opacity(0.14))
                            .cornerRadius(4)
                            .fixedSize(horizontal: true, vertical: false)

                        if let fps = item.fpsBadge {
                            Text(fps)
                                .font(.system(size: 10.5, weight: .semibold, design: .monospaced))
                                .foregroundColor(.green)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Color.green.opacity(0.14))
                                .cornerRadius(4)
                                .fixedSize(horizontal: true, vertical: false)
                        }

                        Spacer()
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(Color(red: 0.05, green: 0.06, blue: 0.10))

                    Divider().background(Color.white.opacity(0.07))
                }

                // Main Full-Height Canvas
                ZStack {
                    Color(red: 0.03, green: 0.04, blue: 0.07)

                    if let item = workspace.stageItem {
                        if item.isVideo && FileManager.default.fileExists(atPath: item.localFileURL.path) {
                            NativeStageVideoPlayer(url: item.localFileURL)
                                .frame(maxWidth: .infinity, maxHeight: .infinity)
                        } else if let img = stageDecodedImage {
                            Image(nsImage: img)
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                                .frame(maxWidth: .infinity, maxHeight: .infinity)
                                .padding(18)
                        } else {
                            ProgressView("正在加载高清画布…")
                                .frame(maxWidth: .infinity, maxHeight: .infinity)
                        }
                    } else {
                        VStack(spacing: 10) {
                            Image(systemName: "sparkles.rectangle.stack")
                                .font(.system(size: 38))
                                .foregroundColor(.cyan.opacity(0.5))
                            Text("在左侧输入一句话提示词并点击「立即生成」，或点击右侧素材库任意作品预览")
                                .font(.system(size: 13))
                                .foregroundColor(.white.opacity(0.6))
                        }
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .task(id: workspace.stageItem?.id) {
                    if let item = workspace.stageItem, item.isImage {
                        stageDecodedImage = await ThumbnailCacheActor.shared.thumbnail(for: item, maxPixelSize: 2048)
                    }
                }

                // Bottom Action Bar of Center Stage
                if let item = workspace.stageItem {
                    Divider().background(Color.white.opacity(0.08))

                    HStack(spacing: 10) {
                        Text(item.subtitlePrompt)
                            .font(.system(size: 11))
                            .foregroundColor(.white.opacity(0.58))
                            .lineLimit(1)

                        Spacer(minLength: 10)

                        if item.isImage {
                            stageActionButton(title: "🎬 用此图生成视频", tint: .cyan) {
                                coordinator.sendItemToVideo(item)
                            }
                            stageActionButton(title: "🧊 用此图生成 3D 世界", tint: .indigo) {
                                coordinator.sendItemToLyra3D(item)
                            }
                        } else {
                            stageActionButton(title: "⚡ 60fps 超分插帧", tint: .cyan) {
                                coordinator.sendItemToM1MaxPost(item)
                            }
                            stageActionButton(title: "╱ 3DGS 对角对比", tint: .indigo) {
                                coordinator.openItemInABCompare(item)
                            }
                        }

                        Button {
                            coordinator.revealInFinder(item)
                        } label: {
                            HStack(spacing: 4) {
                                Image(systemName: "folder.fill")
                                    .font(.system(size: 11))
                                Text("在访达中定位")
                                    .font(.system(size: 11, weight: .semibold))
                                    .lineLimit(1)
                                    .fixedSize(horizontal: true, vertical: false)
                            }
                            .foregroundColor(.white.opacity(0.85))
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(Color.white.opacity(0.1))
                            .cornerRadius(7)
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(Color(red: 0.05, green: 0.06, blue: 0.10))
                }
            }
        }
    }

    // MARK: - 4. Right Column (390px, Full Height): 🗂️ 统一素材库 (Media Library)

    private var unifiedMediaLibrarySidebar: some View {
        VStack(alignment: .leading, spacing: 10) {
            // 1. Library Title & Open Folder Button
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text("🗂️ 素材库")
                            .font(.system(size: 14, weight: .heavy))
                            .foregroundColor(.white)
                        Text("\(gallery.filteredItems.count) 件")
                            .font(.system(size: 10, weight: .bold, design: .monospaced))
                            .foregroundColor(.cyan)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.cyan.opacity(0.15))
                            .cornerRadius(4)
                    }
                    Text("生成的图片与视频自动归档于此，点击即可预览")
                        .font(.system(size: 10))
                        .foregroundColor(.white.opacity(0.55))
                        .lineLimit(1)
                }

                Spacer()

                Button {
                    NSWorkspace.shared.open(GalleryItem.galleryRootURL)
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "folder")
                            .font(.system(size: 10.5))
                        Text("打开目录")
                            .font(.system(size: 10.5, weight: .semibold))
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
                    }
                    .foregroundColor(.white.opacity(0.82))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 5)
                    .background(Color.white.opacity(0.08))
                    .cornerRadius(6)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 12)
            .padding(.top, 12)

            // 2. Single-Line Category Filter Pills (全部 | 🖼️ 图片 | 🎬 视频 | ⭐ 收藏 | 🎨 预设)
            HStack(spacing: 5) {
                ForEach(GalleryFilterCategory.libraryPills) { cat in
                    let active = gallery.activeCategory == cat
                    Button {
                        gallery.activeCategory = cat
                    } label: {
                        Text(cat.title)
                            .font(.system(size: 11, weight: active ? .heavy : .semibold))
                            .foregroundColor(active ? .black : .white.opacity(0.82))
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
                            .padding(.horizontal, 9)
                            .padding(.vertical, 5)
                            .background(
                                RoundedRectangle(cornerRadius: 6, style: .continuous)
                                    .fill(active ? Color.cyan : Color.white.opacity(0.06))
                            )
                    }
                    .buttonStyle(.plain)
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 12)

            // 3. Search Bar
            HStack(spacing: 6) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.45))
                TextField("搜索提示词、图片或视频文件名…", text: $gallery.searchQuery)
                    .textFieldStyle(.plain)
                    .font(.system(size: 11.5))
                    .foregroundColor(.white)
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
            .padding(.vertical, 6)
            .background(Color.black.opacity(0.35))
            .cornerRadius(7)
            .overlay(
                RoundedRectangle(cornerRadius: 7)
                    .stroke(Color.white.opacity(0.08), lineWidth: 1)
            )
            .padding(.horizontal, 12)

            Divider().background(Color.white.opacity(0.08))

            // 4. 2-Column Unified Media Grid (Newest Creations Always at Top-Left!)
            ScrollView {
                LazyVGrid(
                    columns: [
                        GridItem(.flexible(), spacing: 10),
                        GridItem(.flexible(), spacing: 10)
                    ],
                    spacing: 10
                ) {
                    ForEach(gallery.filteredItems) { item in
                        AsyncThumbnailCard(
                            item: item,
                            isSelected: workspace.stageItem?.id == item.id,
                            isFavorite: gallery.isFavorite(item.id),
                            onSelect: {
                                workspace.stageItem = item
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
                .padding(.horizontal, 12)
                .padding(.bottom, 16)
            }
        }
        .background(Color(red: 0.06, green: 0.07, blue: 0.11))
    }

    // MARK: - Reusable Clean UI Helpers

    @ViewBuilder
    private func compactModelRow(
        model: RemoteModelItem,
        isSelected: Bool,
        onSelect: @escaping () -> Void
    ) -> some View {
        let isZeroVRAM = model.id == "breeze-tts-2" || model.kind == "tts"
        let statusText: String = isZeroVRAM
            ? "0显存云盘"
            : (model.status == "loaded" ? "GPU 常驻" : (model.status == "downloaded" ? "已就绪" : "按需加载"))
        let statusColor: Color = isZeroVRAM ? .green : (model.status == "loaded" ? .green : (model.status == "downloaded" ? .cyan : .orange))

        Button(action: onSelect) {
            HStack(spacing: 8) {
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(isSelected ? .cyan : .white.opacity(0.35))

                Text(model.name)
                    .font(.system(size: 11.5, weight: isSelected ? .bold : .medium))
                    .foregroundColor(isSelected ? .white : .white.opacity(0.85))
                    .lineLimit(1)

                Spacer(minLength: 4)

                Text(statusText)
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundColor(statusColor)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 2)
                    .background(statusColor.opacity(0.15))
                    .cornerRadius(4)
                    .fixedSize(horizontal: true, vertical: false)
            }
            .padding(.horizontal, 9)
            .padding(.vertical, 7)
            .background(
                RoundedRectangle(cornerRadius: 7, style: .continuous)
                    .fill(isSelected ? Color.cyan.opacity(0.15) : Color.white.opacity(0.04))
                    .overlay(
                        RoundedRectangle(cornerRadius: 7, style: .continuous)
                            .stroke(isSelected ? Color.cyan.opacity(0.75) : Color.white.opacity(0.06), lineWidth: isSelected ? 1.4 : 1)
                    )
            )
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private func promptChipButton(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 10.5, weight: .semibold))
                .foregroundColor(.cyan)
                .lineLimit(1)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 5)
                .background(Color.cyan.opacity(0.11))
                .cornerRadius(6)
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(Color.cyan.opacity(0.25), lineWidth: 0.8)
                )
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private func videoDurationPill(label: String, frames: Int) -> some View {
        let active = workspace.videoFrames == frames
        Button {
            workspace.videoFrames = frames
        } label: {
            Text(label)
                .font(.system(size: 10.5, weight: .bold))
                .foregroundColor(active ? .black : .white.opacity(0.85))
                .lineLimit(1)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 6)
                .background(active ? Color.cyan : Color.white.opacity(0.05))
                .cornerRadius(6)
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private func videoResolutionPill(label: String, w: Int, h: Int) -> some View {
        let active = workspace.videoWidth == w && workspace.videoHeight == h
        Button {
            workspace.videoWidth = w
            workspace.videoHeight = h
        } label: {
            Text(label)
                .font(.system(size: 10.5, weight: .semibold))
                .foregroundColor(active ? .black : .white.opacity(0.85))
                .lineLimit(1)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 6)
                .background(active ? Color.cyan : Color.white.opacity(0.05))
                .cornerRadius(6)
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private func stageActionButton(title: String, tint: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 11, weight: .bold))
                .foregroundColor(tint == .cyan ? .black : .white)
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
                .padding(.horizontal, 11)
                .padding(.vertical, 6)
                .background(tint)
                .cornerRadius(7)
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private func inspectorSectionCard<Content: View>(
        title: String,
        icon: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            Label(title, systemImage: icon)
                .font(.system(size: 12, weight: .bold))
                .foregroundColor(.cyan)
            content()
        }
        .padding(11)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(Color(red: 0.08, green: 0.10, blue: 0.15))
                .overlay(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .stroke(Color.white.opacity(0.07), lineWidth: 1)
                )
        )
    }
}

// MARK: - Hardware Telemetry, Colab Session & Live Terminal Sheet (Opened from Top Bar)

public struct HardwareAndLogSheetView: View {
    @ObservedObject var telemetry: TelemetryStore
    @ObservedObject var modelCenter: ModelCenterStore
    @ObservedObject var jobQueue: JobQueueStore
    @ObservedObject var coordinator: StudioCoordinator
    @Environment(\.dismiss) private var dismiss

    public var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label("Colab 云端算力监控 · 4级存储金字塔 · 实时终端日志", systemImage: "gauge.with.dots.needle.67percent")
                    .font(.system(size: 15, weight: .heavy))
                    .foregroundColor(.white)
                Spacer()
                Button("⚡ 一键重连 Colab") {
                    Task {
                        _ = try? await ForgeClient.shared.connectColabSession(
                            name: telemetry.sessionName,
                            gpu: telemetry.selectedGPUType
                        )
                        await coordinator.refreshAll()
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(.cyan)

                Button("🛑 释放 Colab 会话") {
                    Task {
                        _ = try? await ForgeClient.shared.stopColabSession(name: telemetry.sessionName)
                        await coordinator.refreshAll()
                    }
                }
                .buttonStyle(.bordered)

                Button("关闭") { dismiss() }
                    .buttonStyle(.bordered)
            }

            HStack(alignment: .top, spacing: 14) {
                // Left: Hardware Sparklines + 4-Tier Storage Pyramid
                ScrollView {
                    TelemetrySparklinePanel(telemetry: telemetry)
                }
                .frame(width: 340)

                // Right: Active Jobs & Live Terminal Log
                VStack(alignment: .leading, spacing: 10) {
                    Text("实时管线终端日志")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(.green)

                    ScrollView {
                        Text(jobQueue.consoleLogText)
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundColor(Color(red: 0.65, green: 0.95, blue: 0.75))
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(10)
                    }
                    .background(Color.black.opacity(0.55))
                    .cornerRadius(8)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .padding(18)
        .frame(width: 820, height: 500)
        .background(Color(red: 0.06, green: 0.08, blue: 0.12))
        .preferredColorScheme(.dark)
    }
}

// MARK: - Model Center Sheet (1-Click HuggingFace Deployment & Worker Management)

public struct ModelCenterSheetView: View {
    @ObservedObject var modelCenter: ModelCenterStore
    @ObservedObject var coordinator: StudioCoordinator
    @Environment(\.dismiss) private var dismiss

    public var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label("WorldForge 模型中心 · 176GB 主机内存零重载调度", systemImage: "memorychip.fill")
                    .font(.system(size: 15, weight: .heavy))
                    .foregroundColor(.white)
                Spacer()
                Button("关闭") { dismiss() }
                    .buttonStyle(.bordered)
            }

            HStack(spacing: 8) {
                TextField("粘贴 HuggingFace 仓库或完整 URL（支持 /tree/main/ 子目录，如 MiniMax-AI/MiniMax-H3-Hybrid-1.8/tree/main/1.8-hybrid）", text: $modelCenter.newRepoInput)
                    .textFieldStyle(.roundedBorder)
                Button("添加为生图模型") {
                    let repo = modelCenter.newRepoInput.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !repo.isEmpty else { return }
                    modelCenter.newRepoInput = ""
                    Task {
                        await coordinator.addCustomModelInline(repoInput: repo, forTab: .image)
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(.cyan)

                Button("添加为视频模型") {
                    let repo = modelCenter.newRepoInput.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !repo.isEmpty else { return }
                    modelCenter.newRepoInput = ""
                    Task {
                        await coordinator.addCustomModelInline(repoInput: repo, forTab: .video)
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(.indigo)
            }

            ScrollView {
                VStack(spacing: 8) {
                    ForEach(modelCenter.models) { model in
                        HStack(spacing: 12) {
                            VStack(alignment: .leading, spacing: 3) {
                                HStack(spacing: 6) {
                                    Text(model.name)
                                        .font(.system(size: 13, weight: .bold))
                                        .foregroundColor(.white)
                                    Text(model.repo)
                                        .font(.system(size: 10.5, design: .monospaced))
                                        .foregroundColor(.cyan)
                                }
                                Text(model.description ?? "")
                                    .font(.system(size: 11))
                                    .foregroundColor(.white.opacity(0.65))
                            }
                            Spacer()
                            Text(model.statusBadgeText)
                                .font(.system(size: 10.5, weight: .bold, design: .monospaced))
                                .foregroundColor(.green)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(Color.green.opacity(0.15))
                                .cornerRadius(5)

                            Button("设为当前模型") {
                                coordinator.selectModelAndSwitchTab(model)
                                dismiss()
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(.cyan)

                            Button("预下载") {
                                Task {
                                    try? await ForgeClient.shared.triggerModelAction(modelId: model.id, action: "download")
                                    await coordinator.refreshJobsAndLogs()
                                }
                            }
                            .buttonStyle(.bordered)

                            Button("预热进显存") {
                                Task {
                                    try? await ForgeClient.shared.triggerModelAction(modelId: model.id, action: "load")
                                    await coordinator.refreshJobsAndLogs()
                                }
                            }
                            .buttonStyle(.bordered)

                            Button("卸载释放") {
                                Task {
                                    try? await ForgeClient.shared.triggerModelAction(modelId: model.id, action: "unload")
                                    await coordinator.refreshModelsOnly()
                                }
                            }
                            .buttonStyle(.bordered)
                        }
                        .padding(11)
                        .background(Color.white.opacity(0.05))
                        .cornerRadius(9)
                    }
                }
            }
        }
        .padding(18)
        .frame(width: 760, height: 460)
        .background(Color(red: 0.06, green: 0.08, blue: 0.12))
        .preferredColorScheme(.dark)
    }
}
