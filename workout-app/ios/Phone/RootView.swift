import SwiftUI

struct RootView: View {
    @State private var config = APIConfig.load()
    @State private var templates: [WorkoutTemplate] = []
    @State private var active: WorkoutSession?
    @State private var error: String?
    @State private var showSettings = false

    var body: some View {
        NavigationStack {
            List {
                if let error { Text(error).foregroundStyle(.red) }
                if let active {
                    Section("In progress") {
                        NavigationLink("\(active.name) (started on \(active.source))") { SessionView(session: active) }
                    }
                }
                Section("Workouts") {
                    ForEach(templates) { t in
                        NavigationLink(t.name) { TemplateDetail(template: t) { s in active = s } }
                    }
                }
            }
            .navigationTitle("Workouts")
            .toolbar { Button("Server") { showSettings = true } }
            .refreshable { await load() }
            .task { await load() }
            .sheet(isPresented: $showSettings) { SettingsView(config: $config) { Task { await load() } } }
        }
    }

    func load() async {
        guard let config else { showSettings = true; return }
        let api = APIClient(config: config)
        do {
            templates = try await api.templates()
            active = try await api.activeSession()
            error = nil
        } catch { self.error = error.localizedDescription }
    }
}

struct SettingsView: View {
    @Binding var config: APIConfig?
    var onSave: () -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var url = APIConfig.load()?.baseURL ?? ""
    @State private var token = APIConfig.load()?.token ?? ""

    var body: some View {
        NavigationStack {
            Form {
                TextField("Server URL (https://…)", text: $url).textInputAutocapitalization(.never).autocorrectionDisabled()
                SecureField("API token", text: $token)
            }
            .navigationTitle("Server")
            .toolbar {
                Button("Save") {
                    let c = APIConfig(baseURL: url, token: token)
                    c.save(); config = c
                    WatchLink.shared.send(c)
                    onSave(); dismiss()
                }
            }
        }
    }
}

struct TemplateDetail: View {
    let template: WorkoutTemplate
    var onStarted: (WorkoutSession) -> Void
    @State private var started: WorkoutSession?
    @State private var error: String?

    var body: some View {
        List {
            ForEach(template.exercises) { e in
                HStack { Text(e.exercise); Spacer(); Text("\(e.sets)×\(e.reps) @ \(e.weightKg, specifier: "%.1f") kg").foregroundStyle(.secondary) }
            }
            if let error { Text(error).foregroundStyle(.red) }
            Button("Start workout") {
                Task {
                    guard let c = APIConfig.load() else { return }
                    do {
                        let s = try await APIClient(config: c).start(templateId: template.id, source: "phone")
                        started = s; onStarted(s)
                    } catch { self.error = error.localizedDescription }
                }
            }
        }
        .navigationTitle(template.name)
        .navigationDestination(item: $started) { SessionView(session: $0) }
    }
}

struct SessionView: View {
    @State var session: WorkoutSession
    @State private var error: String?

    var body: some View {
        List {
            ForEach(session.exercises) { e in
                let done = session.completedSets.filter { $0.exercise == e.exercise }.count
                HStack { Text(e.exercise); Spacer(); Text("\(done)/\(e.sets) sets").foregroundStyle(done >= e.sets ? .green : .secondary) }
            }
            if let error { Text(error).foregroundStyle(.red) }
            if let n = session.next, session.finishedAt == nil {
                Button("Log set \(n.setIndex): \(n.exercise.exercise)") {
                    Task { await run { try await $0.logSet(sessionId: session.id, exercise: n.exercise.exercise,
                                                           setIndex: n.setIndex, reps: n.exercise.reps, weightKg: n.exercise.weightKg) } }
                }
            }
            if session.finishedAt == nil {
                Button("Finish workout", role: .destructive) { Task { await run { try await $0.finish(sessionId: session.id) } } }
            }
        }
        .navigationTitle(session.name)
    }

    func run(_ call: (APIClient) async throws -> WorkoutSession) async {
        guard let c = APIConfig.load() else { return }
        do { session = try await call(APIClient(config: c)) } catch { self.error = error.localizedDescription }
    }
}
