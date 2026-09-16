import SwiftUI
import AppKit

// MARK: - 데이터 모델 (collect.py 출력과 1:1)

struct WindowInfo: Codable, Identifiable {
    var id: String { key }
    let key: String
    let label: String
    let used_pct: Double?
    let resets_at: Double?
    let detail: String?
}

struct Billing: Codable {
    let cycle: String?
    let next_date: String?
    let label: String?
}

struct ProviderInfo: Codable, Identifiable {
    let id: String
    let name: String
    let plan: String?
    let account: String?
    let status: String
    let error: String?
    let windows: [WindowInfo]
    let billing: Billing?
    let stale_age: Double?
}

struct WeatherInfo: Codable {
    let temp_c: String?
    let code: String?
    let desc: String?
    let loc: String?
}

struct NewsItem: Codable, Identifiable {
    var id: String { url.isEmpty ? title : url }
    let title: String
    let source: String
    let url: String
    let ts: Double?
    let breaking: Bool?
}

struct CollectorOutput: Codable {
    let updated_at: String
    let updated_epoch: Double
    let providers: [ProviderInfo]
    let weather: WeatherInfo?
    let news: [NewsItem]?
    let page_seconds: Double?
}

// MARK: - 수집기 실행

enum Collector {
    /// /usr/bin/python3는 Xcode shim — 라이선스 미동의 시 실행이 막히므로
    /// CLT 실제 바이너리와 brew 설치본을 우선 탐색한다.
    static func pythonPath() -> String {
        for p in ["/Library/Developer/CommandLineTools/usr/bin/python3",
                  "/opt/homebrew/bin/python3",
                  "/usr/local/bin/python3",
                  "/usr/bin/python3"]
        where FileManager.default.isExecutableFile(atPath: p) {
            return p
        }
        return "/usr/bin/python3"
    }

    static func run(script: URL) throws -> CollectorOutput {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: pythonPath())
        proc.arguments = [script.path]
        proc.environment = ProcessInfo.processInfo.environment
        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = FileHandle.nullDevice
        try proc.run()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        proc.waitUntilExit()
        guard proc.terminationStatus == 0 else {
            throw NSError(domain: "collector", code: Int(proc.terminationStatus))
        }
        return try JSONDecoder().decode(CollectorOutput.self, from: data)
    }
}

// MARK: - 뷰모델

@MainActor
final class UsageModel: ObservableObject {
    @Published var providers: [ProviderInfo] = []
    @Published var weather: WeatherInfo?
    @Published var news: [NewsItem] = []
    @Published var pageSeconds: Double = 8
    @Published var updatedAt: Date?
    @Published var refreshing = false
    @Published var lastError: String?
    @Published var contentHeight: CGFloat = 0

    let scriptURL: URL
    private var timer: Timer?
    var onResize: (() -> Void)?

    init(scriptURL: URL) { self.scriptURL = scriptURL }

    func start() {
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in
            self?.refresh()
        }
    }

    func refresh() {
        guard !refreshing else { return }
        refreshing = true
        let url = scriptURL
        Task.detached(priority: .utility) { [weak self] in
            let result: Result<CollectorOutput, Error>
            do { result = .success(try Collector.run(script: url)) }
            catch { result = .failure(error) }
            await MainActor.run {
                guard let self else { return }
                self.refreshing = false
                switch result {
                case .success(let out):
                    self.providers = out.providers
                    self.weather = out.weather
                    self.news = out.news ?? []
                    if let ps = out.page_seconds, ps >= 3 { self.pageSeconds = ps }
                    self.updatedAt = Date(timeIntervalSince1970: out.updated_epoch)
                    self.lastError = nil
                case .failure(let err):
                    self.lastError = err.localizedDescription
                }
                self.onResize?()
            }
        }
    }
}

// MARK: - 뷰

/// 콘텐츠 실측 높이 — 패널 크기와 스크롤 필요 여부를 실제 값으로 결정
struct ContentHeightKey: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = nextValue() }
}

/// 번들 Resources에 포함된 프로바이더 아이콘 (icons8 fluency, <id>.png)
let iconCache: [String: NSImage] = {
    var m: [String: NSImage] = [:]
    for id in ["claude", "codex", "grok", "devin", "cursor", "zai", "minimax", "openrouter", "google"] {
        if let url = Bundle.main.url(forResource: id, withExtension: "png"),
           let img = NSImage(contentsOf: url) {
            m[id] = img
        }
    }
    return m
}()

func pctColor(_ p: Double) -> Color {
    // 다크 배경에서 형광 느낌을 줄인 톤다운 팔레트
    if p < 60 { return Color(red: 0.20, green: 0.68, blue: 0.32) }
    if p < 85 { return Color(red: 0.88, green: 0.55, blue: 0.14) }
    return Color(red: 0.85, green: 0.26, blue: 0.23)
}

func resetText(_ epoch: Double?) -> String {
    guard let t = epoch else { return "" }
    let d = t - Date().timeIntervalSince1970
    if d <= 0 { return "곧 리셋" }
    if d < 3600 { return "\(Int(d / 60))분 후" }
    if d < 86400 { return "\(Int(d / 3600))시간 \(Int(d.truncatingRemainder(dividingBy: 3600)) / 60)분 후" }
    return "\(Int(d / 86400))일 \(Int(d.truncatingRemainder(dividingBy: 86400)) / 3600)시간 후"
}

/// wttr.in weatherCode → SF Symbol
func weatherSymbol(_ code: String?) -> String {
    switch code {
    case "113": return "sun.max.fill"
    case "116": return "cloud.sun.fill"
    case "119", "122": return "cloud.fill"
    case "143", "248", "260": return "cloud.fog.fill"
    case "176", "263", "266", "281", "284", "293", "296", "299",
         "302", "305", "308", "311", "314", "353", "356", "359": return "cloud.rain.fill"
    case "179", "182", "227", "230", "323", "326", "329", "332",
         "335", "338", "350", "368", "371", "374", "377": return "cloud.snow.fill"
    case "200", "386", "389", "392", "395": return "cloud.bolt.fill"
    default: return "cloud.fill"
    }
}

