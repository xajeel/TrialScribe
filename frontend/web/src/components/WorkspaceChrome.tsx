import { Link } from "react-router-dom";

import type { Organization } from "../api/types";
import { AccountMenu } from "./AccountMenu";
import { BrandLogo } from "./BrandLogo";

export type WorkspaceTab =
  | "instructions"
  | "progress"
  | "sources"
  | "workspace"
  | "revisions"
  | "readiness";

const TABS: { key: WorkspaceTab; label: string; suffix: string }[] = [
  { key: "instructions", label: "Instructions", suffix: "/instructions" },
  { key: "progress", label: "Progress", suffix: "/progress" },
  { key: "sources", label: "Sources", suffix: "/sources" },
  { key: "workspace", label: "Workspace", suffix: "" },
  { key: "revisions", label: "Revisions", suffix: "/revisions" },
  { key: "readiness", label: "Readiness", suffix: "/readiness" },
];

/** Page-scoped header and tab bar shared by the instruction and progress pages. */
export function WorkspaceChrome({
  conversationId,
  protocolTitle,
  organization,
  current,
  reviewing = false,
}: {
  conversationId: string;
  protocolTitle: string;
  organization: Organization | null;
  current: WorkspaceTab;
  reviewing?: boolean;
}) {
  const base = `/workspace/${encodeURIComponent(conversationId)}`;

  return (
    <header className="protocol-workspace__header">
      <div className="protocol-workspace__header-inner">
        <div className="protocol-workspace__identity">
          <BrandLogo
            className="protocol-workspace__brand"
            to="/protocols"
            ariaLabel="TrialScribe protocols"
          />
          <span className="protocol-workspace__divider" aria-hidden="true" />
          <div className="protocol-workspace__titles">
            <p className="protocol-workspace__eyebrow">
              {organization?.name ?? ""}
            </p>
            <p className="protocol-workspace__protocol">{protocolTitle}</p>
          </div>
        </div>
        <div className="protocol-workspace__header-actions">
          <Link
            className="protocol-workspace__utility"
            to={`${base}/export`}
          >
            Export
          </Link>
          <Link
            className="protocol-workspace__utility"
            to={`${base}/usage`}
          >
            Usage
          </Link>
          <Link className="protocol-workspace__back" to="/protocols">
            Back to protocols
          </Link>
          {reviewing ? (
            <span className="avatar" aria-label="Review account MC">
              MC
            </span>
          ) : (
            <AccountMenu />
          )}
        </div>
      </div>

      <nav className="protocol-workspace__tabs" aria-label="Protocol views">
        <ul>
          {TABS.map((tab) => (
            <li key={tab.key}>
              <Link
                to={`${base}${tab.suffix}`}
                aria-current={tab.key === current ? "page" : undefined}
                className={
                  tab.key === current
                    ? "protocol-workspace__tab protocol-workspace__tab--current"
                    : "protocol-workspace__tab"
                }
              >
                {tab.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
}
