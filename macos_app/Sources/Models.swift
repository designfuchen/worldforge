import Foundation
import CoreGraphics

// MARK: - Studio Navigation & Filter Enums

public enum StudioTab: String, CaseIterable, Identifiable, Sendable {
    case image = "image"
    case video = "video"
    case world = "world"
    case post = "post"
    case abCompare = "abCompare"
    case gallery = "gallery"
    case webStudio = "webStudio"

    public static let primaryTabs: [StudioTab] = [.image, .video, .world, .post]

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .image: return "🎨 AI 生图"
        case .video: return "🎬 AI 视频"
        case .world: return "🧊 3D 世界"
        case .post: return "⚡ 画质超分与对比"
        case .abCompare: return "╱ 3DGS 对比"
        case .gallery: return "🗂️ 素材库"
        case .webStudio: return "内嵌 Web 台"
        }
    }

    public var subtitle: String {
        switch self {
        case .image: return "选模型 → 填一句话提示词 → 立即生成 2K 超清大图"
        case .video: return "选视频模型 → 填一句话镜头描述 → 立即生成动态视频"
        case .world: return "NVIDIA Lyra 2.0 · 单图生成 30s–45s 可漫游 3D 空间穿梭"
        case .post: return "Apple Silicon RIFE 60fps 光流插帧 & 3DGS 对角对比"
        case .abCompare: return "832×480 16fps 原始流 vs 1080p 60fps 逐帧同屏核验"
        case .gallery: return "生成的图片与视频统一归档"
        case .webStudio: return "127.0.0.1:7788 完整 Web 控制台无缝协同"
        }
    }

    public var icon: String {
        switch self {
        case .image: return "sparkles.rectangle.stack.fill"
        case .video: return "film.stack.fill"
        case .world: return "cube.transparent.fill"
        case .post: return "bolt.badge.clock.fill"
        case .abCompare: return "rectangle.split.2x1.slash.fill"
        case .gallery: return "square.grid.2x2.fill"
        case .webStudio: return "safari.fill"
        }
    }

    public var shortcutKey: Character {
        switch self {
        case .image: return "1"
        case .video: return "2"
        case .world: return "3"
        case .post: return "4"
        case .abCompare: return "5"
        case .gallery: return "6"
        case .webStudio: return "7"
        }
    }
}

public enum GalleryFilterCategory: String, CaseIterable, Identifiable, Sendable {
    case all = "all"
    case image2k = "image2k"
    case world3d = "world3d"
    case favorites = "favorites"
    case drafts = "drafts"
    case enhanced1080p = "enhanced1080p"

    public static let libraryPills: [GalleryFilterCategory] = [.all, .image2k, .world3d, .favorites, .drafts]

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .all: return "全部"
        case .image2k: return "🖼️ 图片"
        case .world3d: return "🎬 视频"
        case .favorites: return "⭐ 收藏"
        case .drafts: return "🎨 预设"
        case .enhanced1080p: return "⚡ 60fps"
        }
    }

    public var icon: String {
        switch self {
        case .all: return "square.grid.2x2.fill"
        case .image2k: return "photo.fill"
        case .world3d: return "film.fill"
        case .favorites: return "star.fill"
        case .drafts: return "paintbrush.pointed.fill"
        case .enhanced1080p: return "sparkles.tv.fill"
        }
    }
}

// MARK: - Local Daemon State (/api/local/state)

public struct LocalStateResponse: Codable, Sendable, Equatable {
    public var colab: ColabSnapshot?
    public var tunnel: TunnelSnapshot?
    public var remote: RemoteSnapshot?
    public var settings: AppSettingsSnapshot?
    public var idle: IdleSnapshot?
    public var notices: [NoticeItem]?
    public var local: LocalInfoSnapshot?

    public init(
        colab: ColabSnapshot? = nil,
        tunnel: TunnelSnapshot? = nil,
        remote: RemoteSnapshot? = nil,
        settings: AppSettingsSnapshot? = nil,
        idle: IdleSnapshot? = nil,
        notices: [NoticeItem]? = nil,
        local: LocalInfoSnapshot? = nil
    ) {
        self.colab = colab
        self.tunnel = tunnel
        self.remote = remote
        self.settings = settings
        self.idle = idle
        self.notices = notices
        self.local = local
    }
}

public struct ColabSnapshot: Codable, Sendable, Equatable {
    public var cli_ok: Bool?
    public var sessions: [ColabSessionItem]?
    public var error: String?
    public var updated_at: Double?
}

public struct ColabSessionItem: Codable, Sendable, Equatable, Identifiable, Hashable {
    public var id: String { name }
    public var name: String
    public var host: String?
    public var hardware: String?
    public var status: String?
}

public struct TunnelSnapshot: Codable, Sendable, Equatable {
    public var status: String?
    public var session: String?
    public var local_port: Int?
    public var error: String?
    public var deploying: Bool?
}

public struct RemoteSnapshot: Codable, Sendable, Equatable {
    public var status: String?
    public var version: String?
    public var gpu: String?
    public var error: String?
}

public struct AppSettingsSnapshot: Codable, Sendable, Equatable {
    public var session_name: String?
    public var gpu: String?
    public var idle_minutes: Int?
    public var auto_fetch: Bool?
    public var output_dir: String?
}

public struct IdleSnapshot: Codable, Sendable, Equatable {
    public var seconds: Int?
    public var will_stop_in: Int?
    public var enabled: Bool?
}

public struct NoticeItem: Codable, Sendable, Equatable, Identifiable {
    public var id: String { "\(time ?? 0)-\(text ?? "")" }
    public var time: Double?
    public var level: String?
    public var text: String?
}

public struct LocalInfoSnapshot: Codable, Sendable, Equatable {
    public var version: String?
    public var remote_code_version: String?
    public var tasks_running: Int?
    public var ffmpeg: Bool?
    public var rife: Bool?
}

// MARK: - 3D Vector (Fast Concrete Struct — Zero SIMD Overload Delay)

public struct Vec3D: Sendable, Hashable {
    public var x: Double
    public var y: Double
    public var z: Double

    public init(_ x: Double, _ y: Double, _ z: Double) {
        self.x = x
        self.y = y
        self.z = z
    }

    public func adding(_ other: Vec3D) -> Vec3D {
        Vec3D(x + other.x, y + other.y, z + other.z)
    }
}

// MARK: - Remote Metrics (/api/remote/metrics)

public struct RemoteMetricsResponse: Codable, Sendable, Equatable {
    public var gpu: GPUMetrics?
    public var ram: MemoryMetrics?
    public var shm: DiskMetrics?
    public var drive: DriveMetrics?
    public var disk: DiskMetrics?
    public var workers: [WorkerMetrics]?
    public var queue: QueueMetrics?

    public init(
        gpu: GPUMetrics? = nil,
        ram: MemoryMetrics? = nil,
        shm: DiskMetrics? = nil,
        drive: DriveMetrics? = nil,
        disk: DiskMetrics? = nil,
        workers: [WorkerMetrics]? = nil,
        queue: QueueMetrics? = nil
    ) {
        self.gpu = gpu
        self.ram = ram
        self.shm = shm
        self.drive = drive
        self.disk = disk
        self.workers = workers
        self.queue = queue
    }
}

public struct DriveMetrics: Codable, Sendable, Equatable {
    public var used_gb: Double?
    public var total_gb: Double?
    public var free_gb: Double?
    public var mounted: Bool?

