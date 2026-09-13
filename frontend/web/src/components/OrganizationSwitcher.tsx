import type { Organization } from "../api/types";

const ROLE_LABELS: Record<Organization["role"], string> = {
  owner: "Owner",
  admin: "Admin",
  member: "Member",
};

/** Header control listing the account's organizations and its role in the active one. */
export function OrganizationSwitcher({
  organizations,
  activeId,
  onSelect,
}: {
  organizations: Organization[];
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  if (organizations.length === 0) {
    return null;
  }
  const active =
    organizations.find((item) => item.id === activeId) ?? organizations[0];

  return (
    <div className="organization-switcher">
      <svg
        className="organization-switcher__icon"
        viewBox="0 0 20 20"
        fill="none"
        aria-hidden="true"
      >
        <path
          d="M3.5 17V4.6L10 2.8v14.2M10 17h6.5V7.6L10 6"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
        <path
          d="M6 6.6h1.6M6 9.4h1.6M6 12.2h1.6M12.6 9.4h1.6M12.6 12.2h1.6"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </svg>
      <span className="organization-switcher__text">
        <span className="organization-switcher__name">{active.name}</span>
        <span className="organization-switcher__role">
          {ROLE_LABELS[active.role]}
        </span>
      </span>
      <select
        className="organization-switcher__select"
        aria-label="Organization"
        value={active.id}
        onChange={(event) => onSelect(event.target.value)}
      >
        {organizations.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name} · {ROLE_LABELS[item.role]}
          </option>
        ))}
      </select>
    </div>
  );
}