func newsAge(_ ts: Double?) -> String {
    guard let t = ts else { return "" }
    let d = Date().timeIntervalSince1970 - t
    if d < 0 { return "방금" }
    if d < 60 { return "방금" }
    if d < 3600 { return "\(Int(d / 60))분 전" }
    if d < 86400 { return "\(Int(d / 3600))시간 전" }
    return "\(Int(d / 86400))일 전"
}

/// 한 줄짜리 콤팩트 사용량 행: [라벨 | 막대 | % | 리셋]
struct WindowRow: View {
    let w: WindowInfo
    var body: some View {
        if let pct = w.used_pct {
            HStack(spacing: 5) {
                Text(w.label)
                    .font(.system(size: 9.5, weight: .semibold))
                    .frame(width: 72, alignment: .leading)
                    .lineLimit(1)
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule().fill(Color.white.opacity(0.12))
                        Capsule().fill(pctColor(pct))
                            .frame(width: max(3, geo.size.width * min(pct, 100) / 100))
                    }
                }
                .frame(height: 4)
                Text("\(Int(pct))%")
                    .font(.system(size: 9.5, weight: .semibold, design: .monospaced))
                    .foregroundStyle(pctColor(pct))
                    .frame(width: 27, alignment: .trailing)
                Text(resetText(w.resets_at))
                    .font(.system(size: 8, weight: .medium))
                    .foregroundStyle(.secondary)
                    .frame(width: 56, alignment: .trailing)
                    .lineLimit(1)
            }
            .frame(height: 12)
        } else {
            HStack(alignment: .firstTextBaseline) {
                Text(w.label).font(.system(size: 9.5, weight: .semibold))
                Spacer()
                if let d = w.detail {
                    Text(d).font(.system(size: 8.5, weight: .medium)).foregroundStyle(.secondary)
                }
            }
            .frame(height: 11)
        }
    }
}

struct ProviderCard: View {
    let p: ProviderInfo
    var body: some View {
        VStack(alignment: .leading, spacing: 1.5) {
            HStack(spacing: 5) {
                if let img = iconCache[p.id] {
                    Image(nsImage: img)
                        .resizable()
                        .frame(width: 13, height: 13)
                        .opacity(p.status == "ok" ? 1 : 0.45)
                }
                Text(p.name).font(.system(size: 11, weight: .semibold))
                if let plan = p.plan, !plan.isEmpty {
                    Text(plan)
                        .font(.system(size: 8, weight: .medium))
                        .padding(.horizontal, 4).padding(.vertical, 1)
                        .background(Capsule().fill(Color.white.opacity(0.12)))
                }
                if let age = p.stale_age {
                    Text(age < 3600 ? "\(max(1, Int(age / 60)))분 전" : "\(Int(age / 3600))시간 전")
                        .font(.system(size: 8, weight: .medium))
                        .foregroundStyle(.orange)
                        .padding(.horizontal, 4).padding(.vertical, 1)
                        .background(Capsule().fill(Color.orange.opacity(0.15)))
                }
                if let b = p.billing, let d = b.next_date {
                    Text("· \(d) 결제")
                        .font(.system(size: 8, weight: .medium)).foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                Spacer()
                if p.status != "ok" {
                    Text(p.error ?? "조회 불가")
                        .font(.system(size: 8.5, weight: .medium)).foregroundStyle(.secondary)
                        .lineLimit(1).truncationMode(.middle)
                } else if let acc = p.account, !acc.isEmpty {
                    Text(acc).font(.system(size: 8, weight: .medium)).foregroundStyle(.secondary)
                        .lineLimit(1).truncationMode(.middle)
                }
            }
            if p.status != "ok" {
                // 에러 카드는 헤더 한 줄로 표시
            } else {
                ForEach(p.windows) { WindowRow(w: $0) }
                if let b = p.billing, b.next_date == nil, let label = b.label {
                    Text(label).font(.system(size: 9, weight: .medium)).foregroundStyle(.secondary)
                }
            }
        }
        .padding(.horizontal, 7).padding(.vertical, 4)
        .background(RoundedRectangle(cornerRadius: 8).fill(Color.white.opacity(0.06)))
    }
}

struct NewsRow: View {
    let item: NewsItem
    var isBreaking: Bool { item.breaking == true }
    var body: some View {
        HStack(spacing: 6) {
            if isBreaking {
                Text("속보")
                    .font(.system(size: 8, weight: .bold))
                    .foregroundStyle(Color(red: 0.85, green: 0.26, blue: 0.23))
                    .padding(.horizontal, 4).padding(.vertical, 1)
                    .background(Capsule().fill(Color(red: 0.85, green: 0.26, blue: 0.23).opacity(0.15)))
                    .frame(width: 46, alignment: .leading)
            } else {
                Text(item.source)
                    .font(.system(size: 8, weight: .medium))
                    .foregroundStyle(.secondary)
                    .frame(width: 46, alignment: .leading)
                    .lineLimit(1)
            }
            Text(item.title)
                .font(.system(size: 9.5, weight: isBreaking ? .semibold : .medium))
                .lineLimit(1).truncationMode(.tail)
            Spacer(minLength: 4)
            Text(newsAge(item.ts))
                .font(.system(size: 8, weight: .medium))
                .foregroundStyle(.secondary)
        }
        .frame(height: 17)
        .contentShape(Rectangle())
        .onTapGesture {
            if !item.url.isEmpty, let u = URL(string: item.url) {
                NSWorkspace.shared.open(u)
            }
        }
    }
}

struct NewsSection: View {
    let items: [NewsItem]
    var pageSeconds: Double = 8
    private let perPage = 6