    public var driveFraction: Double {
        guard let u = used_gb, let t = total_gb, t > 0 else { return 0.12 }
        return min(1.0, max(0.0, u / t))
    }
}

public struct GPUMetrics: Codable, Sendable, Equatable {
    public var name: String?
    public var util: Int?
    public var mem_used_mb: Int?
    public var mem_total_mb: Int?
    public var temp_c: Int?
    public var power_w: Int?

    public var vramUsedGB: Double {
        Double(mem_used_mb ?? 0) / 1024.0
    }
    public var vramTotalGB: Double {
        max(1.0, Double(mem_total_mb ?? 24576) / 1024.0)
    }
    public var vramFraction: Double {
        guard let used = mem_used_mb, let total = mem_total_mb, total > 0 else { return 0 }
        return min(1.0, max(0.0, Double(used) / Double(total)))
    }
}

public struct MemoryMetrics: Codable, Sendable, Equatable {
    public var used_gb: Double?
    public var total_gb: Double?

    public var ramFraction: Double {
        guard let u = used_gb, let t = total_gb, t > 0 else { return 0 }
        return min(1.0, max(0.0, u / t))
    }
}

public struct DiskMetrics: Codable, Sendable, Equatable {
    public var used_gb: Double?
    public var total_gb: Double?

    public var diskFraction: Double {
        guard let u = used_gb, let t = total_gb, t > 0 else { return 0 }
        return min(1.0, max(0.0, u / t))
    }
}

public struct WorkerMetrics: Codable, Sendable, Equatable, Identifiable, Hashable {
    public var id: String { model_id }
    public var model_id: String
    public var state: String?
    public var pid: Int?
    public var vram_mb: Int?

    public var isResidentInVRAM: Bool {
        (vram_mb ?? 0) > 512 || state == "ready" || state == "busy" || state == "running"
    }

    public var isOffloadedToHostRAM: Bool {
        state == "offloaded" || (state != "dead" && (vram_mb ?? 0) <= 512 && pid != nil)
    }
}

public struct QueueMetrics: Codable, Sendable, Equatable {
    public var running: String?
    public var queued: Int?
}

// MARK: - Remote Models (/api/remote/models)

public struct RemoteModelItem: Codable, Sendable, Equatable, Identifiable, Hashable {
    public var id: String
    public var repo: String
    public var subfolder: String?
    public var name: String
    public var kind: String
    public var builtin: Bool?
    public var pipeline: String?
    public var description: String?
    public var status: String?
    public var size_gb: Double?

    public init(
        id: String,
        repo: String,
        subfolder: String? = nil,
        name: String,
        kind: String,
        builtin: Bool? = nil,
        pipeline: String? = nil,
        description: String? = nil,
        status: String? = nil,
        size_gb: Double? = nil
    ) {
        self.id = id
        self.repo = repo
        self.subfolder = subfolder
        self.name = name
        self.kind = kind
        self.builtin = builtin
        self.pipeline = pipeline
        self.description = description
        self.status = status
        self.size_gb = size_gb
    }

    public var statusBadgeText: String {
        if id == "breeze-tts-2" || kind == "tts" {
            return "0 MB 显存 · 30TB 谷歌云盘直连"
        }
        switch status ?? "available" {
        case "loaded": return "GPU 显存常驻"
        case "offloaded": return "176GB 内存待命"
        case "loading": return "加载进显存中…"
        case "downloading": return "高速拉取权重…"
        case "downloaded": return "云盘/内存盘就绪"
        default: return "云端可拉取"
        }
    }
}

// MARK: - Remote Jobs & Local Tasks (/api/remote/jobs & /api/local/tasks)

public struct RemoteJobItem: Codable, Sendable, Equatable, Identifiable, Hashable {
    public var id: String
    public var model_id: String?
    public var task: String?
    public var status: String?
    public var progress: Double?
    public var stage: String?
    public var created: Double?
    public var started: Double?
    public var finished: Double?
    public var outputs: [RemoteJobOutput]?
    public var error: String?
    public var eta_s: Int?
    public var params: JobParamsSummary?

    public var isActive: Bool {
        status == "queued" || status == "running"
    }

    public var displayTitle: String {
        if let p = params?.prompt, !p.isEmpty { return p }
        if let s = params?.scene, !s.isEmpty { return s }
        switch task ?? "" {
        case "lyra": return "Lyra 2.0 3D 世界漫游生成"
        case "t2i": return "Qwen-Image 2.1 Turbo 2K 生图"
        case "t2v": return "文生视频渲染"
        case "i2v": return "图生视频渲染"
        case "download": return "下载模型权重 \(model_id ?? "")"
        case "load": return "预热加载模型 \(model_id ?? "")"
        default: return "\(task ?? "任务") · \(id)"
        }
    }
}

public struct RemoteJobOutput: Codable, Sendable, Equatable, Hashable {
    public var path: String?
    public var kind: String?
    public var name: String?
    public var seed: Int?
}

public struct JobParamsSummary: Codable, Sendable, Equatable, Hashable {
    public var prompt: String?
    public var scene: String?
    public var caption: String?
    public var mode: String?
    public var trajectory: String?
    public var width: Int?
    public var height: Int?
    public var seed: Int?
}

public struct LocalTaskItem: Codable, Sendable, Equatable, Identifiable, Hashable {
    public var id: String
    public var type: String?
    public var title: String?
    public var status: String?
    public var progress: Double?
    public var created: Double?
    public var finished: Double?
    public var error: String?

    public var isActive: Bool {
        status == "running" || status == "queued"
    }
}

public struct JobLogChunk: Codable, Sendable, Equatable {
    public var text: String?
    public var offset: Int?
    public var done: Bool?
}

// MARK: - Gallery Models (~/Movies/WorldForge/gallery.json & /api/local/gallery)

public struct GalleryIndexFile: Codable, Sendable {
    public var version: Int?
    public var items: [GalleryItem]
    public var fetched: [String]?
}

public struct GalleryPostMeta: Codable, Sendable, Equatable, Hashable {
    public var speed: Double?
    public var interp: Int?
    public var scale: String?
    public var unsharp: String?
}

public struct GalleryItemMeta: Codable, Sendable, Equatable, Hashable {
    public var title: String?
    public var preset_id: String?
    public var prompt: String?
    public var scene: String?
    public var lyra_scene: String?
    public var caption: String?
    public var model_id: String?
    public var model: String?
    public var task: String?
    public var seed: Int?
    public var steps: Int?
    public var width: Int?
    public var height: Int?
    public var mode: String?
    public var trajectory: String?
    public var job_id: String?
    public var remote_path: String?
    public var builtin_draft: Bool?
    public var parent: String?
    public var post: GalleryPostMeta?

