import SwiftUI

/// Build a workout from recovery, time, goal and equipment; preview it, shuffle, then start.
struct GenerateView: View {
    var onStarted: (WorkoutSession) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var minutes = 45
    @State private var goal = "hypertrophy"
    @State private var profile = ""          // "" = server default (equipment you've used)
    @State private var focus = ""            // "" = automatic (most recovered day)
    @State private var variety = 0.2
    @State private var seed = 0
    @State private var profiles: [EquipmentProfile] = []
    @State private var templateNames: [String] = []
    @State private var draft: GeneratedWorkout?
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("Settings") {
                    Stepper("Time: \(minutes) min", value: $minutes, in: 15...120, step: 5)
                    Picker("Goal", selection: $goal) {
                        Text("Muscle").tag("hypertrophy"); Text("Strength").tag("strength"); Text("Endurance").tag("endurance")
                    }
                    Picker("Equipment", selection: $profile) {
                        Text("Default (from my history)").tag("")
                        ForEach(profiles) { Text($0.name).tag($0.name) }
                    }
                    Picker("Focus", selection: $focus) {
                        Text("Automatic (most recovered)").tag("")
                        ForEach(templateNames, id: \.self) { Text($0).tag($0) }
                    }
                    VStack(alignment: .leading) {
                        Text("Exercise choice")
                        Slider(value: $variety, in: 0...1)
                        HStack { Text("Familiar"); Spacer(); Text("Adventurous") }.font(.caption).foregroundStyle(.secondary)
                    }
                    Button(draft == nil ? "Generate" : "Regenerate with these settings") { Task { await generate(newSeed: false) } }
                        .disabled(busy)
                }
                if let error { Text(error).foregroundStyle(.red) }
                if let d = draft {
                    Section {
                        ForEach(d.exercises) { e in
                            VStack(alignment: .leading, spacing: 2) {
                                HStack {
                                    Text(e.exercise)
                                    Spacer()
                                    Text("\(e.sets)×\(e.reps)" + (e.weightKg > 0 ? " @ \(Units.text(e.weightKg))" : ""))
                                        .foregroundStyle(.secondary)
                                }
                                if let w = e.warmup { Text(w).font(.caption2).foregroundStyle(.secondary) }
                                Text(e.reason).font(.caption2).foregroundStyle(.secondary)
                            }
                        }
                    } header: {
                        Text("\(d.name) · ~\(d.estimatedMinutes) min · \(d.equipmentProfile)")
                    }
                    Section {
                        Button("Shuffle") { Task { await generate(newSeed: true) } }.disabled(busy)
                        Button("Start workout") { Task { await start(d) } }.buttonStyle(.borderedProminent).disabled(busy)
                    }
                }
            }
            .navigationTitle("Generate")
            .toolbar { Button("Close") { dismiss() } }
            .task { await loadOptions() }
        }
    }

    func loadOptions() async {
        guard let c = APIConfig.load() else { return }
        let api = APIClient(config: c)
        profiles = (try? await api.profiles()) ?? []
        templateNames = ((try? await api.templates()) ?? []).map(\.name)
    }

    func generate(newSeed: Bool) async {
        guard let c = APIConfig.load() else { return }
        busy = true; defer { busy = false }
        if newSeed { seed += 1 } else { seed = 0 }
        do {
            draft = try await APIClient(config: c).generate(minutes: minutes, goal: goal, profile: profile, template: focus,
                                                            variety: variety, seed: seed == 0 ? nil : seed)
            error = nil
        } catch { self.error = error.localizedDescription }
    }

    func start(_ d: GeneratedWorkout) async {
        guard let c = APIConfig.load() else { return }
        busy = true; defer { busy = false }
        do {
            let s = try await APIClient(config: c).startCustom(d, source: "phone")
            onStarted(s); dismiss()
        } catch { self.error = error.localizedDescription }
    }
}
