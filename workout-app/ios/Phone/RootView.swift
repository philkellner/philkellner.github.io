import SwiftUI

struct RootView: View {
    @State private var config = APIConfig.load()
    @State private var showSettings = false

    var body: some View {
        TabView {
            WorkoutsTab(config: $config, showSettings: $showSettings)
                .tabItem { Label("Workouts", systemImage: "dumbbell") }
            HistoryTab()
                .tabItem { Label("History", systemImage: "clock") }
            ProgressTab()
                .tabItem { Label("Progress", systemImage: "chart.line.uptrend.xyaxis") }
        }
        .sheet(isPresented: $showSettings) { SettingsView(config: $config) }
        .onAppear { if config == nil { showSettings = true } }
    }
}

struct WorkoutsTab: View {
    @Binding var config: APIConfig?
    @Binding var showSettings: Bool
    @State private var templates: [WorkoutTemplate] = []
    @State private var active: WorkoutSession?
    @State private var error: String?

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
            .toolbar { Button("Settings") { showSettings = true } }
            .refreshable { await load() }
            .task(id: config) { await load() }
        }
    }

    func load() async {
        guard let config else { return }
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
    @Environment(\.dismiss) private var dismiss
    @State private var url = APIConfig.load()?.baseURL ?? ""
    @State private var token = APIConfig.load()?.token ?? ""
    @State private var useLb = Units.useLb

    var body: some View {
        NavigationStack {
            Form {
                Section("Server") {
                    TextField("Server URL (https://…)", text: $url).textInputAutocapitalization(.never).autocorrectionDisabled()
                    SecureField("API token", text: $token)
                }
                Section("Units") {
                    Picker("Weight", selection: $useLb) { Text("lb").tag(true); Text("kg").tag(false) }
                        .pickerStyle(.segmented)
                }
            }
            .navigationTitle("Settings")
            .toolbar {
                Button("Save") {
                    Units.useLb = useLb
                    let c = APIConfig(baseURL: url, token: token)
                    c.save(); config = c
                    WatchLink.shared.send(c)
                    dismiss()
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
                HStack { Text(e.exercise); Spacer(); Text("\(e.sets)×\(e.reps) @ \(Units.text(e.weightKg))").foregroundStyle(.secondary) }
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