    enum CodingKeys: String, CodingKey {
        case title, preset_id, prompt, scene, lyra_scene, caption, model_id, model, task
        case seed, steps, width, height, mode, trajectory, job_id, remote_path
        case builtin_draft, parent, post
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        title = try? c.decodeIfPresent(String.self, forKey: .title)
        preset_id = try? c.decodeIfPresent(String.self, forKey: .preset_id)
        prompt = try? c.decodeIfPresent(String.self, forKey: .prompt)
        scene = try? c.decodeIfPresent(String.self, forKey: .scene)
        lyra_scene = try? c.decodeIfPresent(String.self, forKey: .lyra_scene)
        caption = try? c.decodeIfPresent(String.self, forKey: .caption)
        model_id = try? c.decodeIfPresent(String.self, forKey: .model_id)
        model = try? c.decodeIfPresent(String.self, forKey: .model)
        task = try? c.decodeIfPresent(String.self, forKey: .task)
        if let sInt = try? c.decodeIfPresent(Int.self, forKey: .seed) {
            seed = sInt
        } else if let sDbl = try? c.decodeIfPresent(Double.self, forKey: .seed) {
            seed = Int(sDbl)
        } else {
            seed = nil
        }
        steps = try? c.decodeIfPresent(Int.self, forKey: .steps)
        width = try? c.decodeIfPresent(Int.self, forKey: .width)
        height = try? c.decodeIfPresent(Int.self, forKey: .height)
        mode = try? c.decodeIfPresent(String.self, forKey: .mode)
        trajectory = try? c.decodeIfPresent(String.self, forKey: .trajectory)
        job_id = try? c.decodeIfPresent(String.self, forKey: .job_id)
        remote_path = try? c.decodeIfPresent(String.self, forKey: .remote_path)
        builtin_draft = try? c.decodeIfPresent(Bool.self, forKey: .builtin_draft)
        parent = try? c.decodeIfPresent(String.self, forKey: .parent)
        post = try? c.decodeIfPresent(GalleryPostMeta.self, forKey: .post)
    }

    public init(
        title: String? = nil,
        preset_id: String? = nil,
        prompt: String? = nil,
        scene: String? = nil,
        lyra_scene: String? = nil,
        model_id: String? = nil,
        model: String? = nil,
        task: String? = nil,
        seed: Int? = nil,
        steps: Int? = nil,
        width: Int? = nil,
        height: Int? = nil,
        mode: String? = nil,
        trajectory: String? = nil,
        job_id: String? = nil,
        remote_path: String? = nil,
        builtin_draft: Bool? = nil,
        parent: String? = nil,
        post: GalleryPostMeta? = nil
    ) {
        self.title = title
        self.preset_id = preset_id
        self.prompt = prompt
        self.scene = scene
        self.lyra_scene = lyra_scene
        self.model_id = model_id
        self.model = model
        self.task = task
        self.seed = seed
        self.steps = steps
        self.width = width
        self.height = height
        self.mode = mode
        self.trajectory = trajectory
        self.job_id = job_id
        self.remote_path = remote_path
        self.builtin_draft = builtin_draft
        self.parent = parent
        self.post = post
    }
}

public struct GalleryMediaInfo: Codable, Sendable, Equatable, Hashable {
    public var width: Int?
    public var height: Int?
    public var fps: Double?
    public var duration: Double?
    public var frames: Int?
    public var size: Int64?

    public init(
        width: Int? = nil,
        height: Int? = nil,
        fps: Double? = nil,
        duration: Double? = nil,
        frames: Int? = nil,
        size: Int64? = nil
    ) {
        self.width = width
        self.height = height
        self.fps = fps
        self.duration = duration
        self.frames = frames
        self.size = size
    }
}

public struct GalleryItem: Codable, Sendable, Equatable, Identifiable, Hashable {
    public var id: String
    public var kind: String
    public var name: String
    public var rel: String?
    public var thumb_rel: String?
    public var path: String?
    public var url: String?
    public var thumb: String?
    public var strip_thumb: String?
    public var created: Double?
    public var meta: GalleryItemMeta?
    public var info: GalleryMediaInfo?

    public static var galleryRootURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Movies/WorldForge", isDirectory: true)
    }

    public var isVideo: Bool {
        kind == "video" || name.lowercased().hasSuffix(".mp4") || name.lowercased().hasSuffix(".mov")
    }

    public var isImage: Bool {
        !isVideo
    }

    public var isBuiltinDraft: Bool {
        meta?.builtin_draft == true || id.hasPrefix("g_draft_")
    }

    public var isEnhanced1080p: Bool {
        isVideo && (meta?.post != nil || (info?.fps ?? 0) >= 50 || (info?.width ?? 0) >= 1920 || name.contains("1080p60fps"))
    }

    public var isWorld3D: Bool {
        meta?.task == "lyra" || meta?.model_id == "lyra-2" || name.contains("world") || name.contains("3D")
    }

    public var is2KImage: Bool {
        isImage && ((info?.width ?? meta?.width ?? 0) >= 1600)
    }

    public var localFileURL: URL {
        let root = Self.galleryRootURL
        if let p = path, !p.isEmpty {
            let u = URL(fileURLWithPath: p)
            if FileManager.default.fileExists(atPath: u.path) {
                return u
            }
        }
        if let r = rel, !r.isEmpty {
            let u = root.appendingPathComponent(r)
            if FileManager.default.fileExists(atPath: u.path) {
                return u
            }
        }
        if let uStr = url, uStr.hasPrefix("/media/") {
            let sub = String(uStr.dropFirst("/media/".count))
            let u = root.appendingPathComponent(sub)
            if FileManager.default.fileExists(atPath: u.path) {
                return u
            }
        }
        // Fallback: check root/name or root/drafts/name
        let direct = root.appendingPathComponent(name)
        if FileManager.default.fileExists(atPath: direct.path) {
            return direct
        }
        let draftFallback = root.appendingPathComponent("drafts").appendingPathComponent(name)
        if FileManager.default.fileExists(atPath: draftFallback.path) {
            return draftFallback
        }
        if let r = rel, !r.isEmpty {
            return root.appendingPathComponent(r)
        }
        return direct
    }

    public var localThumbURL: URL {
        let root = Self.galleryRootURL
        let directThumb = root.appendingPathComponent(".thumbs/\(id).jpg")
        if FileManager.default.fileExists(atPath: directThumb.path) {
            return directThumb
        }
        if let tr = thumb_rel, !tr.isEmpty,
           !tr.lowercased().hasSuffix(".mp4"), !tr.lowercased().hasSuffix(".mov") {
            return root.appendingPathComponent(tr)
        }
        if let t = thumb, t.hasPrefix("/media/"),
           !t.lowercased().hasSuffix(".mp4"), !t.lowercased().hasSuffix(".mov") {
            let sub = String(t.dropFirst("/media/".count))
            return root.appendingPathComponent(sub)
        }
        return directThumb
    }

    public var isRecentlyCreated: Bool {
        guard !isBuiltinDraft, let c = created else { return false }
        let age = Date().timeIntervalSince1970 - c
        return age >= -60 && age < 900 // Created within last 15 minutes
    }

    public var formattedTimeText: String {
        guard let c = created, c > 0 else { return isBuiltinDraft ? "内置预设" : "" }
        let age = Date().timeIntervalSince1970 - c
        if age >= -30 && age < 180 {
            return "刚刚生成"
        }
        let date = Date(timeIntervalSince1970: c)
        let fmt = DateFormatter()
        fmt.dateFormat = "HH:mm"
        return fmt.string(from: date)
    }

    public var localStripURL: URL {
        let root = Self.galleryRootURL
        if let st = strip_thumb, st.hasPrefix("/media/") {
            let sub = String(st.dropFirst("/media/".count))
            return root.appendingPathComponent(sub)
        }
        return root.appendingPathComponent(".thumbs/\(id)_strip.jpg")
    }

    public var displayTitle: String {
        if let t = meta?.title, !t.isEmpty {
            return t
        }
        if name.contains("宫崎骏天空之城") || (meta?.prompt?.contains("天空之城") == true) || (meta?.scene?.contains("floating sky island") == true) {
            if isEnhanced1080p {
                let spd = Int(meta?.post?.speed ?? (name.contains("2x") ? 2 : 4))
                return "宫崎骏天空之城 · 3D 穿梭 (\(spd)× 1080p60)"
            } else if isVideo {
                return "宫崎骏天空之城 · Lyra 2.0 原始 3D 漫游"
            } else if name.contains("input_frame") {
                return "宫崎骏天空之城 · Lyra 3D 首帧锚点"
            }
            return "宫崎骏天空之城 · 2K 原生立绘"
        }
        if name.contains("失落神庙") || (meta?.scene?.contains("stepped temple") == true) {
            if isEnhanced1080p {
                let spd = Int(meta?.post?.speed ?? (name.contains("2x") ? 2 : 4))
                return "远古失落神殿 · 3D 穿梭 (\(spd)× 1080p60)"
            } else if isVideo {
                return "远古失落神殿 · Lyra 2.0 原始 3D 漫游"
            } else if name.contains("input_frame") {
                return "远古失落神殿 · Lyra 3D 首帧锚点"
            }
        }
        if let p = meta?.prompt, !p.isEmpty {
            let trimmed = p.trimmingCharacters(in: .whitespacesAndNewlines)
            return String(trimmed.prefix(32))
        }
        return name
    }

    public var subtitlePrompt: String {
        if let p = meta?.prompt, !p.isEmpty { return p }
        if let s = meta?.scene, !s.isEmpty { return s }
        return name
    }

    public var pixelWidth: Int {
        info?.width ?? meta?.width ?? 1920
    }

    public var pixelHeight: Int {
        info?.height ?? meta?.height ?? 1080
    }

    public var resolutionBadge: String {
        let w = pixelWidth
        let h = pixelHeight
        if w >= 2500 {
            return "2K · \(w)×\(h)"
        } else if w >= 1920 {
            return "1080p · \(w)×\(h)"
        }
        return "\(w)×\(h)"
    }

    public var fpsBadge: String? {
        guard isVideo, let fps = info?.fps, fps > 0 else { return nil }
        return "\(Int(round(fps))) fps"
    }

    public var durationBadge: String? {
        guard isVideo, let d = info?.duration, d > 0 else { return nil }
        return String(format: "%.1fs", d)
    }

    public var fileSizeBadge: String {
        guard let sz = info?.size, sz > 0 else { return "" }
        let mb = Double(sz) / (1024.0 * 1024.0)
        return String(format: "%.1f MB", mb)
    }

    public var trajectoryBadge: String? {
        if let post = meta?.post {
            let spd = Int(post.speed ?? 2)
            let interp = post.interp ?? 2
            return "RIFE ×\(interp) · \(spd)× 推进"
        }
        if let t = meta?.trajectory, !t.isEmpty {
            return t
        }
        if let m = meta?.mode, !m.isEmpty {
            return m == "flythrough" ? "Flythrough 全景穿梭" : m
        }
        return nil
    }
}

