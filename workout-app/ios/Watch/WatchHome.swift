import SwiftUI
import WatchKit

struct WatchHome: View {
    let api: APIClient
    @Environment(\.scenePhase) private var phase
    @State private var templates: [WorkoutTemplate] = []
    @State private var active: WorkoutSession?
    @State private var path: [WorkoutSession] = []
    @State private var error: String?
    @State private var generating = false

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
                Button(generating ? "Generating…" : "Generate workout") { Task { await generate() } }
                    .disabled(generating).tint(.blue)
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

    /// Builds a workout from what's recovered and your equipment, then starts it.
    func generate() async {
        generating = true; defer { generating = false }
        do {
            let draft = try await api.generate()
            let s = try await api.startCustom(draft, source: "watch")
            active = s; path = [s]; error = nil
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
    @State private var reps = 0
    @State private var weight = 0.0          // display units (lb or kg); set with the Digital Crown
    @State private var restEnd: Date?
    @State private var busy = false
    @State private var error: String?

    private var key: String {
        guard let n = session.next else { return "" }
        return "\(n.exercise.exercise)#\(n.setIndex)"
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 6) {
                if let restEnd {
                    Text("Rest").font(.caption).foregroundStyle(.secondary)
                    RestCountdown(endDate: restEnd) { endRest(haptic: true) }
                    if let n = session.next {
                        Text("Next: \(n.exercise.exercise)").font(.footnote).multilineTextAlignment(.center)
                    }
                    Button("Skip") { endRest(haptic: false) }
                } else if let n = session.next {
                    Text(n.exercise.exercise).font(.headline).multilineTextAlignment(.center)
                    Text("Set \(n.setIndex) of \(n.exercise.sets)").font(.footnote).foregroundStyle(.secondary)
                    if let why = n.exercise.suggestion?.reason {
                        Text(why).font(.caption2).foregroundStyle(.secondary).multilineTextAlignment(.center)
                    }
                    HStack {
                        Button { reps = max(0, reps - 1) } label: { Image(systemName: "minus") }
                        Text("\(reps) reps").frame(minWidth: 60)
                        Button { reps += 1 } label: { Image(systemName: "plus") }
                    }
                    Text("\(weight, specifier: "%g") \(Units.label)")
                        .font(.title3)
                        .focusable()
                        .digitalCrownRotation($weight, from: 0, through: 1500, by: Units.step,
                                              sensitivity: .low, isContinuous: false, isHapticFeedbackEnabled: true)
                    Text("Turn crown to change weight").font(.caption2).foregroundStyle(.secondary)
                    Button("Log set") { Task { await log(n.exercise, n.setIndex) } }.disabled(busy).tint(.green)
                } else {
                    Text("All sets done").font(.headline)
                    Button("Finish") { Task { await finish() } }.disabled(busy).tint(.green)
                }
                if let error { Text(error).font(.footnote).foregroundStyle(.red) }
            }
        }
        .navigationTitle(session.name)
        .onAppear(perform: loadSuggestion)
        .onChange(of: key) { _, _ in loadSuggestion() }
    }

    func loadSuggestion() {
        guard let n = session.next else { return }
        let s = n.exercise.prefill(forSet: n.setIndex)
        reps = s.reps
        weight = Units.snapped(s.weightKg)
    }

    func log(_ e: ExerciseSpec, _ idx: Int) async {
        busy = true; defer { busy = false }
        do {
            session = try await api.logSet(sessionId: session.id, exercise: e.exercise, setIndex: idx,
                                           reps: reps, weightKg: Units.toKg(weight))
            error = nil
            WKInterfaceDevice.current().play(.success)
            if let next = session.next {
                restEnd = Date().addingTimeInterval(TimeInterval(e.restSeconds))
                RestAlert.schedule(after: e.restSeconds, next: next.exercise.exercise)
            }
        } catch { self.error = error.localizedDescription }
    }

    func endRest(haptic: Bool) {
        if haptic { WKInterfaceDevice.current().play(.notification) } else { RestAlert.cancel() }
        restEnd = nil
    }

    func finish() async {
        busy = true; defer { busy = false }
        do { _ = try await api.finish(sessionId: session.id); onDone() } catch { self.error = error.localizedDescription }
    }
}
