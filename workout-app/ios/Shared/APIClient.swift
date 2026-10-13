import Foundation

struct APIConfig: Equatable {
    var baseURL: String
    var token: String

    private static let key = "apiConfig"

    static func load() -> APIConfig? {
        guard let d = UserDefaults.standard.dictionary(forKey: key) as? [String: String],
              let url = d["baseURL"], let token = d["token"], !url.isEmpty, !token.isEmpty else { return nil }
        return APIConfig(baseURL: url, token: token)
    }

    func save() {
        UserDefaults.standard.set(["baseURL": baseURL, "token": token], forKey: Self.key)
    }
}

enum APIError: LocalizedError {
    case notConfigured, badStatus(Int)
    var errorDescription: String? {
        switch self {
        case .notConfigured: return "Set the server URL and token on your iPhone first."
        case .badStatus(let c): return "Server returned \(c)."
        }
    }
}

struct APIClient {
    let config: APIConfig

    private var decoder: JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func request(_ method: String, _ path: String, body: [String: Any]? = nil) async throws -> (Data, Int) {
        guard let url = URL(string: config.baseURL.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + path) else {
            throw APIError.notConfigured
        }
        var req = URLRequest(url: url, timeoutInterval: 15)
        req.httpMethod = method
        req.setValue("Bearer \(config.token)", forHTTPHeaderField: "Authorization")
        if let body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, resp) = try await URLSession.shared.data(for: req)
        return (data, (resp as? HTTPURLResponse)?.statusCode ?? 0)
    }

    private func decode<T: Decodable>(_ t: T.Type, _ r: (Data, Int)) throws -> T {
        guard (200..<300).contains(r.1) else { throw APIError.badStatus(r.1) }
        return try decoder.decode(T.self, from: r.0)
    }

    func templates() async throws -> [WorkoutTemplate] {
        try decode([WorkoutTemplate].self, try await request("GET", "/templates"))
    }

    /// The in-progress workout, or nil when none is running (server answers 404).
    func activeSession() async throws -> WorkoutSession? {
        let r = try await request("GET", "/sessions/active")
        if r.1 == 404 { return nil }
        return try decode(WorkoutSession.self, r)
    }

    func start(templateId: Int, source: String) async throws -> WorkoutSession {
        try decode(WorkoutSession.self, try await request("POST", "/sessions",
                   body: ["template_id": templateId, "source": source]))
    }

    func logSet(sessionId: Int, exercise: String, setIndex: Int, reps: Int, weightKg: Double,
                isWarmup: Bool = false) async throws -> WorkoutSession {
        try decode(WorkoutSession.self, try await request("POST", "/sessions/\(sessionId)/sets",
                   body: ["exercise": exercise, "set_index": setIndex, "reps": reps, "weight_kg": weightKg,
                          "is_warmup": isWarmup]))
    }

    func deleteSet(sessionId: Int, setId: Int) async throws -> WorkoutSession {
        try decode(WorkoutSession.self, try await request("DELETE", "/sessions/\(sessionId)/sets/\(setId)"))
    }

    func sessions(limit: Int = 100) async throws -> [WorkoutSession] {
        try decode([WorkoutSession].self, try await request("GET", "/sessions?limit=\(limit)"))
    }

    func saveHealth(sessionId: Int, summary: WorkoutSummary) async throws -> WorkoutSession {
        var body: [String: Any] = ["duration_seconds": summary.durationSeconds]
        if let v = summary.avgHeartRate { body["avg_heart_rate"] = v }
        if let v = summary.maxHeartRate { body["max_heart_rate"] = v }
        if let v = summary.activeCalories { body["active_calories"] = v }
        if let v = summary.healthkitUUID { body["healthkit_uuid"] = v }
        return try decode(WorkoutSession.self, try await request("POST", "/sessions/\(sessionId)/health", body: body))
    }

    func info(exercise: String) async throws -> ExerciseInfo {
        let name = exercise.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? exercise
        return try decode(ExerciseInfo.self, try await request("GET", "/exercises/\(name)/info"))
    }

    /// Absolute URL for a server-relative path such as a signed video link.
    func absoluteURL(_ path: String) -> URL? {
        URL(string: config.baseURL.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + path)
    }

    func profiles() async throws -> [EquipmentProfile] {
        try decode([EquipmentProfile].self, try await request("GET", "/equipment-profiles"))
    }

    func generate(minutes: Int = 45, goal: String = "hypertrophy", profile: String? = nil, template: String? = nil,
                  variety: Double = 0.2, seed: Int? = nil) async throws -> GeneratedWorkout {
        var body: [String: Any] = ["minutes": minutes, "goal": goal, "variety": variety]
        if let profile, !profile.isEmpty { body["profile"] = profile }
        if let template, !template.isEmpty { body["template"] = template }
        if let seed { body["seed"] = seed }
        return try decode(GeneratedWorkout.self, try await request("POST", "/generate", body: body))
    }

    func startCustom(_ w: GeneratedWorkout, source: String) async throws -> WorkoutSession {
        let exercises = w.exercises.map { e -> [String: Any] in
            ["exercise": e.exercise, "sets": e.sets, "reps": e.reps, "weight_kg": e.weightKg, "rest_seconds": e.restSeconds]
        }
        return try decode(WorkoutSession.self, try await request("POST", "/sessions/custom",
                          body: ["name": w.name, "source": source, "exercises": exercises]))
    }

    func alternatives(for exercise: String) async throws -> [Alternative] {
        let name = exercise.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? exercise
        return try decode([Alternative].self, try await request("GET", "/exercises/\(name)/alternatives"))
    }

    func swap(sessionId: Int, exercise: String, replacement: String) async throws -> WorkoutSession {
        try decode(WorkoutSession.self, try await request("POST", "/sessions/\(sessionId)/swap",
                   body: ["exercise": exercise, "replacement": replacement]))
    }

    func recovery() async throws -> [MuscleRecovery] {
        try decode([MuscleRecovery].self, try await request("GET", "/recovery"))
    }

    func recommendation() async throws -> [TemplateReadiness] {
        try decode([TemplateReadiness].self, try await request("GET", "/recommendation"))
    }

    func exercises() async throws -> [ExerciseSummary] {
        try decode([ExerciseSummary].self, try await request("GET", "/exercises"))
    }

    func history(exercise: String, limit: Int = 60) async throws -> [HistoryEntry] {
        let name = exercise.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? exercise
        return try decode([HistoryEntry].self, try await request("GET", "/exercises/\(name)/history?limit=\(limit)"))
    }

    func finish(sessionId: Int) async throws -> WorkoutSession {
        try decode(WorkoutSession.self, try await request("POST", "/sessions/\(sessionId)/finish"))
    }
}
