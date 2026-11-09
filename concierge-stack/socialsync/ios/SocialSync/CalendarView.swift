import SwiftUI

struct CalendarView: View {
    @Environment(AppStore.self) private var store
    @State private var month = Date()
    @State private var selected = Date()

    private var calendar: Calendar {
        var calendar = Calendar.current
        calendar.firstWeekday = 2 // weeks start on Monday in New Zealand
        return calendar
    }

    private var days: [Date?] {
        guard let start = calendar.date(from: calendar.dateComponents([.year, .month], from: month)),
              let count = calendar.range(of: .day, in: .month, for: start)?.count else { return [] }
        let weekday = calendar.component(.weekday, from: start)
        let blanks = (weekday - calendar.firstWeekday + 7) % 7
        let dates: [Date?] = (0..<count).map { calendar.date(byAdding: .day, value: $0, to: start) }
        return [Date?](repeating: nil, count: blanks) + dates
    }

    private func posts(on day: Date) -> [Post] {
        store.posts
            .filter { post in
                guard let date = post.calendarDate else { return false }
                return calendar.isDate(date, inSameDayAs: day)
            }
            .sorted { ($0.calendarDate ?? .distantPast) < ($1.calendarDate ?? .distantPast) }
    }

    private var dueNow: [Post] { store.posts.filter(\.isDue) }
    private var drafts: [Post] { store.posts.filter { $0.status == .draft } }

    var body: some View {
        NavigationStack {
            List {
                if !dueNow.isEmpty {
                    Section {
                        ForEach(dueNow) { post in
                            NavigationLink(value: post.id) { PostRow(post: post) }
                        }
                    } header: {
                        Label("Due now (\(dueNow.count))", systemImage: "bell.badge.fill")
                            .foregroundStyle(.orange)
                    } footer: {
                        Text("These were scheduled for a time that has passed. Post them, then mark them as posted.")
                    }
                }

                Section {
                    monthHeader
                    weekdayHeader
                    grid
                }
                .listRowInsets(EdgeInsets(top: 8, leading: 12, bottom: 8, trailing: 12))

                Section {
                    let dayPosts = posts(on: selected)
                    if dayPosts.isEmpty {
                        Text("Nothing planned for this day.").foregroundStyle(.secondary)
                    }
                    ForEach(dayPosts) { post in
                        NavigationLink(value: post.id) { PostRow(post: post) }
                    }
                    Button {
                        store.startNewPost(on: selected)
                    } label: {
                        Label("New post on this day", systemImage: "plus")
                    }
                } header: {
                    Text(selected.formatted(.dateTime.weekday(.wide).day().month(.wide)))
                }

                if !drafts.isEmpty {
                    Section("Unscheduled drafts") {
                        ForEach(drafts) { post in
                            Button { store.edit(post) } label: {
                                Text(post.content.isEmpty ? "(no text)" : post.content).lineLimit(2)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
            .navigationTitle("Calendar")
            .navigationDestination(for: Int.self) { id in PostDetailView(postID: id) }
            .refreshable { await store.refresh() }
            .onAppear(perform: applyFocus)
            .onChange(of: store.calendarFocus) { _, _ in applyFocus() }
        }
    }

    private func applyFocus() {
        guard let focus = store.calendarFocus else { return }
        month = focus
        selected = focus
        store.calendarFocus = nil
    }

    private var monthHeader: some View {
        HStack {
            Button { shift(-1) } label: { Image(systemName: "chevron.left") }
                .buttonStyle(.borderless)
                .accessibilityLabel("Previous month")
            Spacer()
            Text(month.formatted(.dateTime.month(.wide).year())).font(.headline)
            Spacer()
            Button { shift(1) } label: { Image(systemName: "chevron.right") }
                .buttonStyle(.borderless)
                .accessibilityLabel("Next month")
        }
    }

    private func shift(_ delta: Int) {
        if let next = calendar.date(byAdding: .month, value: delta, to: month) {
            month = next
        }
    }

    private var weekdayHeader: some View {
        HStack(spacing: 0) {
            ForEach(Array(["M", "T", "W", "T", "F", "S", "S"].enumerated()), id: \.offset) { _, symbol in
                Text(symbol)
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity)
            }
        }
    }

    private var grid: some View {
        let columns = Array(repeating: GridItem(.flexible(), spacing: 2), count: 7)
        return LazyVGrid(columns: columns, spacing: 2) {
            ForEach(Array(days.enumerated()), id: \.offset) { _, day in
                if let day {
                    dayCell(day)
                } else {
                    Color.clear.frame(height: 46)
                }
            }
        }
    }

    private func dayCell(_ day: Date) -> some View {
        let isSelected = calendar.isDate(day, inSameDayAs: selected)
        let isToday = calendar.isDateInToday(day)
        let dayPosts = posts(on: day)
        return Button {
            selected = day
        } label: {
            VStack(spacing: 3) {
                Text("\(calendar.component(.day, from: day))")
                    .font(.callout)
                    .fontWeight(isToday ? .bold : .regular)
                    .foregroundStyle(isSelected ? Color.white : (isToday ? Color.accentColor : Color.primary))
                HStack(spacing: 2) {
                    ForEach(Array(dayPosts.prefix(3).enumerated()), id: \.offset) { _, post in
                        Circle()
                            .fill(dotColor(post, onSelected: isSelected))
                            .frame(width: 5, height: 5)
                    }
                }
                .frame(height: 5)
            }
            .frame(maxWidth: .infinity, minHeight: 46)
            .background(isSelected ? Color.accentColor : Color.clear, in: RoundedRectangle(cornerRadius: 10))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(day.formatted(.dateTime.weekday(.wide).day().month(.wide)))
        .accessibilityValue(dayPosts.isEmpty ? "No posts" : "\(dayPosts.count) posts")
    }

    private func dotColor(_ post: Post, onSelected: Bool) -> Color {
        if onSelected { return .white }
        if post.isDue { return .orange }
        switch post.status {
        case .draft: return .blue
        case .scheduled: return .green
        case .posted: return .gray
        }
    }
}
