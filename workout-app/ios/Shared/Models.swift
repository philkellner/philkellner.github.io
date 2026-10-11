import Foundation

struct ExerciseSpec: Codable, Identifiable, Hashable {
    var exercise: String
    var sets: Int
    var reps: Int
    var weightKg: Double
    var id: String { exercise }
}

struct WorkoutTemplate: Codable, Identifiable, Hashable {
    var id: Int
    var name: String
    var exercises: [ExerciseSpec]
}

struct CompletedSet: Codable, Hashable {
    var exercise: String
    var setIndex: Int
    var reps: Int
    var weightKg: Double
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

    /// First exercise that still has sets left, with the 1-based index of its next set.
    /// Derived from the server's data so a workout started on the phone or Discord resumes in the right place.
    var next: (exercise: ExerciseSpec, setIndex: Int)? {
        for e in exercises {
            let done = completedSets.filter { $0.exercise == e.exercise }.count
            if done < e.sets { return (e, done + 1) }
        }
        return nil
    }
}
