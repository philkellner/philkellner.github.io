import Foundation

struct SetResult: Codable, Hashable {
    var reps: Int
    var weightKg: Double
}

struct LastPerformance: Codable, Hashable {
    var date: String
    var sets: [SetResult]
}

struct Suggestion: Codable, Hashable {
    var weightKg: Double
    var reps: Int
    var reason: String
}

struct MuscleRecovery: Codable, Identifiable, Hashable {
    var muscle: String
    var recoveryPct: Int
    var status: String        // ready / recovering / fatigued
    var lastTrained: String?
    var id: String { muscle }
}

struct TemplateReadiness: Codable, Identifiable, Hashable {
    var templateId: Int
    var name: String
    var readiness: Int
    var limitingMuscle: String?
    var recommended: Bool
    var id: Int { templateId }
}

struct ExerciseSpec: Codable, Identifiable, Hashable {
    var exercise: String
    var sets: Int
    var reps: Int
    var weightKg: Double
    var restSeconds: Int
    var last: LastPerformance?
    var suggestion: Suggestion?
    var id: String { exercise }

    /// What to prefill for a given 1-based set: the progression suggestion, else what you did last time, else the plan.
    func prefill(forSet index: Int) -> SetResult {
        if let s = suggestion { return SetResult(reps: s.reps, weightKg: s.weightKg) }
        if let l = last?.sets, !l.isEmpty { return l[min(index, l.count) - 1] }
        return SetResult(reps: reps, weightKg: weightKg)
    }
}

struct WorkoutTemplate: Codable, Identifiable, Hashable {
    var id: Int
    var name: String
    var exercises: [ExerciseSpec]
}

struct CompletedSet: Codable, Identifiable, Hashable {
    var id: Int
    var exercise: String
    var setIndex: Int
    var reps: Int
    var weightKg: Double
    var isWarmup: Bool
    var completedAt: String
}

struct WorkoutSession: Codable, Identifiable, Hashable {
    var id: Int
    var templateId: Int?
    var name: String
    var startedAt: String
    var finishedAt: String?
    var source: String
    var exercises: [ExerciseSpec]
    var completedSets: [CompletedSet]

    func workingSets(of exercise: String) -> [CompletedSet] {
        completedSets.filter { $0.exercise == exercise && !$0.isWarmup }
    }

    /// First exercise that still has working sets left, with the 1-based index of its next set.
    /// Derived from the server's data so a workout started elsewhere resumes in the right place.
    var next: (exercise: ExerciseSpec, setIndex: Int)? {
        for e in exercises {
            let done = workingSets(of: e.exercise).count
            if done < e.sets { return (e, done + 1) }
        }
        return nil
    }
}

struct ExerciseSummary: Codable, Identifiable, Hashable {
    var exercise: String
    var sessions: Int
    var bestE1rmKg: Double
    var lastDate: String
    var id: String { exercise }
}

struct HistoryEntry: Codable, Identifiable, Hashable {
    var sessionId: Int
    var date: String
    var sets: [SetResult]
    var bestE1rmKg: Double
    var id: Int { sessionId }
}

func parseISO(_ s: String) -> Date? { ISO8601DateFormatter().date(from: s) }

func shortDate(_ iso: String) -> String {
    guard let d = parseISO(iso) else { return iso }
    return d.formatted(date: .abbreviated, time: .omitted)
}

/// The server stores kilograms; this converts for display and input.
enum Units {
    private static let key = "useLb"
    static var useLb: Bool {
        get { UserDefaults.standard.object(forKey: key) as? Bool ?? true }
        set { UserDefaults.standard.set(newValue, forKey: key) }
    }
    static var label: String { useLb ? "lb" : "kg" }
    /// Increment for steppers and the Digital Crown.
    static var step: Double { useLb ? 5 : 2.5 }

    static func display(_ kg: Double) -> Double {
        let v = useLb ? kg * 2.20462 : kg
        return (v * 2).rounded() / 2
    }
    /// Display value snapped to the nearest loadable step (5 lb or 2.5 kg), for suggested weights.
    static func snapped(_ kg: Double) -> Double {
        let raw = useLb ? kg * 2.20462 : kg
        return (raw / step).rounded() * step
    }
    static func toKg(_ value: Double) -> Double {
        let kg = useLb ? value / 2.20462 : value
        return (kg * 100).rounded() / 100
    }
    static func text(_ kg: Double) -> String {
        let v = display(kg)
        return (v == v.rounded() ? String(Int(v)) : String(format: "%.1f", v)) + " " + label
    }
}
