import SwiftUI

// MARK: - Interactive 60fps 3D Camera Corridor & Frustum Visualizer

public struct Trajectory3DCanvasView: View {
    public let trajectory: LyraTrajectoryDescriptor
    public let strength: Double
    public let sceneTitle: String

    @State private var userOrbitYaw: Double = 0.28
    @State private var userOrbitPitch: Double = 0.24
    @State private var isDragging: Bool = false

    public init(trajectory: LyraTrajectoryDescriptor, strength: Double, sceneTitle: String) {
        self.trajectory = trajectory
        self.strength = strength
        self.sceneTitle = sceneTitle
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Label("3D 空间运镜实时预演 (60fps Metal Canvas)", systemImage: "view.3d")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.cyan)
                Spacer()
                Text(trajectory.englishTag)
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundColor(.white.opacity(0.85))
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.cyan.opacity(0.18))
                    .cornerRadius(4)
            }

            TimelineView(.animation(minimumInterval: 1.0 / 60.0)) { timeline in
                let now = timeline.date.timeIntervalSinceReferenceDate
                let rawCycle = (now.truncatingRemainder(dividingBy: 4.5)) / 4.5
                let t = 0.5 - 0.5 * cos(rawCycle * .pi * 2.0)
                let pose = trajectory.sampleCameraPose(t: t, strength: strength)

                ZStack(alignment: .bottomLeading) {
                    Canvas { context, size in
                        draw3DScene(
                            context: &context,
                            size: size,
                            t: t,
                            pose: pose,
                            orbitYaw: userOrbitYaw,
                            orbitPitch: userOrbitPitch
                        )
                    }
                    .drawingGroup()

                    HStack(spacing: 10) {
                        Text(
                            String(
                                format: "XYZ (%+.2f, %+.2f, %+.2f)",
                                pose.pos.x,
                                pose.pos.y,
                                pose.pos.z
                            )
                        )
                        .font(.system(size: 9.5, weight: .medium, design: .monospaced))
                        .foregroundColor(.cyan)

                        Text(String(format: "进度 %02d%%", Int(t * 100)))
                            .font(.system(size: 9.5, design: .monospaced))
                            .foregroundColor(.white.opacity(0.7))

                        Spacer()

                        Text("拖拽旋转 3D 观察角")
                            .font(.system(size: 9))
                            .foregroundColor(.white.opacity(0.45))
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.black.opacity(0.55))
                }
                .frame(height: 156)
                .background(
                    LinearGradient(
                        colors: [
                            Color(red: 0.04, green: 0.06, blue: 0.11),
                            Color(red: 0.07, green: 0.11, blue: 0.18)
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 9, style: .continuous)
                        .stroke(Color.cyan.opacity(isDragging ? 0.55 : 0.22), lineWidth: 1)
                )
                .gesture(
                    DragGesture(minimumDistance: 2)
                        .onChanged { value in
                            isDragging = true
                            let dx = Double(value.translation.width) * 0.004
                            let dy = Double(value.translation.height) * 0.003
                            userOrbitYaw = max(-0.85, min(0.85, 0.28 + dx))
                            userOrbitPitch = max(0.05, min(0.68, 0.24 + dy))
                        }
                        .onEnded { _ in
                            isDragging = false
                        }
                )
            }
        }
    }

    private func draw3DScene(
        context: inout GraphicsContext,
        size: CGSize,
        t: Double,
        pose: (pos: Vec3D, lookYaw: Double, lookPitch: Double, fovScale: Double),
        orbitYaw: Double,
        orbitPitch: Double
    ) {
        let cx = size.width * 0.5
        let cy = size.height * 0.52
        let focal = min(size.width, size.height) * 1.15

        func project(_ pt: Vec3D) -> CGPoint? {
            let cosY = cos(orbitYaw)
            let sinY = sin(orbitYaw)
            let rx = pt.x * cosY - pt.z * sinY
            let rz1 = pt.x * sinY + pt.z * cosY

            let cosP = cos(orbitPitch)
            let sinP = sin(orbitPitch)
            let ry = pt.y * cosP - rz1 * sinP
            let rz = pt.y * sinP + rz1 * cosP + 3.4

            guard rz > 0.2 else { return nil }
            let scale = focal / rz
            return CGPoint(
                x: cx + CGFloat(rx) * scale,
                y: cy - CGFloat(ry) * scale
            )
        }

        let groundY = -0.55
        for xi in -4...4 {
            let x = Double(xi) * 0.35
            if let p0 = project(Vec3D(x, groundY, -1.6)),
               let p1 = project(Vec3D(x, groundY, 1.8)) {
                var line = Path()
                line.move(to: p0)
                line.addLine(to: p1)
                context.stroke(line, with: .color(Color.cyan.opacity(xi == 0 ? 0.28 : 0.09)), lineWidth: xi == 0 ? 1.2 : 0.6)
            }
        }
        for zi in -4...5 {
            let z = Double(zi) * 0.34
            if let p0 = project(Vec3D(-1.4, groundY, z)),
               let p1 = project(Vec3D(1.4, groundY, z)) {
                var line = Path()
                line.move(to: p0)
                line.addLine(to: p1)
                context.stroke(line, with: .color(Color.cyan.opacity(0.09)), lineWidth: 0.6)
            }
        }

        let archZs: [Double] = [-1.1, -0.45, 0.2, 0.85, 1.5]
        for (idx, az) in archZs.enumerated() {
            let halfW = 0.68
            let baseH = -0.55
            let topH = 0.48
            let crownH = 0.64
            let pLeftBase = project(Vec3D(-halfW, baseH, az))
            let pLeftTop = project(Vec3D(-halfW, topH, az))
            let pCrown = project(Vec3D(0, crownH, az))
            let pRightTop = project(Vec3D(halfW, topH, az))
            let pRightBase = project(Vec3D(halfW, baseH, az))

            if let lb = pLeftBase, let lt = pLeftTop, let cr = pCrown, let rt = pRightTop, let rb = pRightBase {
                var archPath = Path()
                archPath.move(to: lb)
                archPath.addLine(to: lt)
                archPath.addQuadCurve(to: rt, control: cr)
                archPath.addLine(to: rb)
                let distHighlight = max(0.14, 0.48 - abs(pose.pos.z - az) * 0.22)
                context.stroke(
                    archPath,
                    with: .color(Color(red: 0.38, green: 0.68, blue: 0.98).opacity(distHighlight)),
                    style: StrokeStyle(lineWidth: idx == archZs.count - 1 ? 1.8 : 1.2, lineCap: .round)
                )
            }
        }

        var fullTrajPath = Path()
        var activeTrajPath = Path()
        let steps = 42
        for i in 0...steps {
            let sFrac = Double(i) / Double(steps)
            let sample = trajectory.sampleCameraPose(t: sFrac, strength: strength)
            if let pt = project(sample.pos) {
                if i == 0 {
                    fullTrajPath.move(to: pt)
                    activeTrajPath.move(to: pt)
                } else {
                    fullTrajPath.addLine(to: pt)
                    if sFrac <= t {
                        activeTrajPath.addLine(to: pt)
                    }
                }
            }
        }

        context.stroke(
            fullTrajPath,
            with: .color(Color.white.opacity(0.22)),
            style: StrokeStyle(lineWidth: 1.5, dash: [4, 3])
        )
        context.stroke(
            activeTrajPath,
            with: .linearGradient(
                Gradient(colors: [Color.cyan.opacity(0.5), Color(red: 0.22, green: 0.88, blue: 0.72)]),
                startPoint: CGPoint(x: 0, y: size.height),
                endPoint: CGPoint(x: size.width, y: 0)
            ),
            style: StrokeStyle(lineWidth: 2.6, lineCap: .round)
        )

        let camOrigin = pose.pos
        let frustumDepth = 0.42 * pose.fovScale
        let frustumW = 0.26 * pose.fovScale
        let frustumH = 0.16 * pose.fovScale

        func transformCamLocal(_ local: Vec3D) -> Vec3D {
            let cyaw = cos(pose.lookYaw)
            let syaw = sin(pose.lookYaw)
            let cpitch = cos(pose.lookPitch)
            let spitch = sin(pose.lookPitch)

            let y1 = local.y * cpitch - local.z * spitch
            let z1 = local.y * spitch + local.z * cpitch
            let x2 = local.x * cyaw + z1 * syaw
            let z2 = -local.x * syaw + z1 * cyaw
            return camOrigin.adding(Vec3D(x2, y1, z2))
        }

        let corners3D = [
            transformCamLocal(Vec3D(-frustumW,  frustumH, frustumDepth)),
            transformCamLocal(Vec3D( frustumW,  frustumH, frustumDepth)),
            transformCamLocal(Vec3D( frustumW, -frustumH, frustumDepth)),
            transformCamLocal(Vec3D(-frustumW, -frustumH, frustumDepth))
        ]

        if let pCam = project(camOrigin) {
            let projectedCorners = corners3D.compactMap { project($0) }
            if projectedCorners.count == 4 {
                var plane = Path()
                plane.move(to: projectedCorners[0])
                plane.addLine(to: projectedCorners[1])
                plane.addLine(to: projectedCorners[2])
                plane.addLine(to: projectedCorners[3])
                plane.closeSubpath()
                context.fill(plane, with: .color(Color.cyan.opacity(0.18)))
                context.stroke(plane, with: .color(Color.cyan.opacity(0.85)), lineWidth: 1.4)

                for corner in projectedCorners {
                    var edge = Path()
                    edge.move(to: pCam)
                    edge.addLine(to: corner)
                    context.stroke(edge, with: .color(Color.cyan.opacity(0.65)), lineWidth: 1.1)
                }
            }

            let apexGlow = CGRect(x: pCam.x - 6, y: pCam.y - 6, width: 12, height: 12)
            context.fill(Path(ellipseIn: apexGlow), with: .color(Color.cyan.opacity(0.35)))
            let apexDot = CGRect(x: pCam.x - 3, y: pCam.y - 3, width: 6, height: 6)
            context.fill(Path(ellipseIn: apexDot), with: .color(Color.white))
        }
    }
}
