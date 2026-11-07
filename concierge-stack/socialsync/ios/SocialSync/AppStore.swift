import Foundation
import Observation
import PhotosUI
import Security
import SwiftUI
import UIKit

// MARK: - Keychain (the session token never goes in UserDefaults)

enum Keychain {
    private static let service = "nz.co.pukekoconstruction.socialsync"
    private static let account = "session-token"

    private static var baseQuery: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }

    static func read() -> String? {
        var query = baseQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func write(_ value: String) {
        delete()
        var query = baseQuery
        query[kSecValueData as String] = Data(value.utf8)
        query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        SecItemAdd(query as CFDictionary, nil)
    }

    static func delete() {
        SecItemDelete(baseQuery as CFDictionary)
    }
}

// MARK: - Picked video transfer

struct MovieFile: Transferable {
    let url: URL

    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(contentType: .movie) { movie in
            SentTransferredFile(movie.url)
        } importing: { received in
            let ext = received.file.pathExtension.isEmpty ? "mov" : received.file.pathExtension
            let copy = FileManager.default.temporaryDirectory
                .appendingPathComponent("upload-\(UUID().uuidString).\(ext)")
            try FileManager.default.copyItem(at: received.file, to: copy)
            return MovieFile(url: copy)
        }
    }
}

// MARK: - Store

@MainActor
@Observable
final class AppStore {
    enum Tab: Hashable {
        case compose, calendar, posts, photos, settings
    }

    var selectedTab: Tab = .compose
    var serverURLString: String
    private(set) var token: String?
    var rules: Rules?
    var posts: [Post] = []
    var media: [MediaItem] = []
    var channels: [Channel] = []
    var channelPlatforms: [String] = []
    var draft = Draft()
    var calendarFocus: Date?
    var isRefreshing = false
    var lastError: String?

    init() {
        serverURLString = UserDefaults.standard.string(forKey: "serverURL") ?? ""
        token = Keychain.read()
    }

    var isSignedIn: Bool { token != nil && client != nil }
    var dueCount: Int { posts.filter(\.isDue).count }

    var client: APIClient? {
        guard let url = Self.normalizedURL(serverURLString) else { return nil }
        return APIClient(baseURL: url, token: token)
    }