    var body: some View {
        let breaking = items.first(where: { $0.breaking == true })
        let rest = items.filter { $0.breaking != true }
        let pages = max(1, (rest.count + perPage - 1) / perPage)

        // TimelineView로 페이지를 시간 기반 순수 계산 — @State/Timer 불필요
        TimelineView(.periodic(from: .now, by: 1)) { tl in
            let t = tl.date.timeIntervalSinceReferenceDate
            let page = pages > 1 ? Int(t / max(pageSeconds, 3)) % pages : 0
            let pageItems = Array(rest.dropFirst(page * perPage).prefix(perPage))

            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 5) {
                    Image(systemName: "newspaper.fill")
                        .font(.system(size: 9))
                        .foregroundStyle(.secondary)
                    Text("AI 뉴스").font(.system(size: 10, weight: .semibold))
                    Spacer()
                    if pages > 1 {
                        HStack(spacing: 3) {
                            ForEach(0..<pages, id: \.self) { i in
                                Circle()
                                    .fill(i == page ? Color.white.opacity(0.9)
                                                    : Color.white.opacity(0.25))
                                    .frame(width: 4, height: 4)
                            }
                        }
                    }
                }
                .padding(.bottom, 2)
                if let b = breaking { NewsRow(item: b) }
                ForEach(pageItems) { NewsRow(item: $0) }
            }
        }
        .padding(.horizontal, 7).padding(.vertical, 5)
        .background(RoundedRectangle(cornerRadius: 8).fill(Color.white.opacity(0.06)))
    }
}

// MARK: - 신경망 맵 (자비스 스타일 회전 구체 + 시간/날씨 하늘)

struct NeuralMapView: View {
    /// 3D 구 표면 노드 — theta: 위도(-π/2~π/2), phi: 경도(0~2π), r: 반경비율
    struct NNode {
        let theta: CGFloat, phi: CGFloat, r: CGFloat
        let region: Int
        let size: CGFloat
        let phase: Double
    }

    /// 시냅스 — 3D 인덱스 쌍 + 곡률 오프셋
    struct NEdge {
        let a: Int, b: Int
        let off: CGFloat
    }

    enum SkyKind { case clear, cloudy, fog, rain, snow, thunder }

    let weatherCode: String?
    init(weatherCode: String? = nil) { self.weatherCode = weatherCode }

    static var isDay: Bool { (6..<19).contains(Calendar.current.component(.hour, from: Date())) }

    static func skyKind(_ code: String?) -> SkyKind {
        switch code {
        case "113", "116": return .clear
        case "119", "122": return .cloudy
        case "143", "248", "260": return .fog
        case "176", "263", "266", "281", "284", "293", "296", "299",
             "302", "305", "308", "311", "314", "353", "356", "359": return .rain
        case "179", "182", "227", "230", "323", "326", "329", "332",
             "335", "338", "350", "368", "371", "374", "377": return .snow
        case "200", "386", "389", "392", "395": return .thunder
        default: return .cloudy
        }
    }

    /// 카드 배경 하늘 그라데이션 — 시간대×날씨
    static func skyColors(_ code: String?) -> [Color] {
        switch (isDay, skyKind(code)) {
        case (true, .clear):    return [Color(red: 0.30, green: 0.58, blue: 0.88), Color(red: 0.55, green: 0.78, blue: 0.94)]
        case (true, .cloudy):   return [Color(red: 0.40, green: 0.50, blue: 0.61), Color(red: 0.58, green: 0.66, blue: 0.74)]
        case (true, .fog):      return [Color(red: 0.46, green: 0.51, blue: 0.57), Color(red: 0.61, green: 0.65, blue: 0.70)]
        case (true, .rain), (true, .thunder):
            return [Color(red: 0.20, green: 0.26, blue: 0.34), Color(red: 0.35, green: 0.42, blue: 0.51)]
        case (true, .snow):     return [Color(red: 0.42, green: 0.49, blue: 0.59), Color(red: 0.62, green: 0.68, blue: 0.76)]
        case (false, .clear):   return [Color(red: 0.02, green: 0.04, blue: 0.10), Color(red: 0.05, green: 0.09, blue: 0.18)]
        case (false, .cloudy):  return [Color(red: 0.05, green: 0.07, blue: 0.13), Color(red: 0.09, green: 0.12, blue: 0.20)]
        case (false, .fog):     return [Color(red: 0.10, green: 0.12, blue: 0.16), Color(red: 0.17, green: 0.19, blue: 0.24)]
        case (false, .rain), (false, .thunder):
            return [Color(red: 0.05, green: 0.07, blue: 0.12), Color(red: 0.10, green: 0.13, blue: 0.20)]
        case (false, .snow):    return [Color(red: 0.07, green: 0.09, blue: 0.15), Color(red: 0.14, green: 0.17, blue: 0.24)]
        }
    }

    /// 발광 팔레트 — 밤: 밝은 네온 / 낮: 진한 보석색 (밝은 하늘 대비)
    static let nightColors: [Color] = [
        Color(red: 0.62, green: 0.55, blue: 1.00), Color(red: 0.35, green: 0.85, blue: 1.00),
        Color(red: 0.45, green: 0.65, blue: 1.00), Color(red: 1.00, green: 0.60, blue: 0.55),
        Color(red: 1.00, green: 0.80, blue: 0.40), Color(red: 0.45, green: 0.95, blue: 0.65),
    ]
    static let dayColors: [Color] = [
        Color(red: 0.45, green: 0.22, blue: 0.85), Color(red: 0.03, green: 0.45, blue: 0.82),
        Color(red: 0.12, green: 0.28, blue: 0.85), Color(red: 0.82, green: 0.28, blue: 0.22),
        Color(red: 0.80, green: 0.50, blue: 0.05), Color(red: 0.12, green: 0.55, blue: 0.30),
    ]

    /// 결정론적 PRNG — 매 실행 동일한 배치
    static func seeded(_ seed: UInt64 = 0x243F6A8885A308D3) -> () -> Double {
        var s = seed
        return {
            s &+= 0x9E3779B97F4A7C15
            var z = s
            z = (z ^ (z >> 30)) &* 0xBF58476D1CE4E5B9
            z = (z ^ (z >> 27)) &* 0x94D049BB133111EB
            z = z ^ (z >> 31)
            return Double(z % 1_048_576) / 1_048_576
        }
    }

    /// 윈도우 해시 — 주기 효과(유성·번개)의 결정론적 발생
    static func whash(_ w: Double) -> UInt64 {
        var h = UInt64(w) &* 0x9E3779B97F4A7C15
        h ^= h >> 13; h &*= 0xBF58476D1CE4E5B9; h ^= h >> 16
        return h
    }

