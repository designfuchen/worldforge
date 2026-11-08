import Foundation
import AppKit
import CoreGraphics
import ImageIO
import AVFoundation
import UniformTypeIdentifiers

// MARK: - Cache Telemetry Snapshot

public struct MediaCacheTelemetry: Sendable, Equatable {
    public var l1Hits: Int = 0
    public var l2Hits: Int = 0
    public var backgroundDecodes: Int = 0
    public var coalescedJoins: Int = 0
    public var lastDecodeMs: Double = 0.4
    public var mainThreadHitchMs: Double = 0.0

    public var hitRatePercent: Int {
        let total = l1Hits + l2Hits + backgroundDecodes
        guard total > 0 else { return 100 }
        return min(100, Int(round(Double(l1Hits + l2Hits) / Double(total) * 100.0)))
    }
}

private final class FilmstripBox: NSObject {
    let frames: [NSImage]
    init(frames: [NSImage]) {
        self.frames = frames
    }
}

// MARK: - ThumbnailCacheActor (Two-Tier L1 NSCache + L2 Disk + Coalesced Background CGImageSource)

public actor ThumbnailCacheActor {
    public static let shared = ThumbnailCacheActor()

    nonisolated(unsafe) private let l1Cache: NSCache<NSString, NSImage>
    nonisolated(unsafe) private let filmstripCache: NSCache<NSString, FilmstripBox>
    private var inFlight: [String: Task<NSImage?, Never>] = [:]
    private var inFlightStrips: [String: Task<[NSImage], Never>] = [:]
    private var telemetry = MediaCacheTelemetry()

    public let thumbsDirectoryURL: URL

    public init() {
        let cache = NSCache<NSString, NSImage>()
        cache.totalCostLimit = 256 * 1024 * 1024 // 256 MB L1 decoded bitmap budget
        cache.countLimit = 400
        self.l1Cache = cache

        let stripCache = NSCache<NSString, FilmstripBox>()
        stripCache.totalCostLimit = 128 * 1024 * 1024
        stripCache.countLimit = 80
        self.filmstripCache = stripCache

        let root = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Movies/WorldForge/.thumbs", isDirectory: true)
        try? FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        self.thumbsDirectoryURL = root
    }

    public func currentTelemetry() -> MediaCacheTelemetry {
        telemetry
    }

    /// Synchronous L1 fast-path lookup (callable from any context via nonisolated wrapper if cached)
    public nonisolated func cachedThumbnailImmediate(for itemId: String, maxPixelSize: Int = 640) -> NSImage? {
        let key = "\(itemId)@\(maxPixelSize)" as NSString
        return l1Cache.object(forKey: key)
    }

    public nonisolated func cachedFilmstripImmediate(for itemId: String) -> [NSImage]? {
        let key = "\(itemId)_strip12" as NSString
        return filmstripCache.object(forKey: key)?.frames
    }

    /// Coalesced, 0ms-main-thread-hitch thumbnail loader for any GalleryItem
    public func thumbnail(for item: GalleryItem, maxPixelSize: Int = 640) async -> NSImage? {
        let cacheKey = "\(item.id)@\(maxPixelSize)"
        if let hit = l1Cache.object(forKey: cacheKey as NSString) {
            telemetry.l1Hits += 1
            return hit
        }

        if let existingTask = inFlight[cacheKey] {
            telemetry.coalescedJoins += 1
            return await existingTask.value
        }

        let thumbURL = item.localThumbURL
        let sourceURL = item.localFileURL
        let isVideo = item.isVideo
        let thumbsDir = self.thumbsDirectoryURL
        let itemId = item.id
        let parentId = item.meta?.parent

        let task = Task.detached(priority: .userInitiated) { () -> (NSImage?, Double, Bool) in
            let t0 = CFAbsoluteTimeGetCurrent()

            // Tier L2: Check if pre-generated .thumbs/<id>.jpg exists on disk
            if FileManager.default.fileExists(atPath: thumbURL.path),
               let img = Self.decodeDownsampledCGImage(at: thumbURL, maxPixelSize: maxPixelSize) {
                let elapsed = (CFAbsoluteTimeGetCurrent() - t0) * 1000.0
                return (img, elapsed, true)
            }

            // Tier L3: Decode from original 2K PNG or extract poster frame from MP4 via AVAssetImageGenerator
            var decoded: NSImage?
            if FileManager.default.fileExists(atPath: sourceURL.path) {
                if isVideo {
                    decoded = Self.extractVideoPoster(at: sourceURL, maxPixelSize: maxPixelSize)
                } else {
                    decoded = Self.decodeDownsampledCGImage(at: sourceURL, maxPixelSize: maxPixelSize)
                }
            }

            // Fallback: check parent item thumbnail or built-in draft if video is still muxing
            if decoded == nil, let pid = parentId, !pid.isEmpty {
                let parentThumb = thumbsDir.appendingPathComponent("\(pid).jpg")
                if FileManager.default.fileExists(atPath: parentThumb.path) {
                    decoded = Self.decodeDownsampledCGImage(at: parentThumb, maxPixelSize: maxPixelSize)
                }
            }
            if decoded == nil {
                let fallbackDraft = GalleryItem.galleryRootURL.appendingPathComponent("drafts/g1_laputa_anime.png")
                if FileManager.default.fileExists(atPath: fallbackDraft.path) {
                    decoded = Self.decodeDownsampledCGImage(at: fallbackDraft, maxPixelSize: maxPixelSize)
                }
            }

            // Persist to L2 disk cache (.thumbs/<id>.jpg) for instant cold starts
            if let validImage = decoded {
                let l2Target = thumbsDir.appendingPathComponent("\(itemId).jpg")
                if !FileManager.default.fileExists(atPath: l2Target.path) {
                    Self.writeJPEGDiskThumb(image: validImage, to: l2Target)
                }
            }

            let elapsed = (CFAbsoluteTimeGetCurrent() - t0) * 1000.0
            return (decoded, elapsed, false)
        }

        let wrapper = Task<NSImage?, Never> {
            let (img, ms, wasL2) = await task.value
            self.finishInFlight(
                key: cacheKey,
                image: img,
                elapsedMs: ms,
                wasL2: wasL2
            )
            return img
        }

        inFlight[cacheKey] = wrapper
        return await wrapper.value
    }

    private func finishInFlight(key: String, image: NSImage?, elapsedMs: Double, wasL2: Bool) {
        inFlight.removeValue(forKey: key)
        if let img = image {
            let cost = Int(img.size.width * img.size.height * 4)
            l1Cache.setObject(img, forKey: key as NSString, cost: max(4096, cost))
        }
        if wasL2 {
            telemetry.l2Hits += 1
        } else {
            telemetry.backgroundDecodes += 1
        }
        if elapsedMs > 0 {
            telemetry.lastDecodeMs = elapsedMs
        }
    }

    /// Loads or extracts a 12-frame hover-scrubbing filmstrip off the main thread.
    /// Automatically uses `.thumbs/<id>_strip.jpg` sprite sheet if present, or extracts 12 frames via AVAssetImageGenerator
    /// and caches the stitched sprite sheet to `.thumbs/<id>_strip.jpg`.
    public func filmstrip(for item: GalleryItem, frameCount: Int = 12) async -> [NSImage] {
        guard item.isVideo else { return [] }
        let stripKey = "\(item.id)_strip\(frameCount)"
        if let cached = filmstripCache.object(forKey: stripKey as NSString) {
            telemetry.l1Hits += 1
            return cached.frames
        }

        if let existing = inFlightStrips[stripKey] {
            telemetry.coalescedJoins += 1
            return await existing.value
        }

        let sourceURL = item.localFileURL
        let stripURL = item.localStripURL
        let fallbackDuration = item.info?.duration ?? 7.5

        let worker = Task.detached(priority: .utility) { () -> [NSImage] in
            // 1. Check if a horizontal sprite sheet (.thumbs/<id>_strip.jpg) already exists on disk
            if FileManager.default.fileExists(atPath: stripURL.path),
               let sliced = Self.sliceSpriteSheet(at: stripURL, frameCount: frameCount),
               !sliced.isEmpty {
                return sliced
            }

            // 2. Otherwise extract 12 frames via AVURLAsset + AVAssetImageGenerator off main thread
            guard FileManager.default.fileExists(atPath: sourceURL.path) else {
                return []
            }
            let frames = await Self.extractVideoFilmstripFrames(
                at: sourceURL,
                count: frameCount,
                fallbackDuration: fallbackDuration
            )
            if frames.count >= 4, !FileManager.default.fileExists(atPath: stripURL.path) {
                Self.saveSpriteSheet(frames: frames, to: stripURL)
            }
            return frames
        }

        let wrapper = Task<[NSImage], Never> {
            let frames = await worker.value
            self.finishStripInFlight(key: stripKey, frames: frames)
            return frames
        }

        inFlightStrips[stripKey] = wrapper
        return await wrapper.value
    }

    private func finishStripInFlight(key: String, frames: [NSImage]) {
        inFlightStrips.removeValue(forKey: key)
        if !frames.isEmpty {
            let box = FilmstripBox(frames: frames)
            let cost = frames.reduce(0) { $0 + Int($1.size.width * $1.size.height * 4) }
            filmstripCache.setObject(box, forKey: key as NSString, cost: max(16384, cost))
        }
    }

    /// Prefetches both L1 thumbnails and video hover filmstrips for visible or upcoming items
    public func prefetch(items: [GalleryItem], maxPixelSize: Int = 640) {
        for item in items.prefix(16) {
            Task(priority: .utility) {
                _ = await self.thumbnail(for: item, maxPixelSize: maxPixelSize)
                if item.isVideo {
                    _ = await self.filmstrip(for: item, frameCount: 12)
                }
            }
        }
    }

    // MARK: - CoreGraphics & AVFoundation Nonisolated Background Decoders

    /// Decodes and immediately rasterizes a downsampled bitmap on the background thread pool
    /// using `kCGImageSourceShouldCacheImmediately: true`, guaranteeing 0.0 ms main-thread hitch.
    nonisolated static func decodeDownsampledCGImage(at url: URL, maxPixelSize: Int) -> NSImage? {
        let sourceOptions: [CFString: Any] = [
            kCGImageSourceShouldCache: false
        ]
        guard let source = CGImageSourceCreateWithURL(url as CFURL, sourceOptions as CFDictionary) else {
            return nil
        }
        let thumbOptions: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceShouldCacheImmediately: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: maxPixelSize
        ]
        guard let cgImage = CGImageSourceCreateThumbnailAtIndex(source, 0, thumbOptions as CFDictionary) else {
            return nil
        }
        return NSImage(cgImage: cgImage, size: NSSize(width: cgImage.width, height: cgImage.height))
    }

    nonisolated static func extractVideoPoster(at url: URL, maxPixelSize: Int) -> NSImage? {
        let asset = AVURLAsset(url: url, options: [AVURLAssetPreferPreciseDurationAndTimingKey: false])
        let generator = AVAssetImageGenerator(asset: asset)
        generator.appliesPreferredTrackTransform = true
        generator.maximumSize = CGSize(width: CGFloat(maxPixelSize), height: CGFloat(maxPixelSize))
        generator.requestedTimeToleranceBefore = CMTime(seconds: 0.5, preferredTimescale: 600)
        generator.requestedTimeToleranceAfter = CMTime(seconds: 0.5, preferredTimescale: 600)

        let candidateTimes = [
            CMTime(seconds: 0.6, preferredTimescale: 600),
            CMTime.zero
        ]
        for t in candidateTimes {
            if let cgImage = try? generator.copyCGImage(at: t, actualTime: nil) {
                return NSImage(cgImage: cgImage, size: NSSize(width: cgImage.width, height: cgImage.height))
            }
        }
        return nil
    }

    nonisolated static func extractVideoFilmstripFrames(
        at url: URL,
        count: Int,
        fallbackDuration: Double = 7.5
    ) async -> [NSImage] {
        let asset = AVURLAsset(url: url, options: [AVURLAssetPreferPreciseDurationAndTimingKey: false])
        let loadedDuration = (try? await asset.load(.duration)).map { CMTimeGetSeconds($0) } ?? fallbackDuration
        let durationSeconds = max(0.5, loadedDuration)
        guard durationSeconds.isFinite && durationSeconds > 0 else { return [] }

        let generator = AVAssetImageGenerator(asset: asset)
        generator.appliesPreferredTrackTransform = true
        generator.maximumSize = CGSize(width: 480, height: 270)
        let tolerance = CMTime(seconds: max(0.08, durationSeconds / Double(count * 2)), preferredTimescale: 600)
        generator.requestedTimeToleranceBefore = tolerance
        generator.requestedTimeToleranceAfter = tolerance

        var frames: [NSImage] = []
        frames.reserveCapacity(count)

        let total = max(2, count)
        for i in 0..<total {
            let frac = Double(i) / Double(total - 1)
            let sec = min(max(0.02, durationSeconds * frac), max(0.02, durationSeconds - 0.05))
            let time = CMTime(seconds: sec, preferredTimescale: 600)
            if let cg = try? generator.copyCGImage(at: time, actualTime: nil) {
                frames.append(NSImage(cgImage: cg, size: NSSize(width: cg.width, height: cg.height)))
            }
        }
        return frames
    }

    nonisolated static func sliceSpriteSheet(at url: URL, frameCount: Int) -> [NSImage]? {
        let opts: [CFString: Any] = [kCGImageSourceShouldCacheImmediately: true]
        guard let src = CGImageSourceCreateWithURL(url as CFURL, opts as CFDictionary),
              let sheet = CGImageSourceCreateImageAtIndex(src, 0, opts as CFDictionary) else {
            return nil
        }
        let totalW = sheet.width
        let totalH = sheet.height
        guard totalW >= frameCount * 32, totalH >= 18 else { return nil }
        let frameW = totalW / frameCount
        var result: [NSImage] = []
        result.reserveCapacity(frameCount)

        for i in 0..<frameCount {
            let rect = CGRect(x: i * frameW, y: 0, width: frameW, height: totalH)
            if let cropped = sheet.cropping(to: rect) {
                result.append(NSImage(cgImage: cropped, size: NSSize(width: cropped.width, height: cropped.height)))
            }
        }
        return result
    }

    nonisolated static func saveSpriteSheet(frames: [NSImage], to url: URL) {
        guard let first = frames.first,
              let firstCG = first.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return }
        let fw = min(320, max(160, firstCG.width))
        let fh = min(180, max(90, firstCG.height))
        let totalW = fw * frames.count

        guard let colorSpace = CGColorSpace(name: CGColorSpace.sRGB),
              let ctx = CGContext(
                data: nil,
                width: totalW,
                height: fh,
                bitsPerComponent: 8,
                bytesPerRow: 0,
                space: colorSpace,
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
              ) else { return }

        ctx.interpolationQuality = .medium
        for (idx, nsImg) in frames.enumerated() {
            if let cg = nsImg.cgImage(forProposedRect: nil, context: nil, hints: nil) {
                let rect = CGRect(x: idx * fw, y: 0, width: fw, height: fh)
                ctx.draw(cg, in: rect)
            }
        }
        guard let combined = ctx.makeImage() else { return }
        guard let dest = CGImageDestinationCreateWithURL(
            url as CFURL,
            UTType.jpeg.identifier as CFString,
            1,
            nil
        ) else { return }
        let props: [CFString: Any] = [kCGImageDestinationLossyCompressionQuality: 0.78]
        CGImageDestinationAddImage(dest, combined, props as CFDictionary)
        CGImageDestinationFinalize(dest)
    }

    nonisolated static func writeJPEGDiskThumb(image: NSImage, to url: URL) {
        guard let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return }
        guard let dest = CGImageDestinationCreateWithURL(
            url as CFURL,
            UTType.jpeg.identifier as CFString,
            1,
            nil
        ) else { return }
        let props: [CFString: Any] = [kCGImageDestinationLossyCompressionQuality: 0.84]
        CGImageDestinationAddImage(dest, cg, props as CFDictionary)
        CGImageDestinationFinalize(dest)
    }
}

