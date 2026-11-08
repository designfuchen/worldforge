import SwiftUI
import AppKit

// MARK: - AppDelegate for Native Pro Window Styling & Foreground Activation

public final class WorldForgeAppDelegate: NSObject, NSApplicationDelegate {
    public func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.appearance = NSAppearance(named: .darkAqua)

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            for window in NSApplication.shared.windows {
                window.titlebarAppearsTransparent = true
                window.backgroundColor = NSColor(calibratedRed: 0.04, green: 0.05, blue: 0.08, alpha: 1.0)
                window.minSize = NSSize(width: 1180, height: 740)
            }
            NSApp.activate(ignoringOtherApps: true)
        }
    }

    public func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        false
    }
}

// MARK: - WorldForgeApp Entry Point (@main)

@main
public struct WorldForgeApp: App {
    @NSApplicationDelegateAdaptor(WorldForgeAppDelegate.self) private var appDelegate
    @StateObject private var coordinator = StudioCoordinator()

    public init() {}

    public var body: some Scene {
        WindowGroup("WorldForge 世界工坊") {
            MainStudioWindow(coordinator: coordinator)
                .frame(minWidth: 1220, minHeight: 760)
                .onAppear {
                    coordinator.start()
                }
        }
        .windowStyle(.hiddenTitleBar)
        .defaultSize(width: 1520, height: 940)
        .commands {
            CommandMenu("工作台导航") {
                ForEach(StudioTab.allCases) { tab in
                    Button(tab.title) {
                        coordinator.workspace.activeTab = tab
                    }
                    .keyboardShortcut(KeyEquivalent(tab.shortcutKey), modifiers: [.command])
                }
                Divider()
                Button("立即生成当前任务") {
                    Task { await coordinator.submitActiveWorkspaceTask() }
                }
                .keyboardShortcut(.return, modifiers: [.command])

                Button("刷新远端状态与作品库") {
                    Task { await coordinator.refreshAll() }
                }
                .keyboardShortcut("r", modifiers: [.command])

                Button("上传本地 2K 场景图片…") {
                    coordinator.promptAndUploadLocalImage()
                }
                .keyboardShortcut("o", modifiers: [.command])
            }
        }

        // macOS Top System MenuBarExtra (Live Colab GPU VRAM & CU Burn Rate Monitor)
        MenuBarExtra {
            VStack(alignment: .leading, spacing: 8) {
                Text("WorldForge 世界工坊 · 算力监控")
                    .font(.headline)

                Divider()

                Text("GPU 节点: \(coordinator.telemetry.gpuDisplayName)")
                Text("算力负载: \(coordinator.telemetry.gpuUtilPercent)%  |  速率: \(coordinator.telemetry.cuBurnRateText)")
                Text("显存占用: \(coordinator.telemetry.vramSummaryText)")
                Text("主机内存: \(coordinator.telemetry.hostRamSummaryText)")
                Text("看门狗: \(coordinator.telemetry.idleCountdownText)")

                Divider()

                Button("🖥 唤醒 WorldForge 主工作台") {
                    NSApp.activate(ignoringOtherApps: true)
                    if let win = NSApp.windows.first {
                        win.makeKeyAndOrderFront(nil)
                    }
                }

                Button("╱ 打开 @NVIDIAAI 3DGS 斜切同屏对比") {
                    coordinator.workspace.activeTab = .abCompare
                    NSApp.activate(ignoringOtherApps: true)
                }

                Button("📂 打开 ~/Movies/WorldForge 作品库目录") {
                    NSWorkspace.shared.open(GalleryItem.galleryRootURL)
                }

                Divider()

                Button("⚡ 一键启动并连接 Colab GPU") {
                    Task {
                        _ = try? await ForgeClient.shared.startColabSession(
                            name: coordinator.telemetry.sessionName,
                            gpu: coordinator.telemetry.selectedGPUType,
                            connect: true
                        )
                        await coordinator.refreshAll()
                    }
                }

                Button("🛑 立即释放 Colab 会话 (节省算力单元)") {
                    Task {
                        _ = try? await ForgeClient.shared.stopColabSession(name: coordinator.telemetry.sessionName)
                        await coordinator.refreshAll()
                    }
                }

                Divider()

                Button("退出 WorldForge") {
                    NSApplication.shared.terminate(nil)
                }
                .keyboardShortcut("q")
            }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: coordinator.telemetry.isRemoteConnected ? "bolt.horizontal.circle.fill" : "cube.transparent.fill")
                Text(coordinator.telemetry.isRemoteConnected ? "\(coordinator.telemetry.gpuUtilPercent)% · \(coordinator.telemetry.cuBurnRateText)" : "WF Studio")
                    .font(.system(size: 11, weight: .semibold, design: .monospaced))
            }
        }
    }
}
