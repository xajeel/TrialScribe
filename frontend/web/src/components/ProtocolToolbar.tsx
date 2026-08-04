import type { LibraryScope, LibrarySort } from "../workspace/useProtocolLibrary";

const SCOPES: { value: LibraryScope; label: string }[] = [
  { value: "active", label: "Active" },
  { value: "archived", label: "Archived" },
];

/** Search, status filter, and sort controls above the protocol list. */
export function ProtocolToolbar({
  search,
  scope,
  sort,
  onSearch,
  onScope,
  onSort,
}: {
  search: string;
  scope: LibraryScope;
  sort: LibrarySort;
  onSearch: (value: string) => void;
  onScope: (value: LibraryScope) => void;
  onSort: (value: LibrarySort) => void;
}) {
  return (
    <div className="protocol-toolbar">
      <div className="protocol-toolbar__search">
        <label htmlFor="protocol-search">Search protocols</label>
        <div className="protocol-toolbar__search-field">
          <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <circle cx="9" cy="9" r="5.4" stroke="currentColor" strokeWidth="1.5" />
            <path
              d="m13.2 13.2 3.3 3.3"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
          <input
            id="protocol-search"
            type="search"
            value={search}
            placeholder="Search by protocol title"
            onChange={(event) => onSearch(event.target.value)}
          />
        </div>
      </div>

      <div
        className="protocol-toolbar__filter"
        role="group"
        aria-label="Protocol status"
      >
        {SCOPES.map((item) => (
          <button
            key={item.value}
            type="button"
            aria-pressed={scope === item.value}
            onClick={() => onScope(item.value)}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="protocol-toolbar__sort">
        <label htmlFor="protocol-sort">Sort by</label>
        <select
          id="protocol-sort"
          value={sort}
          onChange={(event) => onSort(event.target.value as LibrarySort)}
        >
          <option value="activity">Recent activity</option>
          <option value="title">Title A–Z</option>
        </select>
      </div>
    </div>
  );
}