    static let nodes: [NNode] = {
        let rnd = seeded()
        var arr: [NNode] = []
        // 구 표면 — 피보나치 구 배치로 균일 분포 (72개)
        let surfN = 72
        for i in 0..<surfN {
            let y = 1 - (CGFloat(i) / CGFloat(surfN - 1)) * 2
            let th = asin(y)
            let ph = CGFloat(i) * 2.399963 + (rnd() - 0.5) * 0.15
            let region = Int((ph / (2 * .pi)).truncatingRemainder(dividingBy: 1) * 6 + 6) % 6
            arr.append(NNode(theta: th + (rnd() - 0.5) * 0.08, phi: ph, r: 1.0,
                             region: region, size: 1.2 + rnd() * 1.0, phase: rnd() * 6.28))
        }
        // 내부 채움 — 구 내부 랜덤 (28개)
        for _ in 0..<28 {
            let th = (rnd() - 0.5) * .pi
            let ph = rnd() * 2 * .pi
            let region = Int((ph / (2 * .pi)).truncatingRemainder(dividingBy: 1) * 6 + 6) % 6
            arr.append(NNode(theta: th, phi: ph, r: 0.25 + rnd() * 0.6,
                             region: region, size: 1.0 + rnd() * 1.0, phase: rnd() * 6.28))
        }
        // 허브 노드 — 표면의 밝은 중심점
        for _ in 0..<6 {
            let th = (rnd() - 0.5) * .pi * 0.8
            let ph = rnd() * 2 * .pi
            let region = Int((ph / (2 * .pi)).truncatingRemainder(dividingBy: 1) * 6 + 6) % 6
            arr.append(NNode(theta: th, phi: ph, r: 1.0,
                             region: region, size: 2.3 + rnd() * 0.9, phase: rnd() * 6.28))
        }
        return arr
    }()

    /// 3D 좌표 (회전 없는 기준 좌표)
    static func xyz(_ n: NNode) -> (CGFloat, CGFloat, CGFloat) {
        let c = cos(n.theta) * n.r
        return (c * sin(n.phi), sin(n.theta) * n.r, c * cos(n.phi))
    }

    /// 메시 엣지 — 3D 거리 knn-4 (회전 불변)
    static let edges: [NEdge] = {
        let rnd = seeded(0x517CC1B727220A95)
        let pts = nodes.map(xyz)
        var e: [(Int, Int)] = []
        for i in pts.indices {
            var near: [(Int, CGFloat)] = []
            for j in pts.indices where j != i {
                let dx = pts[i].0 - pts[j].0, dy = pts[i].1 - pts[j].1, dz = pts[i].2 - pts[j].2
                near.append((j, dx * dx + dy * dy + dz * dz))
            }
            near.sort { $0.1 < $1.1 }
            for (j, _) in near.prefix(4) {
                if !e.contains(where: { $0.0 == j && $0.1 == i }) { e.append((i, j)) }
            }
        }
        return e.map { NEdge(a: $0.0, b: $0.1, off: (rnd() - 0.5) * 0.5) }
    }()