// MARK: - A/B Split-Screen Video Comparison Pair

public struct ABComparePair: Identifiable, Hashable, Sendable {
    public let id: String
    public let title: String
    public let subtitle: String
    public let rawItem: GalleryItem
    public let enhancedItem: GalleryItem
    public let speedFactor: Double
    public let interpFactor: Int

    public init(
        id: String,
        title: String,
        subtitle: String,
        rawItem: GalleryItem,
        enhancedItem: GalleryItem,
        speedFactor: Double = 2.0,
        interpFactor: Int = 2
    ) {
        self.id = id
        self.title = title
        self.subtitle = subtitle
        self.rawItem = rawItem
        self.enhancedItem = enhancedItem
        self.speedFactor = speedFactor
        self.interpFactor = interpFactor
    }
}

// MARK: - Scene Presets, Styles, Aspects & Lyra 2.0 Trajectories

public struct ScenePreset: Identifiable, Hashable, Sendable {
    public let id: String
    public let name: String
    public let badge: String
    public let draftFilename: String
    public let prompt: String
    public let lyraScene: String
    public let accentHex: String
    public let icon: String

    public static let all: [ScenePreset] = [
        ScenePreset(
            id: "ghibli_laputa",
            name: "宫崎骏天空之城",
            badge: "吉卜力手绘 · 2K 母版",
            draftFilename: "g1_laputa_anime.png",
            prompt: "宫崎骏《天空之城》风格的漂浮天空之岛，晴朗夏日，湛蓝天空堆满巨大洁白积云，一条长满青草与小野花的古老石板小路从画面正下方中央笔直延伸向远方，两侧是爬满藤蔓的古老石拱门一座接一座排成长廊，尽头是被巨大古树覆盖的圆形古城堡，岛边小瀑布流向云海，没有人物，单点透视，层次丰富，吉卜力手绘动画美术风格，原生2K",
            lyraScene: "a long grassy stone path lined with ivy-covered ancient stone arches on a floating sky island, leading toward a round ancient castle crowned by a giant tree, huge white cumulus clouds in a bright blue sky, Studio Ghibli style",
            accentHex: "#38BDF8",
            icon: "cloud.sun.fill"
        ),
        ScenePreset(
            id: "torii_maple",
            name: "京都千本鸟居",
            badge: "深秋红枫 · 纵深长廊",
            draftFilename: "s1_torii_maple.png",
            prompt: "深秋京都伏见稻荷，成千上万座朱红色鸟居层层叠叠组成的幽深隧道，沿着长满青苔的石阶一路向山林深处延伸，鸟居外是燃烧般火红与金黄的枫叶，金色夕阳光束从缝隙间穿透，薄雾弥漫，没有人物，单点透视，电影级实拍质感，原生2K",
            lyraScene: "an endless tunnel of vermilion torii gates along mossy stone stairs, surrounded by blazing red and golden maple trees, golden sunbeams and soft mist",
            accentHex: "#F97316",
            icon: "torii"
        ),
        ScenePreset(
            id: "cyber_alley",
            name: "新东京赛博雨巷",
            badge: "全息霓虹 · 湿滑镜面",
            draftFilename: "s3_cyber_alley.png",
            prompt: "雨夜赛博朋克未来都市窄巷，湿漉漉街道倒映漫天霓虹，两侧高楼贴满巨大全息广告牌，空中交错电缆与天桥，巷子尽头耸入云霄的巨型摩天楼，没有人物，单点透视，原生2K",
            lyraScene: "a narrow rain-soaked cyberpunk alley with neon holographic signs, cables and skybridges overhead, leading to a colossal skyscraper",
            accentHex: "#EC4899",
            icon: "bolt.horizontal.circle.fill"
        ),
        ScenePreset(
            id: "lost_temple",
            name: "失落神庙",
            badge: "雨林丁达尔 · 巨像石廊",
            draftFilename: "s4_lost_temple.png",
            prompt: "被热带雨林吞没的远古失落神殿峡谷，古老石板步道穿过两侧巨型石刻神像与爬满藤蔓的石柱长廊，延伸向远处巨大的金字塔神殿，瀑布从悬崖倾泻，丁达尔光柱，薄雾缭绕，没有人物，单点透视，电影级实拍质感，原生2K",
            lyraScene: "an ancient stone walkway between giant carved guardian statues and vine-covered pillars in a jungle canyon, leading to a colossal stepped temple, waterfalls and god rays",
            accentHex: "#10B981",
            icon: "building.columns.fill"
        ),
        ScenePreset(
            id: "ice_palace",
            name: "极光水晶冰宫",
            badge: "极光折射 · 冰雕拱廊",
            draftFilename: "s5_ice_palace.png",
            prompt: "极光之夜的冰雪水晶宫殿长廊，晶莹冰面长廊两侧是高耸的冰晶柱与冰雕拱门层层向远方延伸，冰柱透出幽蓝青绿光芒，天空绚烂极光，远处巨大冰晶城堡，没有人物，单点透视，原生2K",
            lyraScene: "a long corridor of glowing translucent ice pillars and carved ice arches leading to a giant crystal ice castle under green and violet aurora",
            accentHex: "#06B6D4",
            icon: "snowflake"
        ),
        ScenePreset(
            id: "lantern_town",
            name: "万灯水乡",
            badge: "大唐夜宴 · 千灯古街",
            draftFilename: "s6_lantern_town.png",
            prompt: "夜晚的中国古风水乡长街，青石板路沿河道延伸向远方，两侧层层叠叠的木结构古楼挂满成百上千盏暖红灯笼，石拱桥横跨河面，远处灯火辉煌的高塔，没有人物，单点透视，原生2K",
            lyraScene: "a night-time ancient Chinese water-town street lined with wooden houses and hundreds of glowing red lanterns, a stone arch bridge and a golden pagoda in the distance",
            accentHex: "#F59E0B",
            icon: "flame.fill"
        ),
        ScenePreset(
            id: "sky_city",
            name: "云海白玉仙宫",
            badge: "东方仙侠 · 浮空金殿",
            draftFilename: "s2_sky_city.png",
            prompt: "云海之上的东方仙侠天空之城，一座悬空的白玉石桥从脚下笔直伸向远方，石桥两侧是巨大的悬浮山峰与层层叠叠的金顶宫殿楼阁，飞檐斗拱挂满发光的灯笼，瀑布从悬浮山上倾泻进无边云海，原生2K",
            lyraScene: "a white jade bridge stretching across a sea of clouds between floating mountains and golden-roofed celestial palaces with waterfalls and glowing lanterns",
            accentHex: "#8B5CF6",
            icon: "sparkles"
        )
    ]
}

