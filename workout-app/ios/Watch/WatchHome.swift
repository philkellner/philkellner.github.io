import SwiftUI
import WatchKit

struct WatchHome: View {
    let api: APIClient
    @Environment(\.scenePhase) private var phase
    @State private var templates: [WorkoutTemplate] = []
    @State private var active: WorkoutSession?
    @State private var path: [WorkoutSession] = []
    @State private var error: String?

    var body: some View {
        NavigationStack(path: $path) {
            List {
                if let error { Text(error).font(.footnote).foregroundStyle(.red) }
                // A workout already running (started on the phone or via Discord) shows up here.
                if let active {
                    Button("Resume \(active.name)") { path = [active] }.tint(.green)
                }
                ForEach(templates) { t in
                    Button(t.name) { Task { await start(t) } }
                }
            }
            .navigationTitle("Workouts")
            .navigationDestination(for: WorkoutSession.self) { WatchWorkoutView(api: api, session: $0, onDone: { active = nil; path = [] }) }
            .task { await refresh() }
            .onChange(of: phase) { _, p in if p == .active { Task { await refresh() } } }
        }
    }

    func refresh() async {
        do {
            templates = try await api.templates()
            active = try await api.activeSession()
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    func start(_ t: WorkoutTemplate) async {
        do {
            let s = try await api.start(templateId: t.id, source: "watch")
            active = s; path = [s]
        } catch { self.error = error.localizedDescription }
    }
}

struct WatchWorkoutView: View {
    let api: APIClient
    @State var session: WorkoutSession
    var onDone: () -> Void
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        VStack(spacing: 6) {
            if let n = session.next {
                Text(n.exercise.exercise).font(.headline).multilineTextAlignment(.center)
                Text("Set \(n.setIndex) of \(n.exercise.sets)").foregroundStyle(.secondary)
                Text("\(n.exercise.reps) × \(n.exercise.weightKg, specifier: "%.1f") kg").font(.title3)
                Button("Done") { Task { await log(n.exercise, n.setIndex) } }.disabled(busy).tint(.green)
            } else {
                Text("All sets done").font(.headline)
                Button("Finish") { Task { await finish() } }.disabled(busy).tint(.green)
            }
            if let error { Text(error).font(.footnote).foregroundStyle(.red) }
        }
        .navigationTitle(session.name)
    }

    func log(_ e: ExerciseSpec, _ idx: Int) async {
        busy = true; defer { busy = false }
        do {
            session = try await api.logSet(sessionId: session.id, exercise: e.exercise, setIndex: idx, reps: e.reps, weightKg: e.weightKg)
            WKInterfaceDevice.current().play(.success)
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    func finish() async {
        busy = true; defer { busy = false }
        do { _ = try await api.finish(sessionId: session.id); onDone() } catch { self.error = error.localizedDescription }
    }
}
