import SwiftUI

struct RootView: View {
    @Environment(AppStore.self) private var store
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        Group {
            if store.isSignedIn {
                MainTabView()
            } else {
                SignInView()
            }
        }
        .task {
            if store.isSignedIn { await store.refresh() }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active, store.isSignedIn {
                Task { await store.refresh() }
            }
        }
        .alert(
            "SocialSync",
            isPresented: Binding(
                get: { store.lastError != nil },
                set: { if !$0 { store.lastError = nil } }
            )
        ) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(store.lastError ?? "")
        }
    }
}

struct MainTabView: View {
    @Environment(AppStore.self) private var store

    var body: some View {
        @Bindable var store = store
        TabView(selection: $store.selectedTab) {
            ComposeView()
                .tabItem { Label("Compose", systemImage: "square.and.pencil") }
                .tag(AppStore.Tab.compose)

            CalendarView()
                .tabItem { Label("Calendar", systemImage: "calendar") }
                .tag(AppStore.Tab.calendar)

            PostsView()
                .tabItem { Label("Posts", systemImage: "list.bullet.rectangle") }
                .badge(store.dueCount)
                .tag(AppStore.Tab.posts)

            PhotosView()
                .tabItem { Label("Photos", systemImage: "photo.on.rectangle") }
                .tag(AppStore.Tab.photos)

            SettingsView()
                .tabItem { Label("Settings", systemImage: "gearshape") }
                .tag(AppStore.Tab.settings)
        }
    }
}

struct SignInView: View {
    @Environment(AppStore.self) private var store
    @State private var server = ""
    @State private var passcode = ""
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Image("PukekoLogo")
                        .resizable()
                        .scaledToFit()
                        .frame(maxHeight: 64)
                        .frame(maxWidth: .infinity)
                        .listRowBackground(Color.clear)
                        .accessibilityLabel("Pukeko Construction")
                }

                Section {
                    TextField("http://192.168.1.20:4377", text: $server)
                        .keyboardType(.URL)
                        .textContentType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    SecureField("Passcode", text: $passcode)
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                } header: {
                    Text("Server")
                } footer: {
                    Text("The SocialSync server prints its address and passcode when it starts. Your phone must be on the same network as the computer running it.")
                }

                if let error {
                    Section { Text(error).foregroundStyle(.red) }
                }

                Section {
                    Button {
                        Task { await signIn() }
                    } label: {
                        HStack {
                            Text("Sign in").bold()
                            if busy { ProgressView() }
                        }
                    }
                    .disabled(busy || server.trimmingCharacters(in: .whitespaces).isEmpty || passcode.isEmpty)
                }
            }
            .navigationTitle("SocialSync")
            .onAppear {
                if server.isEmpty { server = store.serverURLString }
            }
        }
    }

    private func signIn() async {
        busy = true
        error = nil
        defer { busy = false }
        do {
            try await store.signIn(server: server, passcode: passcode.trimmingCharacters(in: .whitespaces))
        } catch {
            self.error = error.localizedDescription
        }
    }
}

struct SettingsView: View {
    @Environment(AppStore.self) private var store

    private var version: String {
        let info = Bundle.main.infoDictionary
        let short = info?["CFBundleShortVersionString"] as? String ?? "1.0"
        let build = info?["CFBundleVersion"] as? String ?? "1"
        return "\(short) (\(build))"
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    NavigationLink {
                        SocialPagesView()
                    } label: {
                        Label("Social pages", systemImage: "link")
                    }
                } footer: {
                    Text("Facebook, Instagram, LinkedIn and every other page Pukeko uses, in one list.")
                }

                Section("Server") {
                    LabeledContent("Address", value: store.serverURLString)
                    Button {
                        Task { await store.refresh() }
                    } label: {
                        HStack {
                            Text("Refresh now")
                            if store.isRefreshing { ProgressView() }
                        }
                    }
                }

                Section {
                    Button("Sign out", role: .destructive) { store.signOut() }
                } footer: {
                    Text("To use a different server, sign out and sign in again with the new address.")
                }

                Section("About") {
                    LabeledContent("Version", value: version)
                    Text("SocialSync plans and schedules posts for Pukeko Construction. It does not publish by itself: when a post is due, copy it into the platform and mark it as posted.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Settings")
        }
    }
}