public struct StylePreset: Identifiable, Hashable, Sendable {
    public let id: String
    public let name: String
    public let suffix: String
    public let icon: String

    public static let all: [StylePreset] = [
        StylePreset(id: "none", name: "原生直出", suffix: "", icon: "wand.and.stars"),
        StylePreset(id: "ghibli", name: "吉卜力手绘", suffix: "，吉卜力工作室手绘动画美术风格，水彩水粉质感背景，柔和明亮的色彩，宫崎骏电影截图级别", icon: "paintbrush.fill"),
        StylePreset(id: "cinematic", name: "IMAX 电影写实", suffix: "，电影级超写实实拍质感，IMAX摄影机，体积光，HDR，电影级色彩分级，细节极其丰富，原生2K", icon: "camera.aperture"),
        StylePreset(id: "ue5", name: "虚幻 5 次世代", suffix: "，虚幻引擎5实时渲染，次世代3A游戏CG，体积雾，光线追踪，史诗级场景", icon: "cube.fill"),
        StylePreset(id: "pixar", name: "3D 动画渲染", suffix: "，皮克斯迪士尼风格3D动画电影画面，柔和全局光照，可爱精致，细节丰富", icon: "sparkles.rectangle.stack"),
        StylePreset(id: "ink", name: "东方水墨国风", suffix: "，中国传统水墨画风格，留白意境，淡雅设色，宣纸质感", icon: "drop.fill"),
        StylePreset(id: "portrait", name: "哈苏中画幅", suffix: "，顶级商业影楼人像摄影，哈苏中画幅，85mm f/1.4，柔和轮廓光，真实皮肤质感，杂志封面级", icon: "person.crop.rectangle"),
        StylePreset(id: "poster", name: "商业中文海报", suffix: "，高级商业海报设计，精致排版，中文标题清晰锐利，构图大气", icon: "text.below.photo.fill")
    ]
}

public struct AspectPreset: Identifiable, Hashable, Sendable {
    public let id: String
    public let name: String
    public let width: Int
    public let height: Int

    public static let all: [AspectPreset] = [
        AspectPreset(id: "16:9", name: "16:9 横屏 2K (2752×1536)", width: 2752, height: 1536),
        AspectPreset(id: "lyra", name: "16:9 Lyra 黄金比 (1664×960)", width: 1664, height: 960),
        AspectPreset(id: "21:9", name: "21:9 电影宽银幕 (3024×1296)", width: 3024, height: 1296),
        AspectPreset(id: "9:16", name: "9:16 竖屏 2K (1536×2752)", width: 1536, height: 2752),
        AspectPreset(id: "1:1", name: "1:1 极清方图 (2048×2048)", width: 2048, height: 2048),
        AspectPreset(id: "4:3", name: "4:3 经典画幅 (2368×1776)", width: 2368, height: 1776),
        AspectPreset(id: "3:4", name: "3:4 竖版海报 (1776×2368)", width: 1776, height: 2368)
    ]
}

public struct LyraDurationPreset: Identifiable, Hashable, Sendable {
    public let id: String
    public let title: String
    public let subtitle: String
    public let badge: String
    public let totalFrames: Int
    public let durationSeconds: Double
    public let zoomOutFrames: Int
    public let zoomInFrames: Int
    public let singleFrames: Int

    public static let all: [LyraDurationPreset] = [
        LyraDurationPreset(
            id: "nvidia_30s_481f",
            title: "30秒官方长片 (481帧)",
            subtitle: "复刻 @NVIDIAAI 官宣演示 · 后退 241 帧 + 前推 241 帧",
            badge: "30.0s · @NVIDIAAI 同款",
            totalFrames: 481,
            durationSeconds: 30.06,
            zoomOutFrames: 241,
            zoomInFrames: 241,
            singleFrames: 481
        ),
        LyraDurationPreset(
            id: "epic_45s_721f",
            title: "45秒史诗长镜头 (721帧)",
            subtitle: "9 段自回归 3DGS 空间接力 · 后退 241 帧 + 纵深前推 481 帧",
            badge: "45.0s · 史诗一镜到底",
            totalFrames: 721,
            durationSeconds: 45.06,
            zoomOutFrames: 241,
            zoomInFrames: 481,
            singleFrames: 721
        ),
        LyraDurationPreset(
            id: "fast_15s_241f",
            title: "15秒快速预览 (241帧)",
            subtitle: "3 段快速勘景 · 后退 81 帧 + 前推 161 帧",
            badge: "15.0s · 极速验景",
            totalFrames: 241,
            durationSeconds: 15.06,
            zoomOutFrames: 81,
            zoomInFrames: 161,
            singleFrames: 241
        )
    ]
}

public struct LyraTrajectoryDescriptor: Identifiable, Hashable, Sendable {
    public let id: String
    public let name: String
    public let englishTag: String
    public let subtitle: String
    public let icon: String
    public let backendMode: String
    public let backendTrajectory: String
    public let backendDirection: String
    public let defaultStrength: Double
    public let minStrength: Double
    public let maxStrength: Double
    public let unitLabel: String