    /// 3D → 2D 투영 (y축 자전 + 약한 원근). 반환: 화면점, 깊이 z(-1~1)
    static func project(_ n: NNode, _ rot: CGFloat, _ W: CGFloat, _ H: CGFloat) -> (CGPoint, CGFloat) {
        let c = cos(n.theta) * n.r
        let p = n.phi + rot
        let x3 = c * sin(p), y3 = sin(n.theta) * n.r, z3 = c * cos(p)
        let R = min(W, H) * 0.40
        let cx = W * 0.5, cy = H * 0.40
        let persp = 1.0 / (1.0 + (1 - z3) * 0.12)
        return (CGPoint(x: cx + x3 * R * persp, y: cy - y3 * R * persp), z3)
    }

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 24)) { tl in
            Canvas { ctx, size in
                let t = tl.date.timeIntervalSinceReferenceDate
                let W = size.width, H = size.height
                let rot = CGFloat(t * 0.35)
                let day = Self.isDay
                let kind = Self.skyKind(weatherCode)
                let cyan = day ? Color(red: 0.10, green: 0.35, blue: 0.75)
                             : Color(red: 0.45, green: 0.85, blue: 1.0)
                let palette = day ? Self.dayColors : Self.nightColors
                let R = min(W, H) * 0.40
                let cx = W * 0.5, cy = H * 0.40
                let horizon: CGFloat = 0.84

                // === 밤하늘 별 (맑음/흐림/눈 밤) ===
                if !day && (kind == .clear || kind == .cloudy || kind == .snow) {
                    let srnd = Self.seeded(0xB5297A4D)
                    for _ in 0..<30 {
                        let sx = srnd() * W, sy = srnd() * horizon * H * 0.9
                        let tw = 0.5 + 0.5 * sin(t * (1.0 + srnd() * 1.5) + srnd() * 6.28)
                        let r = 0.5 + srnd() * 0.9
                        ctx.fill(Path(ellipseIn: CGRect(x: sx - r, y: sy - r, width: r * 2, height: r * 2)),
                                 with: .color(.white.opacity(0.4 * tw)))
                    }
                }

                // === 태양 (낮 + 맑음) — 우측 상단, 광선 회전 ===
                if day && kind == .clear {
                    let sun = CGPoint(x: W * 0.88, y: H * 0.15)
                    ctx.fill(Path(ellipseIn: CGRect(x: sun.x - 17, y: sun.y - 17, width: 34, height: 34)),
                             with: .radialGradient(
                                Gradient(colors: [Color(red: 1, green: 0.85, blue: 0.3).opacity(0.95),
                                                  Color(red: 1, green: 0.85, blue: 0.3).opacity(0)]),
                                center: sun, startRadius: 0, endRadius: 17))
                    ctx.fill(Path(ellipseIn: CGRect(x: sun.x - 5.5, y: sun.y - 5.5, width: 11, height: 11)),
                             with: .color(Color(red: 1, green: 0.93, blue: 0.55)))
                    var rays = Path()
                    for i in 0..<8 {
                        let a = t * 0.15 + Double(i) * .pi / 4
                        rays.move(to: CGPoint(x: sun.x + cos(a) * 7.5, y: sun.y + sin(a) * 7.5))
                        rays.addLine(to: CGPoint(x: sun.x + cos(a) * 11, y: sun.y + sin(a) * 11))
                    }
                    ctx.stroke(rays, with: .color(Color(red: 1, green: 0.9, blue: 0.4).opacity(0.8)), lineWidth: 1)
                }

                // === 구름 — 낮: 흰 구름 / 밤: 옅은 구름 ===
                let cloudN = kind == .fog ? 0 : (day ? (kind == .clear ? 1 : 4) : (kind == .cloudy ? 3 : 0))
                if cloudN > 0 {
                    let crnd = Self.seeded(0xC10D5)
                    for _ in 0..<cloudN {
                        let cw = 46 + CGFloat(crnd()) * 42
                        let drift = (t * (0.005 + crnd() * 0.008) + crnd()).truncatingRemainder(dividingBy: 1.3)
                        let cx0 = (drift - 0.15) * W
                        let cy0 = H * (0.07 + CGFloat(crnd()) * 0.20)
                        let op = day ? 0.55 : 0.14
                        let cc = day ? Color.white : Color(red: 0.55, green: 0.65, blue: 0.78)
                        for (ox, oy, s) in [(0.0, 0.0, 1.0), (-0.36, 0.05, 0.68), (0.34, 0.06, 0.74)] {
                            ctx.fill(Path(ellipseIn: CGRect(x: cx0 + ox * cw - cw * s / 2,
                                                          y: cy0 + oy * cw - cw * s * 0.20,
                                                          width: cw * s, height: cw * s * 0.40)),
                                     with: .color(cc.opacity(op * 0.55)))
                        }
                    }
                }

                // === 안개층 (안개 날씨) ===
                if kind == .fog {
                    for i in 0..<3 {
                        let y = H * (0.45 + 0.17 * CGFloat(i))
                        let drift = sin(t * 0.12 + Double(i) * 2.1) * 22
                        ctx.fill(Path(ellipseIn: CGRect(x: -40 + drift, y: y - 9, width: W + 80, height: 18)),
                                 with: .linearGradient(
                                    Gradient(colors: [Color.white.opacity(0), Color.white.opacity(0.14), Color.white.opacity(0)]),
                                    startPoint: CGPoint(x: 0, y: y - 9), endPoint: CGPoint(x: 0, y: y + 9)))
                    }
                }

                // === 유성 — 밤, 가끔, 구체 좌우 하늘을 가로지름 ===
                if !day && (kind == .clear || kind == .cloudy || kind == .snow) {
                    let win = 9.0, phase = t.truncatingRemainder(dividingBy: win)
                    let h = Self.whash(t / win)
                    if h % 100 < 65 && phase < 1.1 {
                        let mrnd = Self.seeded(h)
                        let dir: CGFloat = mrnd() < 0.5 ? 1 : -1
                        let side = mrnd() < 0.5 ? (0.05 + mrnd() * 0.18) : (0.77 + mrnd() * 0.18)
                        let sx = side * W
                        let sy = (0.03 + mrnd() * 0.20) * H
                        let speed = 0.30 + mrnd() * 0.25
                        let px = sx + dir * phase * speed * W
                        let py = sy + phase * speed * W * 0.45
                        var streak = Path()
                        for k in 0...8 {
                            let f = phase - CGFloat(k) * 0.035
                            guard f > 0 else { break }
                            let gx = sx + dir * f * speed * W
                            let gy = sy + f * speed * W * 0.45
                            k == 0 ? streak.move(to: CGPoint(x: gx, y: gy))
                                   : streak.addLine(to: CGPoint(x: gx, y: gy))
                        }
                        ctx.stroke(streak, with: .linearGradient(
                            Gradient(colors: [.white.opacity(0.85 * (1 - phase / 1.1)), .white.opacity(0)]),
                            startPoint: CGPoint(x: px, y: py),
                            endPoint: CGPoint(x: px - dir * 34, y: py - 15)), lineWidth: 1.1)
                        ctx.fill(Path(ellipseIn: CGRect(x: px - 4, y: py - 4, width: 8, height: 8)),
                                 with: .radialGradient(
                                    Gradient(colors: [.white.opacity(0.85), .white.opacity(0)]),
                                    center: CGPoint(x: px, y: py), startRadius: 0, endRadius: 4))
                    }
                }

                // === 하단 홀로그램 바닥 ===
                var grid = Path()
                for i in 0..<4 {
                    let gy = horizon + 0.04 * CGFloat(i) + 0.011 * CGFloat(i * i)
                    grid.move(to: CGPoint(x: 0.04 * W, y: gy * H))
                    grid.addLine(to: CGPoint(x: 0.96 * W, y: gy * H))
                }
                ctx.stroke(grid, with: .color(cyan.opacity(day ? 0.22 : 0.16)), lineWidth: 0.5)
                var radials = Path()
                for k in -5...5 {
                    radials.move(to: CGPoint(x: (0.5 + CGFloat(k) * 0.03) * W, y: horizon * H))
                    radials.addLine(to: CGPoint(x: (0.5 + CGFloat(k) * 0.10) * W, y: 0.99 * H))
                }
                ctx.stroke(radials, with: .color(cyan.opacity(day ? 0.18 : 0.12)), lineWidth: 0.5)
                let gl = CGPoint(x: cx, y: horizon * H)
                ctx.fill(Path(ellipseIn: CGRect(x: gl.x - 55, y: gl.y - 6, width: 110, height: 12)),
                         with: .radialGradient(
                            Gradient(colors: [cyan.opacity(day ? 0.30 : 0.35), cyan.opacity(0)]),
                            center: gl, startRadius: 0, endRadius: 55))

                // === 노드 투영 ===
                var proj: [(CGPoint, CGFloat)] = []
                proj.reserveCapacity(Self.nodes.count)
                for n in Self.nodes { proj.append(Self.project(n, rot, W, H)) }

                // === 구 반사 — 바닥면 아래로 미러 ===
                var rep = Path()
                for e in Self.edges {
                    let (pa, _) = proj[e.a], (pb, _) = proj[e.b]
                    rep.move(to: CGPoint(x: pa.x, y: horizon * H + (horizon * H - pa.y) * 0.22))
                    rep.addLine(to: CGPoint(x: pb.x, y: horizon * H + (horizon * H - pb.y) * 0.22))
                }
                ctx.stroke(rep, with: .color(cyan.opacity(day ? 0.10 : 0.06)), lineWidth: 0.5)

                // === 궤도 링 — 기울어진 타원 2개 + 위를 도는 밝은 점 ===
                for (oi, tilt) in [(-0.18, 0.16), (0.22, -0.10)].enumerated() {
                    var orb = Path()
                    let steps = 60
                    for i in 0...steps {
                        let a = CGFloat(i) / CGFloat(steps) * 2 * .pi
                        let ox = cos(a) * R * 1.18
                        let oy = sin(a) * R * 0.30
                        let rx = ox * cos(tilt.0) - oy * sin(tilt.0)
                        let ry = ox * sin(tilt.0) + oy * cos(tilt.0)
                        let pt = CGPoint(x: cx + rx, y: cy + ry * 0.85)
                        i == 0 ? orb.move(to: pt) : orb.addLine(to: pt)
                    }
                    ctx.stroke(orb, with: .color(cyan.opacity(day ? 0.30 : 0.20)), lineWidth: 0.5)
                    let a = t * (oi == 0 ? 0.9 : -0.7) + Double(oi) * 2.4
                    let ox = cos(a) * R * 1.18, oy = sin(a) * R * 0.30
                    let sp = CGPoint(x: cx + ox * cos(tilt.0) - oy * sin(tilt.0),
                                     y: cy + (ox * sin(tilt.0) + oy * cos(tilt.0)) * 0.85)
                    ctx.fill(Path(ellipseIn: CGRect(x: sp.x - 4, y: sp.y - 4, width: 8, height: 8)),
                             with: .radialGradient(
                                Gradient(colors: [cyan.opacity(0.8), cyan.opacity(0)]),
                                center: sp, startRadius: 0, endRadius: 4))
                }

                // === 위도선 — 정적 타원 ===
                for lat in [-0.6, -0.3, 0.0, 0.3, 0.6] {
                    let yy = cy - CGFloat(lat) * R
                    let rr = R * sqrt(1 - lat * lat)
                    let e = CGRect(x: cx - rr, y: yy - rr * 0.28, width: rr * 2, height: rr * 0.56)
                    ctx.stroke(Path(ellipseIn: e),
                               with: .color(cyan.opacity(lat == 0 ? (day ? 0.22 : 0.16) : (day ? 0.15 : 0.10))),
                               lineWidth: 0.5)
                }

                // === 경도선 — 자전하는 파라메트릭 곡선 ===
                for li in 0..<4 {
                    let phi0 = CGFloat(li) * .pi / 2 + rot
                    var mp = Path()
                    var started = false
                    for i in 0...40 {
                        let th = -CGFloat.pi / 2 + CGFloat(i) / 40 * .pi
                        let c3 = cos(th)
                        let x3 = c3 * sin(phi0), z3 = c3 * cos(phi0)
                        let persp = 1.0 / (1.0 + (1 - z3) * 0.12)
                        let pt = CGPoint(x: cx + x3 * R * persp,
                                         y: cy - sin(th) * R * persp)
                        if !started { mp.move(to: pt); started = true } else { mp.addLine(to: pt) }
                    }
                    ctx.stroke(mp, with: .color(cyan.opacity(day ? 0.13 : 0.08)), lineWidth: 0.4)
                }

                // === 시냅스 엣지 — 깊이로 앞/뒷면 구분 ===
                var front = Path(), back = Path()
                for e in Self.edges {
                    let (pa, za) = proj[e.a], (pb, zb) = proj[e.b]
                    let mid = CGPoint(x: (pa.x + pb.x) / 2 + e.off * (pb.y - pa.y) * 0.3,
                                      y: (pa.y + pb.y) / 2 - e.off * (pb.x - pa.x) * 0.3)
                    if (za + zb) / 2 > -0.15 {
                        front.move(to: pa); front.addQuadCurve(to: pb, control: mid)
                    } else {
                        back.move(to: pa); back.addQuadCurve(to: pb, control: mid)
                    }
                }
                ctx.stroke(back, with: .color(cyan.opacity(day ? 0.14 : 0.10)), lineWidth: 0.5)
                ctx.stroke(front, with: .color(cyan.opacity(day ? 0.38 : 0.32)), lineWidth: 0.6)

                // === 중심 코어 ===
                let coreP = CGPoint(x: cx, y: cy)
                ctx.fill(Path(ellipseIn: CGRect(x: coreP.x - 22, y: coreP.y - 22, width: 44, height: 44)),
                         with: .radialGradient(
                            Gradient(colors: [(day ? cyan : .white).opacity(0.25), cyan.opacity(0.10), cyan.opacity(0)]),
                            center: coreP, startRadius: 0, endRadius: 22))
                ctx.fill(Path(ellipseIn: CGRect(x: coreP.x - 4, y: coreP.y - 4, width: 8, height: 8)),
                         with: .radialGradient(
                            Gradient(colors: [day ? cyan : .white, cyan.opacity(0.6)]),
                            center: coreP, startRadius: 0, endRadius: 4))

                // === 신호 펄스 ===
                for i in 0..<10 {
                    let cyc = 1.4 + Double(i % 5) * 0.35
                    let raw = t / cyc + Double(i) * 0.618
                    let prog = raw.truncatingRemainder(dividingBy: 1)
                    var h = UInt64(i &* 2_654_435_761) &+ UInt64(raw - prog) &* 0x9E3779B97F4A7C15
                    h ^= h >> 13; h &*= 0xBF58476D1CE4E5B9; h ^= h >> 16
                    let e = Self.edges[Int(h % UInt64(Self.edges.count))]
                    let fwd = (h >> 20) & 1 == 0
                    let (pa, za) = proj[e.a], (pb, zb) = proj[e.b]
                    if (za + zb) / 2 < -0.3 { continue }
                    let mid = CGPoint(x: (pa.x + pb.x) / 2 + e.off * (pb.y - pa.y) * 0.3,
                                      y: (pa.y + pb.y) / 2 - e.off * (pb.x - pa.x) * 0.3)
                    func qp(_ f: CGFloat) -> CGPoint {
                        let u = 1 - f
                        return CGPoint(x: u * u * pa.x + 2 * u * f * mid.x + f * f * pb.x,
                                       y: u * u * pa.y + 2 * u * f * mid.y + f * f * pb.y)
                    }
                    let f = fwd ? prog : 1 - prog
                    let pos = qp(f)
                    let col = palette[Self.nodes[fwd ? e.b : e.a].region]
                    var tail = Path()
                    tail.move(to: qp(max(0, f - 0.25)))
                    for k in 1...6 { tail.addLine(to: qp(max(0, f - 0.25) + 0.25 * CGFloat(k) / 6)) }
                    ctx.stroke(tail, with: .color(col.opacity(0.55)), lineWidth: 1.3)
                    ctx.fill(Path(ellipseIn: CGRect(x: pos.x - 6, y: pos.y - 6, width: 12, height: 12)),
                             with: .radialGradient(
                                Gradient(colors: [col.opacity(0.9), col.opacity(0)]),
                                center: pos, startRadius: 0, endRadius: 6))
                    ctx.fill(Path(ellipseIn: CGRect(x: pos.x - 1.4, y: pos.y - 1.4, width: 2.8, height: 2.8)),
                             with: .color(.white))
                }

                // === 뉴런 노드 — z 순 정렬, 깊이 기반 밝기 ===
                let order = Self.nodes.indices.sorted { proj[$0].1 < proj[$1].1 }
                for ni in order {
                    let n = Self.nodes[ni]
                    let (p, z) = proj[ni]
                    let depth = (z + 1) / 2
                    let breathe = 0.5 + 0.5 * sin(t * 1.6 + n.phase)
                    let col = palette[n.region]
                    let alpha = 0.25 + 0.75 * depth
                    let sz = n.size * (0.6 + 0.4 * depth)
                    let gr = sz * 4 + 2
                    ctx.fill(Path(ellipseIn: CGRect(x: p.x - gr, y: p.y - gr, width: gr * 2, height: gr * 2)),
                             with: .radialGradient(
                                Gradient(colors: [col.opacity(0.6 * breathe * alpha), col.opacity(0)]),
                                center: p, startRadius: 0, endRadius: gr))
                    let cr = sz * 0.8
                    ctx.fill(Path(ellipseIn: CGRect(x: p.x - cr, y: p.y - cr, width: cr * 2, height: cr * 2)),
                             with: .color(col.opacity((0.65 + 0.35 * breathe) * alpha)))
                    let hr = cr * 0.5
                    ctx.fill(Path(ellipseIn: CGRect(x: p.x - hr, y: p.y - hr, width: hr * 2, height: hr * 2)),
                             with: .color(.white.opacity(0.85 * alpha)))
                    if ni % 5 == 0 && depth > 0.6 {
                        let L = sz * (3.5 + breathe * 1.5)
                        var sp = Path()
                        sp.move(to: CGPoint(x: p.x - L, y: p.y))
                        sp.addLine(to: CGPoint(x: p.x + L, y: p.y))
                        sp.move(to: CGPoint(x: p.x, y: p.y - L))
                        sp.addLine(to: CGPoint(x: p.x, y: p.y + L))
                        ctx.stroke(sp, with: .color(.white.opacity(0.4 * breathe)), lineWidth: 0.5)
                    }
                }

                // === 비 — 전경 빗줄기 ===
                if kind == .rain || kind == .thunder {
                    let rrnd = Self.seeded(0xA15EED)
                    var rain = Path()
                    for _ in 0..<30 {
                        let x = rrnd() * W
                        let speed = 0.55 + rrnd() * 0.5
                        let ph = rrnd()
                        let y = ((t * speed * 0.85 + ph).truncatingRemainder(dividingBy: 1)) * H
                        rain.move(to: CGPoint(x: x, y: y))
                        rain.addLine(to: CGPoint(x: x - 3, y: y + 8))
                    }
                    ctx.stroke(rain, with: .color(Color(red: 0.6, green: 0.75, blue: 0.9).opacity(0.45)), lineWidth: 0.7)
                }

                // === 눈 — 흔들리며 낙하 ===
                if kind == .snow {
                    let srnd = Self.seeded(0x5A0F1A)
                    for _ in 0..<22 {
                        let ph = srnd()
                        let baseX = srnd() * W
                        let y = ((t * (0.05 + srnd() * 0.07) + ph).truncatingRemainder(dividingBy: 1)) * H
                        let x = baseX + sin(t * 0.8 + ph * 6.28) * 6
                        let r = 0.8 + srnd() * 1.0
                        ctx.fill(Path(ellipseIn: CGRect(x: x - r, y: y - r, width: r * 2, height: r * 2)),
                                 with: .color(.white.opacity(0.7)))
                    }
                }

                // === 번개 — 천둥 날씨, 가끔 지그재그 방전 + 플래시 ===
                if kind == .thunder {
                    let win = 9.0, phase = t.truncatingRemainder(dividingBy: win)
                    let h = Self.whash(t / win + 0.5)
                    if h % 100 < 55 && phase < 0.18 {
                        let brnd = Self.seeded(h)
                        var bolt = Path()
                        var bx = (0.15 + brnd() * 0.7) * W, by: CGFloat = 0
                        bolt.move(to: CGPoint(x: bx, y: by))
                        while by < H * 0.55 {
                            bx += (brnd() - 0.5) * 18; by += 4 + brnd() * 7
                            bolt.addLine(to: CGPoint(x: bx, y: by))
                        }
                        ctx.stroke(bolt, with: .color(Color(red: 0.7, green: 0.8, blue: 1).opacity(0.5)), lineWidth: 3)
                        ctx.stroke(bolt, with: .color(.white.opacity(0.9)), lineWidth: 1.2)
                        ctx.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.white.opacity(0.08)))
                    }
                }
            }
        }
    }
}

