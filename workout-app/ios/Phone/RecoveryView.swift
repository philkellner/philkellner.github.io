import SwiftUI

/// How recovered each muscle is, most fatigued first.
struct RecoveryTab: View {
    @State private var rows: [MuscleRecovery] = []
    @State private var error: String?

    var body: some View {
        NavigationStack {
            List {
                if let error { Text(error).foregroundStyle(.red) }
                ForEach(rows) { r in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(r.muscle.capitalized)
                            Spacer()
                            Text("\(r.recoveryPct)% · \(r.status)").font(.caption).foregroundStyle(.secondary)
                        }
                        ProgressView(value: Double(r.recoveryPct), total: 100).tint(color(r.status))
                        if let last = r.lastTrained {
                            Text("Last trained \(shortDate(last))").font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                }
                Section {} footer: {
                    Text("Estimated from your logged sets: bigger muscles and harder sessions take longer to recover.")
                }
            }
            .navigationTitle("Recovery")
            .refreshable { await load() }
            .task { await load() }
        }
    }

    func color(_ status: String) -> Color {
        switch status {
        case "ready": return .green
        case "recovering": return .orange
        default: return .red
        }
    }

    func load() async {
        guard let c = APIConfig.load() else { return }
        do { rows = try await APIClient(config: c).recovery(); error = nil }
        catch { self.error = error.localizedDescription }
    }
}
