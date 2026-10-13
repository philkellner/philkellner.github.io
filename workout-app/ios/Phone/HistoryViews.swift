import SwiftUI
import Charts

struct HistoryTab: View {
    @State private var sessions: [WorkoutSession] = []
    @State private var error: String?

    var body: some View {
        NavigationStack {
            List {
                if let error { Text(error).foregroundStyle(.red) }
                ForEach(sessions) { s in
                    NavigationLink {
                        SessionDetail(session: s)
                    } label: {
                        VStack(alignment: .leading) {
                            Text(s.name)
                            Text("\(shortDate(s.startedAt)) · \(s.completedSets.filter { !$0.isWarmup }.count) sets"
                                 + (s.health?.avgHeartRate.map { " · ♥ \(Int($0))" } ?? ""))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .navigationTitle("History")
            .refreshable { await load() }
            .task { await load() }
        }
    }

    func load() async {
        guard let c = APIConfig.load() else { return }
        do { sessions = try await APIClient(config: c).sessions(limit: 100); error = nil }
        catch { self.error = error.localizedDescription }
    }
}

struct SessionDetail: View {
    let session: WorkoutSession

    var body: some View {
        List {
            if let h = session.health {
                Section("Health") {
                    if let avg = h.avgHeartRate {
                        LabeledContent("Heart rate", value: "avg \(Int(avg))" + (h.maxHeartRate.map { ", max \(Int($0))" } ?? "") + " bpm")
                    }
                    if let kcal = h.activeCalories { LabeledContent("Active energy", value: "\(Int(kcal)) kcal") }
                    if let d = h.durationSeconds { LabeledContent("Duration", value: "\(d / 60) min") }
                }
            }
            ForEach(session.exercises) { e in
                let sets = session.completedSets.filter { $0.exercise == e.exercise && !$0.isWarmup }
                if !sets.isEmpty {
                    Section(e.exercise) {
                        ForEach(sets) { s in
                            HStack { Text("Set \(s.setIndex)"); Spacer(); Text("\(s.reps) × \(Units.text(s.weightKg))").foregroundStyle(.secondary) }
                        }
                    }
                }
            }
        }
        .navigationTitle(shortDate(session.startedAt))
    }
}

struct ProgressTab: View {
    @State private var exercises: [ExerciseSummary] = []
    @State private var error: String?

    var body: some View {
        NavigationStack {
            List {
                if let error { Text(error).foregroundStyle(.red) }
                ForEach(exercises) { e in
                    NavigationLink {
                        ExerciseProgress(exercise: e.exercise)
                    } label: {
                        HStack {
                            VStack(alignment: .leading) {
                                Text(e.exercise)
                                Text("\(e.sessions) sessions · last \(shortDate(e.lastDate))").font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            if e.bestE1rmKg > 0 { Text("1RM ≈ \(Units.text(e.bestE1rmKg))").font(.caption) }
                        }
                    }
                }
            }
            .navigationTitle("Progress")
            .refreshable { await load() }
            .task { await load() }
        }
    }

    func load() async {
        guard let c = APIConfig.load() else { return }
        do { exercises = try await APIClient(config: c).exercises(); error = nil }
        catch { self.error = error.localizedDescription }
    }
}

struct ExerciseProgress: View {
    let exercise: String
    @State private var entries: [HistoryEntry] = []   // newest first
    @State private var error: String?

    private var points: [(date: Date, value: Double)] {
        entries.compactMap { e in
            guard e.bestE1rmKg > 0, let d = parseISO(e.date) else { return nil }
            return (d, Units.display(e.bestE1rmKg))
        }
    }

    var body: some View {
        List {
            if let error { Text(error).foregroundStyle(.red) }
            if points.count > 1 {
                Section("Estimated 1RM (\(Units.label))") {
                    Chart(points, id: \.date) { p in
                        LineMark(x: .value("Date", p.date), y: .value("1RM", p.value))
                        PointMark(x: .value("Date", p.date), y: .value("1RM", p.value))
                    }
                    .chartYScale(domain: .automatic(includesZero: false))
                    .frame(height: 200)
                }
            }
            Section("Sessions") {
                ForEach(entries) { e in
                    VStack(alignment: .leading) {
                        Text(shortDate(e.date)).font(.subheadline)
                        Text(e.sets.map { "\($0.reps)×\(Units.text($0.weightKg))" }.joined(separator: ", "))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
        }
        .navigationTitle(exercise)
        .task {
            guard let c = APIConfig.load() else { return }
            do { entries = try await APIClient(config: c).history(exercise: exercise) }
            catch { self.error = error.localizedDescription }
        }
    }
}