struct RootView: View {
    @ObservedObject var model: UsageModel
    let onQuit: () -> Void

    /// 목록이 차지할 수 있는 최대 높이 = 화면 가용 높이 - 헤더/여백
    var maxListHeight: CGFloat {
        (NSScreen.main?.visibleFrame.height ?? 800) - 70
    }

    /// 프로바이더 카드 + 뉴스 카드 + 신경망 맵 — 동일한 horizontal 패딩으로 좌우 열 정렬 통일
    @ViewBuilder var contentList: some View {
        VStack(spacing: 6) {
            ForEach(model.providers) { ProviderCard(p: $0) }
            if !model.news.isEmpty {
                NewsSection(items: model.news, pageSeconds: model.pageSeconds)
            }
            NeuralMapView(weatherCode: model.weather?.code)
                .frame(height: 92)
                .padding(.vertical, 2)
                .background(RoundedRectangle(cornerRadius: 8)
                    .fill(LinearGradient(colors: NeuralMapView.skyColors(model.weather?.code),
                                         startPoint: .top, endPoint: .bottom))
                    .overlay(RoundedRectangle(cornerRadius: 8)
                        .stroke(NeuralMapView.isDay
                                ? Color(red: 0.15, green: 0.35, blue: 0.65).opacity(0.35)
                                : Color(red: 0.40, green: 0.75, blue: 1.0).opacity(0.25),
                                lineWidth: 0.5)))
        }
        .padding(.horizontal, 8)
        .background(
            GeometryReader { g in
                Color.clear.preference(key: ContentHeightKey.self, value: g.size.height)
            }
        )
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Text("Used AI Models").font(.system(size: 11, weight: .bold))
                Spacer()
                if let w = model.weather, let temp = w.temp_c {
                    Image(systemName: weatherSymbol(w.code))
                        .font(.system(size: 9))
                        .symbolRenderingMode(.multicolor)
                    Text("\(temp)°")
                        .font(.system(size: 9, weight: .medium, design: .monospaced))
                        .foregroundStyle(.secondary)
                }
                if let t = model.updatedAt {
                    Text(t, style: .time).font(.system(size: 9, weight: .medium, design: .monospaced))
                        .foregroundStyle(.secondary)
                }
                Button(action: model.refresh) {
                    Image(systemName: model.refreshing ? "arrow.triangle.2.circlepath" : "arrow.clockwise")
                        .font(.system(size: 10))
                }
                .buttonStyle(.plain).foregroundStyle(.secondary)
                .disabled(model.refreshing)
                Button(action: onQuit) {
                    Image(systemName: "power").font(.system(size: 10))
                }
                .buttonStyle(.plain).foregroundStyle(.secondary)
            }
            .padding(.horizontal, 12).padding(.top, 6)

