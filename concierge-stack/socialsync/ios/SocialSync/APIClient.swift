import Foundation

struct APIError: LocalizedError {
    var status: Int
    var message: String
    var problems: [String] = []

    var errorDescription: String? {
        problems.isEmpty ? message : "\(message) \(problems.joined(separator: " "))"
    }

    static func from(data: Data, status: Int) -> APIError {
        struct Body: Decodable {
            var error: String?
            var problems: [String]?
        }
        let body = try? JSONDecoder().decode(Body.self, from: data)
        return APIError(
            status: status,
            message: body?.error ?? "The server returned an error (\(status)).",
            problems: body?.problems ?? []
        )
    }
}

/// Talks to the SocialSync server. A value type: make a new one when the address or token changes.
struct APIClient {
    let baseURL: URL
    var token: String?

    static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let text = try container.decode(String.self)
            let withFraction = ISO8601DateFormatter()
            withFraction.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = withFraction.date(from: text) { return date }
            let plain = ISO8601DateFormatter()
            plain.formatOptions = [.withInternetDateTime]
            if let date = plain.date(from: text) { return date }
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Bad date: \(text)")
        }
        return decoder
    }()

    private func makeRequest(_ method: String, _ path: String, query: [URLQueryItem] = []) throws -> URLRequest {
        guard var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) else {
            throw APIError(status: 0, message: "The server address is not valid.")
        }
        var basePath = components.path
        while basePath.hasSuffix("/") { basePath.removeLast() }
        components.path = basePath + path
        components.queryItems = query.isEmpty ? nil : query
        guard let url = components.url else {
            throw APIError(status: 0, message: "The server address is not valid.")
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 30
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        return request
    }

    private func decode<T: Decodable>(_ data: Data, _ response: URLResponse) throws -> T {
        guard let http = response as? HTTPURLResponse else {
            throw APIError(status: 0, message: "No response from the server.")
        }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.from(data: data, status: http.statusCode)
        }
        do {
            return try Self.decoder.decode(T.self, from: data)
        } catch {
            throw APIError(status: http.statusCode, message: "The server sent something unexpected.")
        }
    }

    private func translate(_ error: Error) -> Error {
        if let urlError = error as? URLError {
            switch urlError.code {
            case .notConnectedToInternet, .networkConnectionLost:
                return APIError(status: 0, message: "No network connection.")
            case .cannotConnectToHost, .cannotFindHost, .timedOut, .dnsLookupFailed:
                return APIError(
                    status: 0,
                    message: "Cannot reach the SocialSync server. Check the address and that the server is running."
                )
            default:
                break
            }
        }
        return error
    }

    func send<T: Decodable>(
        _ method: String,
        _ path: String,
        body: [String: Any]? = nil,
        query: [URLQueryItem] = []
    ) async throws -> T {
        var request = try makeRequest(method, path, query: query)
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            return try decode(data, response)
        } catch {
            throw translate(error)
        }
    }

    private func uploadQuery(filename: String, project: String, caption: String) -> [URLQueryItem] {
        [
            URLQueryItem(name: "filename", value: filename),
            URLQueryItem(name: "project", value: project),
            URLQueryItem(name: "caption", value: caption),
        ]
    }

    func upload(data: Data, mime: String, filename: String, project: String, caption: String) async throws -> MediaItem {
        var request = try makeRequest("POST", "/api/media", query: uploadQuery(filename: filename, project: project, caption: caption))
        request.setValue(mime, forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 300
        do {
            let (body, response) = try await URLSession.shared.upload(for: request, from: data)
            let result: MediaResponse = try decode(body, response)
            return result.media
        } catch {
            throw translate(error)
        }
    }

    func upload(fileURL: URL, mime: String, filename: String, project: String, caption: String) async throws -> MediaItem {
        var request = try makeRequest("POST", "/api/media", query: uploadQuery(filename: filename, project: project, caption: caption))
        request.setValue(mime, forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 600
        do {
            let (body, response) = try await URLSession.shared.upload(for: request, fromFile: fileURL)
            let result: MediaResponse = try decode(body, response)
            return result.media
        } catch {
            throw translate(error)
        }
    }

    /// URL for showing a photo. AsyncImage cannot send headers, so the token rides in the query.
    func mediaURL(_ item: MediaItem) -> URL? {
        guard var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) else { return nil }
        var basePath = components.path
        while basePath.hasSuffix("/") { basePath.removeLast() }
        components.path = basePath + "/media/\(item.id)"
        if let token { components.queryItems = [URLQueryItem(name: "token", value: token)] }
        return components.url
    }
}