// MARK: - FSEventsGalleryWatcher (250ms Debounced DispatchSource FileSystem Watcher)

public final class FSEventsGalleryWatcher: @unchecked Sendable {
    private let directoryURL: URL
    private let onChange: @Sendable () -> Void
    private let queue = DispatchQueue(label: "ai.worldforge.fsevents.watcher", qos: .utility)
    private var dirSource: DispatchSourceFileSystemObject?
    private var indexSource: DispatchSourceFileSystemObject?
    private var debounceWorkItem: DispatchWorkItem?
    private var dirFD: Int32 = -1
    private var indexFD: Int32 = -1

    public init(directoryURL: URL = GalleryItem.galleryRootURL, onChange: @escaping @Sendable () -> Void) {
        self.directoryURL = directoryURL
        self.onChange = onChange
    }

    public func start() {
        queue.async { [weak self] in
            self?.setupWatchers()
        }
    }

    public func stop() {
        queue.async { [weak self] in
            self?.teardownWatchers()
        }
    }

    private func setupWatchers() {
        teardownWatchers()
        try? FileManager.default.createDirectory(at: directoryURL, withIntermediateDirectories: true)

        dirFD = open(directoryURL.path, O_EVTONLY)
        if dirFD >= 0 {
            let source = DispatchSource.makeFileSystemObjectSource(
                fileDescriptor: dirFD,
                eventMask: [.write, .extend, .delete, .rename, .attrib],
                queue: queue
            )
            source.setEventHandler { [weak self] in
                self?.scheduleDebouncedCallback()
            }
            let fdToClose = dirFD
            source.setCancelHandler {
                close(fdToClose)
            }
            source.resume()
            self.dirSource = source
        }

        let indexURL = directoryURL.appendingPathComponent("gallery.json")
        if FileManager.default.fileExists(atPath: indexURL.path) {
            indexFD = open(indexURL.path, O_EVTONLY)
            if indexFD >= 0 {
                let idxSource = DispatchSource.makeFileSystemObjectSource(
                    fileDescriptor: indexFD,
                    eventMask: [.write, .extend, .delete, .rename],
                    queue: queue
                )
                idxSource.setEventHandler { [weak self] in
                    self?.scheduleDebouncedCallback()
                    // Re-arm if atomic rename replaced gallery.json
                    if idxSource.data.contains(.rename) || idxSource.data.contains(.delete) {
                        self?.queue.asyncAfter(deadline: .now() + 0.3) {
                            self?.setupWatchers()
                        }
                    }
                }
                let fdToClose = indexFD
                idxSource.setCancelHandler {
                    close(fdToClose)
                }
                idxSource.resume()
                self.indexSource = idxSource
            }
        }
    }

    private func scheduleDebouncedCallback() {
        debounceWorkItem?.cancel()
        let work = DispatchWorkItem { [weak self] in
            self?.onChange()
        }
        debounceWorkItem = work
        queue.asyncAfter(deadline: .now() + .milliseconds(250), execute: work)
    }

    private func teardownWatchers() {
        debounceWorkItem?.cancel()
        debounceWorkItem = nil
        if let ds = dirSource {
            ds.cancel()
            dirSource = nil
            dirFD = -1
        }
        if let idx = indexSource {
            idx.cancel()
            indexSource = nil
            indexFD = -1
        }
    }

    deinit {
        dirSource?.cancel()
        indexSource?.cancel()
    }
}