    public static let all: [LyraTrajectoryDescriptor] = [
        LyraTrajectoryDescriptor(
            id: "flythrough",
            name: "全景纵深穿梭",
            englishTag: "flythrough",
            subtitle: "双向段逆序无缝拼接（后退段翻转 + 前推段），打造超长一镜到底穿越长廊",
            icon: "airplane.departure",
            backendMode: "flythrough",
            backendTrajectory: "horizontal_zoom",
            backendDirection: "right",
            defaultStrength: 2.2,
            minStrength: 0.5,
            maxStrength: 4.5,
            unitLabel: "× 场景深度"
        ),
        LyraTrajectoryDescriptor(
            id: "Shrink-Grow",
            name: "希区柯克呼吸变焦",
            englishTag: "Shrink-Grow",
            subtitle: "镜头前推伴随螺旋俯仰呼吸感，营造梦境空间尺度伸缩",
            icon: "arrow.up.left.and.down.right.magnifyingglass",
            backendMode: "single",
            backendTrajectory: "horizontal_spiral",
            backendDirection: "right",
            defaultStrength: 1.6,
            minStrength: 0.2,
            maxStrength: 4.0,
            unitLabel: "× 螺旋深度"
        ),
        LyraTrajectoryDescriptor(
            id: "forward_orbit",
            name: "推进俯冲掠影",
            englishTag: "forward_orbit",
            subtitle: "向前推进同时带轻微俯冲弧线，适合飞越浮岛与古建筑群",
            icon: "location.north.line.fill",
            backendMode: "single",
            backendTrajectory: "horizontal_zoom_bend",
            backendDirection: "right",
            defaultStrength: 1.8,
            minStrength: 0.2,
            maxStrength: 4.5,
            unitLabel: "× 俯冲深度"
        ),
        LyraTrajectoryDescriptor(
            id: "waves",
            name: "正弦波浪漫游",
            englishTag: "waves",
            subtitle: "沿纵深方向呈柔和双螺旋起伏推进，极具吉卜力飞行器漂浮感",
            icon: "water.waves",
            backendMode: "single",
            backendTrajectory: "spiral",
            backendDirection: "right",
            defaultStrength: 1.2,
            minStrength: 0.2,
            maxStrength: 3.0,
            unitLabel: "× 波浪幅度"
        ),
        LyraTrajectoryDescriptor(
            id: "orbit",
            name: "360° 环绕凝视",
            englishTag: "orbit",
            subtitle: "围绕场景视觉中心做平滑圆弧环绕，充分展现 3D 高斯点云立体视差",
            icon: "arrow.triangle.2.circlepath.camera.fill",
            backendMode: "single",
            backendTrajectory: "orbit_horizontal",
            backendDirection: "right",
            defaultStrength: 0.65,
            minStrength: 0.1,
            maxStrength: 1.6,
            unitLabel: "弧度 (rad)"
        ),
        LyraTrajectoryDescriptor(
            id: "zoom_in",
            name: "直线极速前推",
            englishTag: "zoom_in",
            subtitle: "沿画面消失点笔直向前推进，最稳定清晰的纵深探索轨迹",
            icon: "arrow.up.circle.fill",
            backendMode: "single",
            backendTrajectory: "horizontal_zoom",
            backendDirection: "right",
            defaultStrength: 2.0,
            minStrength: 0.2,
            maxStrength: 5.0,
            unitLabel: "× 推进深度"
        ),
        LyraTrajectoryDescriptor(
            id: "zoom_out",
            name: "史诗缓慢拉远",
            englishTag: "zoom_out",
            subtitle: "从主体细节缓缓向后拉出并微抬视角，揭示宏大世界全貌",
            icon: "arrow.down.backward.circle.fill",
            backendMode: "single",
            backendTrajectory: "horizontal_zoom",
            backendDirection: "left",
            defaultStrength: 1.5,
            minStrength: 0.2,
            maxStrength: 4.0,
            unitLabel: "× 拉远深度"
        ),
        LyraTrajectoryDescriptor(
            id: "left_right",
            name: "电影摇臂横移",
            englishTag: "left_right",
            subtitle: "镜头横向平滑移动并锁定远景主体，前景石柱产生强烈遮挡视差",
            icon: "arrow.left.and.right.circle.fill",
            backendMode: "single",
            backendTrajectory: "horizontal",
            backendDirection: "right",
            defaultStrength: 0.9,
            minStrength: 0.1,
            maxStrength: 3.0,
            unitLabel: "× 横移跨度"
        ),
        LyraTrajectoryDescriptor(
            id: "up_down",
            name: "垂直航拍升降",
            englishTag: "up_down",
            subtitle: "镜头垂直拔高或俯降，从地面步道升向云端古堡穹顶",
            icon: "arrow.up.and.down.circle.fill",
            backendMode: "single",
            backendTrajectory: "vertical_simple",
            backendDirection: "up",
            defaultStrength: 0.75,
            minStrength: 0.1,
            maxStrength: 3.0,
            unitLabel: "× 升降高度"
        )
    ]

    /// Evaluates normalized 3D camera position (x, y, z) and look-at angles (yaw, pitch, roll)
    /// for `t` in `0.0 ... 1.0`, powering our 60fps interactive 3D Trajectory Canvas.
    public func sampleCameraPose(t: Double, strength: Double) -> (pos: Vec3D, lookYaw: Double, lookPitch: Double, fovScale: Double) {
        let clamped = min(1.0, max(0.0, t))
        let s = max(0.2, min(3.5, strength)) / 2.0

        switch id {
        case "flythrough":
            let z = -1.2 + clamped * 2.5 * s
            let y = 0.18 * (1.0 - clamped) * sin(clamped * .pi)
            let x = 0.04 * sin(clamped * .pi * 2.0)
            return (Vec3D(x, y, z), -x * 0.25, -0.05 * cos(clamped * .pi), 1.0)

        case "Shrink-Grow":
            let z = -1.0 + clamped * 2.0 * s
            let angle = clamped * .pi * 4.0
            let radius = 0.18 * sin(clamped * .pi) * s
            let x = cos(angle) * radius
            let y = sin(angle) * radius * 0.7
            let fov = 1.0 + 0.25 * sin(clamped * .pi * 2.0)
            return (Vec3D(x, y, z), -x * 0.35, -y * 0.35, fov)

        case "forward_orbit":
            let z = -1.1 + clamped * 2.2 * s
            let y = 0.35 * (1.0 - clamped) - 0.15 * sin(clamped * .pi)
            let x = 0.22 * sin(clamped * .pi) * s
            return (Vec3D(x, y, z), -x * 0.45, -0.14 * sin(clamped * .pi), 1.0)

        case "waves":
            let z = -1.1 + clamped * 2.2 * s
            let x = 0.32 * sin(clamped * .pi * 3.0) * s
            let y = 0.18 * cos(clamped * .pi * 4.0) * s
            return (Vec3D(x, y, z), -x * 0.3, -y * 0.3, 1.0)

        case "orbit":
            let theta = (clamped - 0.5) * .pi * 0.85 * s
            let radius = 1.35
            let x = sin(theta) * radius
            let z = -cos(theta) * radius + 0.35
            let y = 0.12 * sin(clamped * .pi * 2.0)
            return (Vec3D(x, y, z), -theta * 0.9, -0.05, 1.0)

        case "zoom_in":
            let z = -1.2 + clamped * 2.4 * s
            return (Vec3D(0, 0, z), 0, 0, 1.0)

        case "zoom_out":
            let z = 1.1 - clamped * 2.3 * s
            let y = 0.28 * clamped * s
            return (Vec3D(0, y, z), 0, -0.12 * clamped, 1.0)

        case "left_right":
            let x = (-0.75 + clamped * 1.5) * s
            let z = -0.7 + 0.15 * sin(clamped * .pi)
            return (Vec3D(x, 0.02, z), -x * 0.45, 0, 1.0)

        case "up_down":
            let y = (-0.45 + clamped * 1.1) * s
            let z = -0.75 + 0.25 * clamped
            return (Vec3D(0, y, z), 0, -y * 0.35, 1.0)

        default:
            let z = -1.0 + clamped * 2.0 * s
            return (Vec3D(0, 0, z), 0, 0, 1.0)
        }
    }
}

