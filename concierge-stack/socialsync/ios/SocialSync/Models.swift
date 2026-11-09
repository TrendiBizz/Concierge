import Foundation
import SwiftUI

// MARK: - Platforms

enum Platform: String, CaseIterable, Identifiable {
    case linkedin, facebook, instagram, twitter

    var id: String { rawValue }

    var label: String {
        switch self {
        case .linkedin: return "LinkedIn"
        case .facebook: return "Facebook"
        case .instagram: return "Instagram"
        case .twitter: return "X"
        }
    }

    var tag: String {
        switch self {
        case .linkedin: return "in"
        case .facebook: return "f"
        case .instagram: return "ig"
        case .twitter: return "X"
        }
    }

    var color: Color {
        switch self {
        case .linkedin: return Color(red: 0.04, green: 0.40, blue: 0.76)
        case .facebook: return Color(red: 0.09, green: 0.47, blue: 0.95)
        case .instagram: return Color(red: 0.76, green: 0.21, blue: 0.52)
        case .twitter: return Color.primary
        }
    }
}

// MARK: - Posts

enum PostStatus: String, Codable {
    case draft, scheduled, posted

    var label: String {
        switch self {
        case .draft: return "Draft"
        case .scheduled: return "Scheduled"
        case .posted: return "Posted"
        }
    }
}

struct Post: Codable, Identifiable, Hashable {
    let id: Int
    var content: String
    var link: String
    var hashtags: String
    var platforms: [String]
    var mediaIds: [Int]
    var status: PostStatus
    var scheduledAt: Date?
    var postedAt: Date?
    var createdAt: Date
    var updatedAt: Date

    var isDue: Bool {
        status == .scheduled && (scheduledAt ?? .distantFuture) <= Date()
    }

    /// The date this post sits on in the calendar.
    var calendarDate: Date? {
        status == .posted ? postedAt : scheduledAt
    }

    var statusLabel: String { isDue ? "Due now" : status.label }

    /// Text ready to paste into a platform.
    var shareText: String {
        [content, link, hashtags]
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .joined(separator: "\n\n")
    }
}

struct MediaItem: Codable, Identifiable, Hashable {
    let id: Int
    var filename: String
    var mime: String
    var size: Int
    var caption: String
    var project: String
    var createdAt: Date
    var url: String

    var isVideo: Bool { mime.hasPrefix("video/") }
}

// MARK: - Checks (guardrails)

struct CheckIssue: Codable, Identifiable, Hashable {
    let code: String
    let message: String
    var platform: String?
    var match: String?

    var id: String { "\(code)|\(platform ?? "")|\(message)" }
}

struct PlatformCount: Codable, Hashable {
    let label: String
    let length: Int
    let limit: Int
    let over: Bool
}

struct Check: Codable, Hashable {
    let ok: Bool
    let errors: [CheckIssue]
    let warnings: [CheckIssue]
    let platforms: [String: PlatformCount]
}

// MARK: - Rules from the server

struct PlatformRule: Codable, Hashable {
    let label: String
    let limit: Int
    var linkLength: Int?
    var requiresMedia: Bool?
}

struct Rules: Codable, Hashable {
    let platforms: [String: PlatformRule]
    let platformOrder: [String]
}

// MARK: - Editing state shared by Compose, Calendar and Posts

struct Draft: Equatable {
    var id: Int?
    var status: PostStatus = .draft
    var content = ""
    var link = ""
    var hashtags = ""
    var platforms: Set<String> = []
    var mediaIds: [Int] = []
    var when: Date = Draft.defaultTime()

    init() {}

    init(post: Post) {
        id = post.id
        status = post.status
        content = post.content
        link = post.link
        hashtags = post.hashtags
        platforms = Set(post.platforms)
        mediaIds = post.mediaIds
        when = post.scheduledAt ?? Draft.defaultTime()
    }

    static func defaultTime() -> Date {
        let calendar = Calendar.current
        let tomorrow = calendar.date(byAdding: .day, value: 1, to: Date()) ?? Date()
        return calendar.date(bySettingHour: 9, minute: 0, second: 0, of: tomorrow) ?? tomorrow
    }

    /// Characters this draft uses on a platform. X counts any link as a fixed length.
    func length(for rule: PlatformRule?) -> Int {
        let text = content.trimmingCharacters(in: .whitespacesAndNewlines)
        let url = link.trimmingCharacters(in: .whitespacesAndNewlines)
        let tags = hashtags.trimmingCharacters(in: .whitespacesAndNewlines)
        var total = text.count
        if !url.isEmpty {
            total += (total > 0 ? 1 : 0) + (rule?.linkLength ?? url.count)
        }
        if !tags.isEmpty {
            total += (total > 0 ? 1 : 0) + tags.count
        }
        return total
    }
}

// MARK: - Responses

struct PostResponse: Codable { let post: Post; let check: Check }
struct PostsResponse: Codable { let posts: [Post] }
struct MediaResponse: Codable { let media: MediaItem }
struct MediaListResponse: Codable { let media: [MediaItem] }
struct CheckResponse: Codable { let check: Check }
struct LoginResponse: Codable { let token: String }
struct Health: Codable { let ok: Bool }
struct OK: Codable { let ok: Bool }

// MARK: - Social pages

struct Channel: Codable, Identifiable, Hashable {
    let id: Int
    var platform: String
    var name: String
    var url: String
    var notes: String
    var createdAt: Date
    var updatedAt: Date
}

struct ChannelsResponse: Codable { let channels: [Channel]; let platforms: [String] }
struct ChannelResponse: Codable { let channel: Channel }

/// One "Post now" button: where to open for a platform once the text is copied.
struct PublishTarget: Identifiable {
    let platform: String
    let label: String
    let url: URL?
    let hint: String
    var id: String { platform }
}
