import SwiftUI

/// Live workout: log reps and weight for each set, with a rest timer between sets.
struct SessionView: View {
    @State var session: WorkoutSession
    @State private var reps = 0
    @State private var weight = 0.0          // in display units (lb or kg)
    @State private var warmup = false
    @State private var restEnd: Date?
    @State private var error: String?
    @State private var swapFrom: String?
    @State private var alternatives: [Alternative] = []

    private var key: String {
        guard let n = session.next else { return "" }
        return "\(n.exercise.exercise)#\(n.setIndex)"
    }

    var body: some View {
        List {
            if let restEnd {
                Section {
                    VStack {
                        Text("Rest").font(.caption).foregroundStyle(.secondary)
                        RestCountdown(endDate: restEnd) { finishRest(skipped: false) }
                        Button("Skip rest") { finishRest(skipped: true) }.buttonStyle(.bordered)
                    }
                    .frame(maxWidth: .infinity)
                }
            }
            ForEach(session.exercises) { e in
                Section {
                    ForEach(session.completedSets.filter { $0.exercise == e.exercise }) { s in
                        HStack {
                            Text(s.isWarmup ? "Warm-up" : "Set \(s.setIndex)")
                            Spacer()
                            Text("\(s.reps) × \(Units.text(s.weightKg))").foregroundStyle(.secondary)
                        }
                        .swipeActions { Button("Delete", role: .destructive) { Task { await delete(s) } } }
                    }
                    if session.finishedAt == nil, let n = session.next, n.exercise.exercise == e.exercise {
                        logControls(n.exercise, setIndex: n.setIndex)
                    }
                } header: {
                    HStack {
                        Text(e.exercise)
                        Spacer()
                        if session.finishedAt == nil && session.workingSets(of: e.exercise).isEmpty && session.completedSets.filter({ $0.exercise == e.exercise }).isEmpty {
                            Button { Task { await loadAlternatives(for: e.exercise) } } label: {
                                Label("Swap", systemImage: "arrow.triangle.2.circlepath")
                            }
                            .font(.caption)
                        }
                    }
                } footer: {
                    VStack(alignment: .leading) {
                        if let sug = e.suggestion { Text("Suggested: \(sug.reps) × \(Units.text(sug.weightKg)). \(sug.reason)") }
                        if let last = e.last {
                            Text("Last (\(shortDate(last.date))): " + last.sets.map { "\($0.reps)×\(Units.text($0.weightKg))" }.joined(separator: ", "))
                        }
                    }
                }
            }
            if let error { Text(error).foregroundStyle(.red) }
            if session.finishedAt == nil {
                Button(session.next == nil ? "Finish workout" : "Finish early", role: session.next == nil ? nil : .destructive) {
                    Task { await run { try await $0.finish(sessionId: session.id) } }
                }
            }
        }
        .navigationTitle(session.name)
        .confirmationDialog("Swap \(swapFrom ?? "")", isPresented: Binding(get: { swapFrom != nil }, set: { if !$0 { swapFrom = nil } }),
                            titleVisibility: .visible) {
            ForEach(alternatives) { a in
                Button("\(a.exercise) (\(a.equipment.joined(separator: ", ")))") { Task { await swap(to: a.exercise) } }
            }
        } message: {
            if alternatives.isEmpty { Text("No alternatives for your equipment.") }
        }
        .onAppear(perform: loadSuggestion)
        .onChange(of: key) { _, _ in loadSuggestion() }
    }

    @ViewBuilder
    func logControls(_ e: ExerciseSpec, setIndex: Int) -> some View {
        Stepper("Reps: \(reps)", value: $reps, in: 0...100)
        Stepper("Weight: \(weight, specifier: "%g") \(Units.label)", value: $weight, in: 0...1500, step: Units.step)
        Toggle("Warm-up set", isOn: $warmup)
        Button(warmup ? "Log warm-up" : "Log set \(setIndex) of \(e.sets)") { Task { await log(e, setIndex) } }
            .buttonStyle(.borderedProminent)
    }

    func loadSuggestion() {
        guard let n = session.next else { return }
        let s = n.exercise.prefill(forSet: n.setIndex)
        reps = s.reps
        weight = Units.snapped(s.weightKg)
    }

    func log(_ e: ExerciseSpec, _ setIndex: Int) async {
        let count = session.completedSets.filter { $0.exercise == e.exercise }.count
        let isWarmup = warmup
        await run { try await $0.logSet(sessionId: session.id, exercise: e.exercise,
                                        setIndex: isWarmup ? count + 1 : setIndex,
                                        reps: reps, weightKg: Units.toKg(weight), isWarmup: isWarmup) }
        if error == nil, !isWarmup, session.next != nil {
            restEnd = Date().addingTimeInterval(TimeInterval(e.restSeconds))
            RestAlert.schedule(after: e.restSeconds, next: session.next?.exercise.exercise ?? "")
        }
        warmup = false
    }

    func loadAlternatives(for exercise: String) async {
        guard let c = APIConfig.load() else { return }
        do {
            alternatives = try await APIClient(config: c).alternatives(for: exercise)
            swapFrom = exercise
        } catch { self.error = error.localizedDescription }
    }

    func swap(to replacement: String) async {
        guard let from = swapFrom else { return }
        swapFrom = nil
        await run { try await $0.swap(sessionId: session.id, exercise: from, replacement: replacement) }
    }

    func delete(_ s: CompletedSet) async {
        await run { try await $0.deleteSet(sessionId: session.id, setId: s.id) }
    }

    func finishRest(skipped: Bool) {
        if skipped { RestAlert.cancel() }
        restEnd = nil
    }

    func run(_ call: (APIClient) async throws -> WorkoutSession) async {
        guard let c = APIConfig.load() else { return }
        do { session = try await call(APIClient(config: c)); error = nil } catch { self.error = error.localizedDescription }
    }
}