// MARK: - Professional Aesthetic Cinema Camera Rigs (🎥 专业级唯美电影摄影机)

public struct CinemaCameraPreset: Identifiable, Hashable, Sendable {
    public let id: String
    public let name: String
    public let cameraSpec: String
    public let badge: String
    public let promptSuffix: String

    public static let all: [CinemaCameraPreset] = [
        CinemaCameraPreset(
            id: "iwai_85mm_f12",
            name: "🌸 岩井俊二·黄金逆光柔焦",
            cameraSpec: "ARRI Alexa 65 · Canon FD 85mm f/1.2L · Black Pro-Mist 1/4",
            badge: "人像最唯美",
            promptSuffix: ", captured on ARRI Alexa 65 paired with vintage Canon FD 85mm f/1.2L lens wide open at f/1.2, Tiffen Black Pro-Mist 1/4 soft filter, bathed in warm golden hour backlighting with glowing amber hair rim light, translucent porcelain skin with delicate rosy blush and subsurface scattering, ultra-shallow depth of field, creamy dreamy bokeh, soft Tyndall light rays, Kodak Portra 400 film aesthetic, 8K masterpiece cinematography"
        ),
        CinemaCameraPreset(
            id: "wong_kar_wai_anamorphic",
            name: "🌙 王家卫·暗夜霓虹变形宽银幕",
            cameraSpec: "ARRI Alexa Mini LF · Cooke Anamorphic 40mm T2.0",
            badge: "迷离电影感",
            promptSuffix: ", shot on ARRI Alexa Mini LF with vintage Cooke Anamorphic/i 40mm T2.0 lens, Wong Kar-wai and Christopher Doyle cinematography, sultry neon-drenched atmosphere, rich emerald green and warm crimson-amber color contrast, creamy oval anamorphic bokeh, horizontal blue-and-gold anamorphic lens flare streaks, rain-slicked reflections, Kodak Vision3 500T 35mm film grain, deeply poetic and melancholic film still"
        ),
        CinemaCameraPreset(
            id: "deakins_imax_65mm",
            name: "🌅 迪金斯·丁达尔黄金史诗",
            cameraSpec: "IMAX MSM 65mm · Panavision Sphero 50mm T1.3",
            badge: "史诗丁达尔光",
            promptSuffix: ", Roger Deakins masterclass cinematography, shot on IMAX 65mm film camera with Panavision Sphero 65 lens, dramatic volumetric golden hour god rays cutting through atmospheric mist, floating illuminated golden dust motes, natural motivated chiaroscuro lighting, breathtaking spatial depth and parallax, 8K ultra-detailed photorealistic cinema"
        ),
        CinemaCameraPreset(
            id: "leica_noctilux_f095",
            name: "💎 徕卡夜神·f/0.95 刀锐奶化",
            cameraSpec: "Sony Venice 2 8K · Leica Noctilux-M 50mm f/0.95",
            badge: "极限浅景深",
            promptSuffix: ", captured on Sony Venice 2 8K cinema camera with Leica Noctilux-M 50mm f/0.95 ASPH lens wide open at f/0.95, razor-sharp focus on expressive eyes with sparkling catchlights, signature dreamy swirly bokeh background, soft Rembrandt butterfly lighting, luminous dewy skin texture, haute couture editorial cinema portrait"
        ),
        CinemaCameraPreset(
            id: "shinkai_twilight_panavision",
            name: "🌌 新海诚·暮光云海星芒镜头",
            cameraSpec: "Panavision DXL2 8K · Ultra Panatar 1.3x",
            badge: "梦幻暮光",
            promptSuffix: ", shot on Panavision Millennium DXL2 with Ultra Panatar anamorphic lens, breathtaking magic hour twilight sky with violet-pink and cerulean glowing clouds, radiant sunburst lens flare, crystal-clear water reflection, ethereal rim lighting, hyper-detailed cinematic masterpiece"
        ),
        CinemaCameraPreset(
            id: "raw_lens",
            name: "📷 原生直出镜头 (无滤镜)",
            cameraSpec: "Standard 50mm Prime",
            badge: "原始",
            promptSuffix: ""
        )
    ]
}

// MARK: - Cinema Camera Movement Presets for Video (🎬 电影级唯美运镜调度)

public struct CinemaMovementPreset: Identifiable, Hashable, Sendable {
    public let id: String
    public let name: String
    public let englishSpec: String
    public let promptSuffix: String

    public static let all: [CinemaMovementPreset] = [
        CinemaMovementPreset(
            id: "dolly_rack_focus",
            name: "🎬 浅景深呼吸慢推 (Dolly-In + 焦点转移)",
            englishSpec: "120fps Slow-Mo Dolly-In + Rack Focus",
            promptSuffix: ", smooth 120fps slow-motion camera dolly-in with gentle rack focus from foreground floating petals/bokeh to the subject's expressive eyes, subtle natural hair and fabric movement in the breeze"
        ),
        CinemaMovementPreset(
            id: "slow_orbit_120fps",
            name: "🌸 120fps 唯美环绕慢镜 (Slow-Mo Orbit)",
            englishSpec: "Steadicam 180° Arc Orbit + Rim Light Flare",
            promptSuffix: ", fluid Steadicam slow-motion arc orbit around the subject at 120fps, golden rim light flaring softly across the lens, rich foreground-to-background parallax"
        ),
        CinemaMovementPreset(
            id: "wong_dolly_zoom",
            name: "🌙 王家卫希区柯克变焦 (Dolly Zoom)",
            englishSpec: "Vertigo Dolly Zoom + Step-Printing Blur",
            promptSuffix: ", cinematic Hitchcock dolly zoom compressing background space while keeping the subject in intimate close-up, subtle Wong Kar-wai step-printing poetic motion trail"
        ),
        CinemaMovementPreset(
            id: "epic_crane_up",
            name: "🌅 史诗摇臂升格掠镜 (Crane Up & Glide)",
            englishSpec: "Sweeping Techno-Crane Glide + God Rays",
            promptSuffix: ", sweeping Techno-Crane camera gliding forward and gently rising through volumetric god rays, revealing grand architectural depth"
        )
    ]
}

// MARK: - God-Tier Movie Scene & Master Prompt Vault (🎬 殿堂级唯美电影片段与神级提示词库)

