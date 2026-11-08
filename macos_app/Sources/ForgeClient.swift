import Foundation

// MARK: - ForgeSSEEvent

public enum ForgeSSEEvent: Sendable {
    case stateUpdated
    case metricsUpdated(RemoteMetricsResponse)
    case jobsUpdated
    case galleryUpdated
    case logChunk(jobId: String, line: String)
    case heartbeat
}

public enum ForgeClientError: LocalizedError, Sendable {
    case invalidURL
    case serverError(status: Int, detail: String)
    case daemonUnavailable

    public var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "无效的本地服务地址"
        case .serverError(let status, let detail):
            return "HTTP \(status): \(detail)"
        case .daemonUnavailable:
            return "本地守护进程 (127.0.0.1:7788) 正在启动或未响应"
        }
    }
}

// MARK: - ForgeClient Actor

public actor ForgeClient {
    public static let shared = ForgeClient()

    public let baseURL: URL
    private let session: URLSession
    private let sseSession: URLSession
    private let decoder: JSONDecoder
    private var daemonProcess: Process?
    private var isBootstrapping = false

    public init(port: Int = 7788) {
        self.baseURL = URL(string: "http://127.0.0.1:\(port)")!

        let config = URLSessionConfiguration.ephemeral
        config.httpMaximumConnectionsPerHost = 8
        config.waitsForConnectivity = false
        config.timeoutIntervalForRequest = 15.0
        config.timeoutIntervalForResource = 300.0
        config.httpShouldUsePipelining = true
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        self.session = URLSession(configuration: config)

        let sseConfig = URLSessionConfiguration.ephemeral
        sseConfig.httpMaximumConnectionsPerHost = 2
        sseConfig.waitsForConnectivity = false
        sseConfig.timeoutIntervalForRequest = 3600.0
        sseConfig.timeoutIntervalForResource = 86400.0
        self.sseSession = URLSession(configuration: sseConfig)

        self.decoder = JSONDecoder()
    }

    // MARK: - Automatic Daemon Bootstrapper

    public func ensureDaemonRunning() async -> Bool {
        if await pingDaemon() {
            return true
        }
        guard !isBootstrapping else {
            try? await Task.sleep(nanoseconds: 500_000_000)
            return await pingDaemon()
        }
        isBootstrapping = true
        defer { isBootstrapping = false }

        let homeDir = FileManager.default.homeDirectoryForCurrentUser
        let forgeScriptCandidates: [String] = [
            URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent("forge.py").path,
            Bundle.main.bundleURL.deletingLastPathComponent().appendingPathComponent("forge.py").path,
            Bundle.main.resourceURL?.appendingPathComponent("forge.py").path ?? "",
            homeDir.appendingPathComponent("worldforge/forge.py").path,
            homeDir.appendingPathComponent(".gemini/antigravity/scratch/worldforge/forge.py").path
        ].filter { !$0.isEmpty }

        guard let scriptPath = forgeScriptCandidates.first(where: { FileManager.default.fileExists(atPath: $0) }) else {
            return false
        }

        let pythonCandidates = [
            "/usr/bin/python3",
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3"
        ]
        let pythonPath = pythonCandidates.first(where: { FileManager.default.isExecutableFile(atPath: $0) }) ?? "/usr/bin/python3"

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: pythonPath)
        proc.arguments = [scriptPath, "--port", "7788"]
        proc.currentDirectoryURL = URL(fileURLWithPath: scriptPath).deletingLastPathComponent()

        var env = ProcessInfo.processInfo.environment
        let extraPath = "\(FileManager.default.homeDirectoryForCurrentUser.path)/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
        env["PATH"] = extraPath + ":" + (env["PATH"] ?? "")
        env["PYTHONUNBUFFERED"] = "1"
        proc.environment = env
        proc.standardOutput = FileHandle.nullDevice
        proc.standardError = FileHandle.nullDevice

        do {
            try proc.run()
            self.daemonProcess = proc
        } catch {
            return false
        }

        for _ in 0..<25 {
            try? await Task.sleep(nanoseconds: 200_000_000)
            if await pingDaemon() {
                return true
            }
        }
        return false
    }

    public func pingDaemon() async -> Bool {
        var req = URLRequest(url: baseURL.appendingPathComponent("api/local/state"))
        req.timeoutInterval = 1.5
        do {
            let (_, resp) = try await session.data(for: req)
            if let http = resp as? HTTPURLResponse, (200..<400).contains(http.statusCode) {
                return true
            }
        } catch {}
        return false
    }

    // MARK: - Direct Zero-Overhead Disk Reader for ~/Movies/WorldForge/gallery.json

    public nonisolated func loadGalleryDirectFromDisk() async -> [GalleryItem] {
        await Task.detached(priority: .userInitiated) {
            let indexURL = GalleryItem.galleryRootURL.appendingPathComponent("gallery.json")
            guard let data = try? Data(contentsOf: indexURL) else {
                return []
            }
            let dec = JSONDecoder()
            if let indexFile = try? dec.decode(GalleryIndexFile.self, from: data) {
                return indexFile.items.sorted { ($0.created ?? 0) > ($1.created ?? 0) }
            }
            if let directArray = try? dec.decode([GalleryItem].self, from: data) {
                return directArray.sorted { ($0.created ?? 0) > ($1.created ?? 0) }
            }
            return []
        }.value
    }

    // MARK: - Core GET Endpoints

    public func fetchLocalState() async throws -> LocalStateResponse {
        try await getJSON(path: "/api/local/state")
    }

    public func fetchRemoteMetrics() async throws -> RemoteMetricsResponse {
        try await getJSON(path: "/api/remote/metrics", timeout: 6.0)
    }

    public func fetchRemoteModels() async throws -> [RemoteModelItem] {
        try await getJSON(path: "/api/remote/models", timeout: 10.0)
    }

    public func fetchRemoteJobs(limit: Int = 50) async throws -> [RemoteJobItem] {
        try await getJSON(path: "/api/remote/jobs?limit=\(limit)", timeout: 10.0)
    }

    public func fetchLocalTasks() async throws -> [LocalTaskItem] {
        try await getJSON(path: "/api/local/tasks", timeout: 6.0)
    }

    public func fetchGallery() async throws -> [GalleryItem] {
        try await getJSON(path: "/api/local/gallery", timeout: 8.0)
    }

    public func fetchJobLog(id: String, offset: Int = 0, isLocalTask: Bool) async throws -> JobLogChunk {
        let route = isLocalTask
            ? "/api/local/tasks/\(id)/log?offset=\(offset)"
            : "/api/remote/jobs/\(id)/log?offset=\(offset)"
        return try await getJSON(path: route, timeout: 6.0)
    }

    // MARK: - Mutations & Job Submission

    public func submitRemoteJob(modelId: String?, task: String, params: [String: Any]) async throws -> String {
        var body: [String: Any] = [
            "task": task,
            "params": params
        ]
        if let mid = modelId {
            body["model_id"] = mid
        }
        let dict = try await postJSONDict(path: "/api/remote/jobs", body: body)
        return (dict["job_id"] as? String) ?? ""
    }

    public func cancelRemoteJob(jobId: String) async throws {
        _ = try await postJSONDict(path: "/api/remote/jobs/\(jobId)/cancel", body: [:])
    }

    public func submitLocalPost(
        galleryId: String,
        speed: Double,
        interp: Int,
        scale: String,
        trimStart: Double = 0.0,
        trimEnd: Double? = nil,
        endHoldImage: String? = nil
    ) async throws -> String {
        var body: [String: Any] = [
            "gallery_id": galleryId,
            "speed": speed,
            "interp": interp,
            "scale": scale,
            "trim_start": trimStart
        ]
        if let te = trimEnd, te > trimStart {
            body["trim_end"] = te
        }
        if let ehi = endHoldImage, !ehi.isEmpty {
            body["end_hold_image"] = ehi
        }
        let res = try await postJSONDict(path: "/api/local/post", body: body)
        return (res["task_id"] as? String) ?? ""
    }

    public func startColabSession(name: String, gpu: String, connect: Bool = true) async throws -> String {
        let body: [String: Any] = ["name": name, "gpu": gpu, "connect": connect]
        let res = try await postJSONDict(path: "/api/local/session/start", body: body)
        return (res["task_id"] as? String) ?? ""
    }

    public func stopColabSession(name: String) async throws -> String {
        let body: [String: Any] = ["name": name]
        let res = try await postJSONDict(path: "/api/local/session/stop", body: body)
        return (res["task_id"] as? String) ?? ""
    }

    public func connectColabSession(name: String, gpu: String) async throws -> String {
        let body: [String: Any] = ["name": name, "gpu": gpu]
        let res = try await postJSONDict(path: "/api/local/connect", body: body)
        return (res["task_id"] as? String) ?? ""
    }

    public func disconnectColabTunnel() async throws {
        _ = try await postJSONDict(path: "/api/local/disconnect", body: [:])
    }

    public func refreshColabCLI() async throws {
        _ = try await postJSONDict(path: "/api/local/refresh", body: [:])
    }

    nonisolated public static func parseHuggingFaceInput(_ raw: String) -> (repo: String, subfolder: String) {
        var cleaned = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if let r = cleaned.range(of: "huggingface.co/") {
            cleaned = String(cleaned[r.upperBound...])
        }
        cleaned = cleaned.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        if let treeRange = cleaned.range(of: "/tree/main/") {
            let repoPart = String(cleaned[..<treeRange.lowerBound])
            let subPart = String(cleaned[treeRange.upperBound...]).trimmingCharacters(in: CharacterSet(charactersIn: "/"))
            return (repoPart, subPart)
        }
        return (cleaned, "")
    }

    public func addRemoteModel(repo: String, kind: String? = nil) async throws -> RemoteModelItem {
        let parsed = Self.parseHuggingFaceInput(repo)
        var payload: [String: Any] = ["repo": repo.trimmingCharacters(in: .whitespacesAndNewlines)]
        if !parsed.subfolder.isEmpty {
            payload["subfolder"] = parsed.subfolder
        }
        if let k = kind, !k.isEmpty {
            payload["kind"] = k
        }
        let data = try JSONSerialization.data(withJSONObject: payload)
        var req = URLRequest(url: URL(string: "/api/remote/models", relativeTo: baseURL)!)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = data
        let (respData, resp) = try await session.data(for: req)
        try validateHTTP(resp: resp, data: respData)
        return try decoder.decode(RemoteModelItem.self, from: respData)
    }

    public func triggerModelAction(modelId: String, action: String) async throws {
        if action == "delete" {
            var req = URLRequest(url: URL(string: "/api/remote/models/\(modelId)", relativeTo: baseURL)!)
            req.httpMethod = "DELETE"
            let (respData, resp) = try await session.data(for: req)
            try validateHTTP(resp: resp, data: respData)
        } else {
            _ = try await postJSONDict(path: "/api/remote/models/\(modelId)/\(action)", body: [:])
        }
    }

    public func deleteGalleryItem(id: String) async throws {
        var req = URLRequest(url: URL(string: "/api/local/gallery/\(id)", relativeTo: baseURL)!)
        req.httpMethod = "DELETE"
        let (respData, resp) = try await session.data(for: req)
        try validateHTTP(resp: resp, data: respData)
    }

    public func sendGalleryItemToRemote(galleryId: String) async throws -> String {
        let res = try await postJSONDict(path: "/api/local/to_remote", body: ["gallery_id": galleryId], timeout: 120.0)
        return (res["remote_path"] as? String) ?? ""
    }

    // MARK: - Binary Upload Off Main Thread (Zero Base64 Bloat)

    public func uploadFileBinary(fileURL: URL) async throws -> (remotePath: String?, localPath: String?) {
        let filename = fileURL.lastPathComponent
        let fileData = try await Task.detached(priority: .userInitiated) {
            try Data(contentsOf: fileURL, options: .mappedIfSafe)
        }.value

        var comps = URLComponents(url: baseURL.appendingPathComponent("api/local/upload"), resolvingAgainstBaseURL: false)!
        comps.queryItems = [URLQueryItem(name: "filename", value: filename)]
        guard let targetURL = comps.url else { throw ForgeClientError.invalidURL }

        var req = URLRequest(url: targetURL)
        req.httpMethod = "POST"
        req.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 120.0

        let (respData, resp) = try await session.upload(for: req, from: fileData)
        try validateHTTP(resp: resp, data: respData)
        let json = (try? JSONSerialization.jsonObject(with: respData) as? [String: Any]) ?? [:]
        return (json["remote_path"] as? String, json["local_path"] as? String)
    }

    // MARK: - Streaming SSE Consumer (/api/local/events)

    public func streamEvents(onEvent: @escaping @Sendable (ForgeSSEEvent) async -> Void) async {
        guard let eventsURL = URL(string: "/api/local/events", relativeTo: baseURL) else { return }
        var req = URLRequest(url: eventsURL)
        req.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        req.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
        req.timeoutInterval = 3600

        do {
            let (bytes, response) = try await sseSession.bytes(for: req)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                return
            }
            var currentEvent = "message"
            for try await line in bytes.lines {
                if Task.isCancelled { break }
                if line.hasPrefix("event:") {
                    currentEvent = line.dropFirst(6).trimmingCharacters(in: .whitespaces)
                } else if line.hasPrefix("data:") {
                    let payload = line.dropFirst(5).trimmingCharacters(in: .whitespaces)
                    if currentEvent == "metrics",
                       let data = payload.data(using: .utf8),
                       let m = try? decoder.decode(RemoteMetricsResponse.self, from: data) {
                        await onEvent(.metricsUpdated(m))
                    } else if currentEvent == "gallery" || payload.contains("gallery") {
                        await onEvent(.galleryUpdated)
                    } else if currentEvent == "jobs" || payload.contains("job") {
                        await onEvent(.jobsUpdated)
                    } else if currentEvent == "state" {
                        await onEvent(.stateUpdated)
                    } else {
                        await onEvent(.heartbeat)
                    }
                    currentEvent = "message"
                }
            }
        } catch {
            // Normal fallback to adaptive polling when SSE closes or is unsupported
        }
    }

    // MARK: - Internal Helpers

    private func getJSON<T: Decodable>(path: String, timeout: TimeInterval = 10.0) async throws -> T {
        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw ForgeClientError.invalidURL
        }
        var req = URLRequest(url: url)
        req.httpMethod = "GET"
        req.timeoutInterval = timeout
        let (data, resp) = try await session.data(for: req)
        try validateHTTP(resp: resp, data: data)
        return try decoder.decode(T.self, from: data)
    }

    private func postJSONDict(path: String, body: [String: Any], timeout: TimeInterval = 20.0) async throws -> [String: Any] {
        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw ForgeClientError.invalidURL
        }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = timeout
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, resp) = try await session.data(for: req)
        try validateHTTP(resp: resp, data: data)
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    private func validateHTTP(resp: URLResponse, data: Data) throws {
        guard let http = resp as? HTTPURLResponse else { return }
        guard (200..<300).contains(http.statusCode) else {
            var detail = HTTPURLResponse.localizedString(forStatusCode: http.statusCode)
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let d = json["detail"] as? String {
                detail = d
            } else if let str = String(data: data, encoding: .utf8), !str.isEmpty {
                detail = String(str.prefix(200))
            }
            throw ForgeClientError.serverError(status: http.statusCode, detail: detail)
        }
    }
}