            if let err = model.lastError {
                Text("수집 오류: \(err)").font(.system(size: 9)).foregroundStyle(.red)
                    .padding(.horizontal, 12)
            }

            if model.contentHeight > maxListHeight {
                ScrollView { contentList }
                    .scrollIndicators(.never)
            } else {
                contentList
            }
            Spacer(minLength: 0).padding(.bottom, 1)
        }
        .onPreferenceChange(ContentHeightKey.self) { h in
            if h > 0 && abs(model.contentHeight - h) > 0.5 {
                model.contentHeight = h
                DispatchQueue.main.async { model.onResize?() }
            }
        }
        .frame(width: 300)
        .background(
            RoundedRectangle(cornerRadius: 14)
                .fill(.regularMaterial)
                .overlay(RoundedRectangle(cornerRadius: 14)
                    .stroke(Color.white.opacity(0.14), lineWidth: 0.5))
        )
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }
}

// MARK: - 앱 델리게이트

final class PanelWindow: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    var panel: PanelWindow!
    var model: UsageModel!

    /// 패널 최대 높이 = 화면 가용 높이 - 여백
    var maxPanelHeight: CGFloat {
        (NSScreen.main?.visibleFrame.height ?? 800) - 8
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let script = Bundle.main.resourceURL!
            .appendingPathComponent("collector/collect.py")
        let model = UsageModel(scriptURL: script)
        self.model = model

        let panel = PanelWindow(
            contentRect: NSRect(x: 0, y: 0, width: 300, height: 200),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered, defer: false)
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = true
        panel.isMovableByWindowBackground = true
        panel.hidesOnDeactivate = false
        panel.isReleasedWhenClosed = false
        self.panel = panel

        let root = RootView(model: model, onQuit: { NSApp.terminate(nil) })
        let hosting = NSHostingController(rootView: root)
        panel.contentViewController = hosting

        model.onResize = { [weak panel, weak self] in
            guard let panel, let self else { return }
            // 실측 콘텐츠 높이 + 헤더(~30) + 하단 여백으로 패널 높이 결정
            let contentH = model.contentHeight > 0 ? model.contentHeight : 400
            let newH = min(max(contentH + 36, 90), self.maxPanelHeight)
            var f = panel.frame
            // 높이 변화가 없으면 프레임 재설정 생략 — 갱신마다 패널이 흔들리는 깜빡임 방지
            if abs(newH - f.size.height) < 1.5 { return }
            let top = f.maxY
            f.size.height = newH
            f.origin.y = top - newH
            panel.setFrame(f, display: true, animate: false)
        }

        // 위치 복원 (기본: 화면 우상단)
        if let screen = NSScreen.main {
            let size = hosting.sizeThatFits(in: CGSize(width: 300, height: CGFloat.greatestFiniteMagnitude))
            let h = min(max(size.height, 90), maxPanelHeight)
            let vf = screen.visibleFrame
            let x = UserDefaults.standard.object(forKey: "winX") as? CGFloat
                ?? (vf.maxX - 300 - 20)
            let y = UserDefaults.standard.object(forKey: "winY") as? CGFloat
                ?? (vf.maxY - h - 12)
            panel.setFrame(NSRect(x: x, y: y, width: 300, height: h), display: false)
        }
        NotificationCenter.default.addObserver(
            forName: NSWindow.didMoveNotification, object: panel, queue: .main) { [weak panel] _ in
                guard let f = panel?.frame else { return }
                UserDefaults.standard.set(f.origin.x, forKey: "winX")
                UserDefaults.standard.set(f.origin.y, forKey: "winY")
            }

        panel.orderFrontRegardless()
        model.start()
    }
}

// MARK: - 엔트리포인트

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let delegate = AppDelegate()
app.delegate = delegate
app.run()