public struct MasterpieceFilmScenePreset: Identifiable, Hashable, Sendable {
    public let id: String
    public let shortTag: String
    public let directorBadge: String
    public let cameraId: String
    public let prompt: String

    public static let all: [MasterpieceFilmScenePreset] = [
        MasterpieceFilmScenePreset(
            id: "iwai_love_letter_sakura",
            shortTag: "🌸 《情书》樱花逆光回眸",
            directorBadge: "岩井俊二柔焦慢镜",
            cameraId: "iwai_85mm_f12",
            prompt: "春日黄昏的镰仓木质车站，漫天樱花花瓣在夕阳逆光中缓慢飘落。一位清冷绝美的年轻东方女子身着轻盈丝质白裙，微风轻轻吹起她散落的栗色长发，她缓缓转头看向镜头，双眸清澈含光，白皙通透的脸颊带着淡淡的粉红红晕。Shot on ARRI Alexa 65 with Canon FD 85mm f/1.2L lens at f/1.2, Black Pro-Mist 1/4 filter, golden hour backlighting creating a glowing amber rim light around her hair, shallow depth of field with creamy bokeh, slow-motion 120fps camera dolly-in, rack focus from falling cherry blossom petals in the foreground to her expressive eyes."
        ),
        MasterpieceFilmScenePreset(
            id: "wong_in_the_mood_for_love",
            shortTag: "🌧️ 《花样年华》暗夜雨窗佳人",
            directorBadge: "王家卫×杜可风",
            cameraId: "wong_kar_wai_anamorphic",
            prompt: "凌晨两点的香港霓虹雨夜，复古旅馆窗前雨滴沿着玻璃缓缓滑落，窗外翠绿与绯红色的霓虹灯牌在湿漉漉的街面晕染开迷离光斑。一位身姿曼妙的绝美女子斜倚在窗边，暖黄台灯与冷色霓虹在她细腻白皙的肌肤上交织出暧昧光影，眼神迷离而深邃。Wong Kar-wai and Christopher Doyle aesthetic, shot on ARRI Alexa Mini LF with Cooke Anamorphic 40mm T2.0 lens, slow dolly zoom with subtle step-printing motion blur, rack focus from raindrops on the glass to her luminous eyes, rich emerald and crimson color grading, 35mm Kodak Vision3 500T film grain."
        ),
        MasterpieceFilmScenePreset(
            id: "deakins_dune_golden_goddess",
            shortTag: "🌅 《沙丘》丁达尔丝绸女神",
            directorBadge: "罗杰·迪金斯神光",
            cameraId: "deakins_imax_65mm",
            prompt: "黄昏日落最后三分钟的金色古老石殿拱廊，低悬的夕阳穿透金色薄雾投射出壮丽的丁达尔体积光束，空气中漂浮着发光的金色微尘。一位身披半透明香槟金丝绸长纱的绝美女神迎风而立，轻纱与长发在微风中如水波般飘逸流动，金色夕阳勾勒出她曼妙的身姿与粉嫩脸庞。Roger Deakins cinematography, shot on IMAX 65mm with Panavision anamorphic lens, volumetric sunbeams, slow sweeping crane shot orbiting around the subject, horizontal gold-and-blue anamorphic flare streaks, 8K masterpiece."
        ),
        MasterpieceFilmScenePreset(
            id: "leica_black_swan_ballet",
            shortTag: "🦢 《黑天鹅》晨曦芭蕾缪斯",
            directorBadge: "徕卡 f/0.95 刀锐奶化",
            cameraId: "leica_noctilux_f095",
            prompt: "清晨第一缕阳光穿透巴洛克歌剧院高耸的彩绘玻璃窗，洒下梦幻的丁达尔光柱。一位拥有天鹅颈与丝绸般透亮粉嫩肌肤的绝美芭蕾舞者立于光束中央，她微微仰首轻合双眸，纤长睫毛在逆光中清晰可见，锁骨与肩颈线条沐浴在柔和晨光里。Shot on Sony Venice 2 8K with Leica Noctilux-M 50mm f/0.95 ASPH wide open, razor-sharp focus on her face, dreamy swirly bokeh background, slow breathing camera push-in, luminous subsurface scattering skin texture."
        ),
        MasterpieceFilmScenePreset(
            id: "otaru_snow_queen",
            shortTag: "❄️ 《小樽雪国》极光雪原少女",
            directorBadge: "高调纯净唯美特写",
            cameraId: "iwai_85mm_f12",
            prompt: "漫天飘雪的北海道纯白雪原，天际泛着清透的冰蓝与淡粉色晚霞。一位肤若凝脂的绝美少女伫立在漫天飞舞的晶莹雪花中，她轻轻转头望向镜头，眼神温柔清澈，粉嫩微红的脸颊与纯白雪景形成极致唯美的对比。Shot on RED V-Raptor 8K VV with Canon K35 85mm T1.3 vintage lens, high-key ethereal natural light, crystalline snowflakes drifting in slow motion across the foreground with creamy bokeh, intimate slow dolly-in."
        ),
        MasterpieceFilmScenePreset(
            id: "malena_mediterranean_sun",
            shortTag: "🌊 《西西里》盛夏阳光海岸",
            directorBadge: "35mm 胶片暖阳",
            cameraId: "deakins_imax_65mm",
            prompt: "意大利阿马尔菲海岸盛夏午后的金色阳光，蔚蓝透明的海水拍打着礁石。一位明艳动人的年轻女子站在阳光斑驳的露台拱门下，海风拂过她微湿的卷发，金色阳光在她微红的脸颊与晶莹水珠上闪烁出迷人光泽。Shot on 35mm Kodak Vision3 250D film with Cooke S4/i 65mm lens, warm Mediterranean sun flare, shallow depth of field, gentle handheld camera breathing, vibrant nostalgic cinema aesthetic."
        ),
        MasterpieceFilmScenePreset(
            id: "changan_lantern_fairy",
            shortTag: "🏮 《千与千寻》万灯水乡画舫",
            directorBadge: "IMAX 东方幻想长镜",
            cameraId: "shinkai_twilight_panavision",
            prompt: "蓝调时刻的大唐千灯水乡，成千上万盏暖橘色孔明灯缓缓升向紫金暮空，河面铺满璀璨灯火倒影。一叶乌篷画舫划破水面，船头绝美古风女子手捧微光莲花灯，衣袂飘飘，满天星火在她眼眸中闪烁。Shot on ARRI Alexa 65 with Panavision Primo 50mm lens, cinematic crane shot gliding smoothly over the glowing river through floating sky lanterns, deep spatial parallax, 8K ultra-detailed."
        ),
        MasterpieceFilmScenePreset(
            id: "laputa_floating_castle_fpv",
            shortTag: "🏰 《天空之城》浮空古树云海",
            directorBadge: "Lyra 2.0 一镜到底",
            cameraId: "deakins_imax_65mm",
            prompt: "高耸入云的吉卜力风远古浮空城堡，遮天蔽日的参天巨树根系缠绕着布满青苔的石砌拱门，银河般的瀑布从浮岛边缘倾泻入金色云海，晨光穿透云层洒下神圣的丁达尔光束。A cinematic FPV drone shot glides smoothly forward through ancient mossy stone arches of a floating sky castle wrapped in giant tree roots above a sea of golden clouds, rich 3D parallax, volumetric god rays, IMAX 65mm cinematography."
        )
    ]
}