    static func normalizedURL(_ text: String) -> URL? {
        var value = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return nil }
        if !value.contains("://") { value = "http://" + value }
        while value.hasSuffix("/") { value.removeLast() }
        guard let url = URL(string: value), url.host != nil else { return nil }
        return url
    }

    // MARK: Session

    func signIn(server: String, passcode: String) async throws {
        guard let url = Self.normalizedURL(server) else {
            throw APIError(status: 0, message: "Enter the server address, for example http://192.168.1.20:4377")
        }
        let anonymous = APIClient(baseURL: url, token: nil)
        let _: Health = try await anonymous.send("GET", "/api/health")
        let login: LoginResponse = try await anonymous.send("POST", "/api/login", body: ["passcode": passcode])
        serverURLString = url.absoluteString
        UserDefaults.standard.set(serverURLString, forKey: "serverURL")
        Keychain.write(login.token)
        token = login.token
        await refresh()
    }

    func signOut() {
        Keychain.delete()
        token = nil
        posts = []
        media = []
        channels = []
        rules = nil
        draft = Draft()
        selectedTab = .compose
    }

    func handle(_ error: Error) {
        if let api = error as? APIError, api.status == 401 {
            signOut()
            lastError = "Your session ended. Please sign in again."
        } else {
            lastError = error.localizedDescription
        }
    }

    // MARK: Loading

    func refresh() async {
        guard let client else { return }
        isRefreshing = true
        defer { isRefreshing = false }
        do {
            async let rulesTask: Rules = client.send("GET", "/api/rules")
            async let postsTask: PostsResponse = client.send("GET", "/api/posts")
            async let mediaTask: MediaListResponse = client.send("GET", "/api/media")
            async let channelsTask: ChannelsResponse = client.send("GET", "/api/channels")
            let (loadedRules, loadedPosts, loadedMedia, loadedChannels) =
                try await (rulesTask, postsTask, mediaTask, channelsTask)
            rules = loadedRules
            posts = loadedPosts.posts
            media = loadedMedia.media
            channels = loadedChannels.channels
            channelPlatforms = loadedChannels.platforms
            lastError = nil
        } catch {
            handle(error)
        }
    }

    func refreshPosts() async throws {
        guard let client else { return }
        let response: PostsResponse = try await client.send("GET", "/api/posts")
        posts = response.posts
    }

    func refreshMedia() async throws {
        guard let client else { return }
        let response: MediaListResponse = try await client.send("GET", "/api/media")
        media = response.media
    }

    // MARK: Posts

    private func requireClient() throws -> APIClient {
        guard let client else { throw APIError(status: 401, message: "Please sign in.") }
        return client
    }

    func payload(for draft: Draft) -> [String: Any] {
        let order = rules?.platformOrder ?? Platform.allCases.map(\.rawValue)
        return [
            "content": draft.content,
            "link": draft.link,
            "hashtags": draft.hashtags,
            "platforms": order.filter { draft.platforms.contains($0) },
            "media_ids": draft.mediaIds,
        ]
    }

    func check(_ draft: Draft) async throws -> Check {
        let response: CheckResponse = try await requireClient().send("POST", "/api/check", body: payload(for: draft))
        return response.check
    }

    /// Creates or updates the post for the current draft and returns it.
    @discardableResult
    func save(_ draft: Draft) async throws -> Post {
        let client = try requireClient()
        let response: PostResponse
        if let id = draft.id {
            response = try await client.send("PUT", "/api/posts/\(id)", body: payload(for: draft))
        } else {
            response = try await client.send("POST", "/api/posts", body: payload(for: draft))
        }
        try await refreshPosts()
        return response.post
    }

    func schedule(postID: Int, at date: Date) async throws {
        let iso = ISO8601DateFormatter().string(from: date)
        let _: PostResponse = try await requireClient().send(
            "POST", "/api/posts/\(postID)/schedule", body: ["scheduled_at": iso]
        )
        try await refreshPosts()
    }

    func unschedule(_ post: Post) async throws {
        let _: PostResponse = try await requireClient().send("POST", "/api/posts/\(post.id)/unschedule")
        try await refreshPosts()
    }

    func markPosted(_ post: Post) async throws {
        let _: PostResponse = try await requireClient().send("POST", "/api/posts/\(post.id)/mark-posted")
        try await refreshPosts()
    }

    func duplicate(_ post: Post) async throws -> Post {
        let response: PostResponse = try await requireClient().send("POST", "/api/posts/\(post.id)/duplicate")
        try await refreshPosts()
        return response.post
    }

    func delete(_ post: Post) async throws {
        let _: OK = try await requireClient().send("DELETE", "/api/posts/\(post.id)")
        try await refreshPosts()
    }

    func edit(_ post: Post) {
        draft = Draft(post: post)
        selectedTab = .compose
    }

    func startNewPost(on day: Date? = nil) {
        var fresh = Draft()
        if let day {
            let calendar = Calendar.current
            if let nine = calendar.date(bySettingHour: 9, minute: 0, second: 0, of: day), nine > Date() {
                fresh.when = nine
            }
        }
        draft = fresh
        selectedTab = .compose
    }

    // MARK: Social pages

    func refreshChannels() async throws {
        guard let client else { return }
        let response: ChannelsResponse = try await client.send("GET", "/api/channels")
        channels = response.channels
        channelPlatforms = response.platforms
    }

    func saveChannel(id: Int?, platform: String, name: String, url: String, notes: String) async throws {
        let client = try requireClient()
        let body: [String: Any] = [
            "platform": platform,
            "name": name.trimmingCharacters(in: .whitespaces),
            "url": url.trimmingCharacters(in: .whitespaces),
            "notes": notes,
        ]
        if let id {
            let _: ChannelResponse = try await client.send("PUT", "/api/channels/\(id)", body: body)
        } else {
            let _: ChannelResponse = try await client.send("POST", "/api/channels", body: body)
        }
        try await refreshChannels()
    }

    func deleteChannel(_ channel: Channel) async throws {
        let _: OK = try await requireClient().send("DELETE", "/api/channels/\(channel.id)")
        try await refreshChannels()
    }

    /// Where each of a post's platforms opens. LinkedIn and X accept pre-filled text;
    /// Facebook and Instagram open the page, so the text is copied for pasting.
    func publishTargets(for post: Post) -> [PublishTarget] {
        post.platforms.compactMap { id in
            guard let platform = Platform(rawValue: id) else { return nil }
            let page = channels.first { $0.platform == id }.flatMap { URL(string: $0.url) }

            func prefilled(_ base: String, key: String) -> URL? {
                var components = URLComponents(string: base)
                var items = components?.queryItems ?? []
                items.append(URLQueryItem(name: key, value: post.shareText))
                components?.queryItems = items
                return components?.url
            }

            switch platform {
            case .linkedin:
                return PublishTarget(
                    platform: id,
                    label: "Post to LinkedIn",
                    url: prefilled("https://www.linkedin.com/feed/?shareActive=true", key: "text"),
                    hint: "Text is copied and LinkedIn opens with it filled in. To post as the company page, switch to it first."
                )
            case .twitter:
                return PublishTarget(
                    platform: id,
                    label: "Post to X",
                    url: prefilled("https://x.com/intent/post", key: "text"),
                    hint: "Text is copied and X opens with it filled in."
                )
            case .facebook:
                return PublishTarget(
                    platform: id,
                    label: "Post to Facebook",
                    url: page,
                    hint: page == nil
                        ? "Add the Facebook page under Social pages first."
                        : "Text is copied. On the page, choose Create post and paste."
                )
            case .instagram:
                return PublishTarget(
                    platform: id,
                    label: "Post to Instagram",
                    url: page,
                    hint: page == nil
                        ? "Add the Instagram page under Social pages first."
                        : "Text is copied. In Instagram, add the photo and paste."
                )
            }
        }
    }

    // MARK: Photos

    func mediaURL(_ item: MediaItem) -> URL? {
        client?.mediaURL(item)
    }

    func updateMedia(_ item: MediaItem, caption: String, project: String) async throws {
        let _: MediaResponse = try await requireClient().send(
            "PATCH", "/api/media/\(item.id)", body: ["caption": caption, "project": project]
        )
        try await refreshMedia()
    }

    func deleteMedia(_ item: MediaItem) async throws {
        let _: OK = try await requireClient().send("DELETE", "/api/media/\(item.id)")
        try await refreshMedia()
    }

    /// Uploads one item chosen in the system photo picker. HEIC photos are converted to JPEG
    /// first because most social platforms do not accept HEIC.
    func upload(_ item: PhotosPickerItem, project: String, caption: String) async throws -> MediaItem {
        let client = try requireClient()
        let stamp = Int(Date().timeIntervalSince1970)

        if item.supportedContentTypes.contains(where: { $0.conforms(to: .movie) }) {
            guard let movie = try await item.loadTransferable(type: MovieFile.self) else {
                throw APIError(status: 0, message: "That video could not be read.")
            }
            defer { try? FileManager.default.removeItem(at: movie.url) }
            let isMP4 = movie.url.pathExtension.lowercased() == "mp4"
            let uploaded = try await client.upload(
                fileURL: movie.url,
                mime: isMP4 ? "video/mp4" : "video/quicktime",
                filename: "video-\(stamp).\(isMP4 ? "mp4" : "mov")",
                project: project,
                caption: caption
            )
            try await refreshMedia()
            return uploaded
        }

        guard let data = try await item.loadTransferable(type: Data.self) else {
            throw APIError(status: 0, message: "That photo could not be read.")
        }
        var payload = data
        var kind = Self.sniffImage(data)
        if kind == nil || kind?.mime == "image/heic" {
            guard let image = UIImage(data: data), let jpeg = image.jpegData(compressionQuality: 0.9) else {
                throw APIError(status: 0, message: "That photo format is not supported.")
            }
            payload = jpeg
            kind = (mime: "image/jpeg", ext: "jpg")
        }
        guard let kind else { throw APIError(status: 0, message: "That photo format is not supported.") }
        let uploaded = try await client.upload(
            data: payload,
            mime: kind.mime,
            filename: "photo-\(stamp).\(kind.ext)",
            project: project,
            caption: caption
        )
        try await refreshMedia()
        return uploaded
    }

    static func sniffImage(_ data: Data) -> (mime: String, ext: String)? {
        let bytes = [UInt8](data.prefix(16))
        if bytes.count >= 3, bytes[0] == 0xFF, bytes[1] == 0xD8, bytes[2] == 0xFF { return ("image/jpeg", "jpg") }
        if bytes.count >= 4, bytes[0] == 0x89, bytes[1] == 0x50, bytes[2] == 0x4E, bytes[3] == 0x47 { return ("image/png", "png") }
        if bytes.count >= 4, bytes[0] == 0x47, bytes[1] == 0x49, bytes[2] == 0x46, bytes[3] == 0x38 { return ("image/gif", "gif") }
        if bytes.count >= 12, String(bytes: bytes[0..<4], encoding: .ascii) == "RIFF",
           String(bytes: bytes[8..<12], encoding: .ascii) == "WEBP" { return ("image/webp", "webp") }
        if bytes.count >= 12, String(bytes: bytes[4..<8], encoding: .ascii) == "ftyp" { return ("image/heic", "heic") }
        return nil
    }
}
