import type { AuthorizedFetch } from "../auth/AuthContext";
import type {
  CreatedOrganizationInvitation,
  InvitationRole,
  OrganizationMembership,
} from "./types";

/** Create a single-use invitation for an organization. */
export function createOrganizationInvitation(
  fetcher: AuthorizedFetch,
  organizationId: string,
  email: string,
  role: InvitationRole,
): Promise<CreatedOrganizationInvitation> {
  return fetcher<CreatedOrganizationInvitation>(
    `/v1/organizations/${organizationId}/invitations`,
    {
      method: "POST",
      json: { email, role },
    },
  );
}

/** Accept an invitation and return the resulting membership. */
export function acceptOrganizationInvitation(
  fetcher: AuthorizedFetch,
  token: string,
): Promise<OrganizationMembership> {
  return fetcher<OrganizationMembership>(
    "/v1/organization-invitations/accept",
    {
      method: "POST",
      json: { token },
    },
  );
}

/** Read a raw token or the token query parameter from an invitation URL. */
export function extractInvitationToken(value: string): string | null {
  const normalized = value.trim();
  if (normalized === "") {
    return null;
  }
  if (!normalized.includes("?") && !/^https?:\/\//i.test(normalized)) {
    return normalized.length <= 512 ? normalized : null;
  }
  try {
    const token = new URL(normalized, window.location.origin).searchParams
      .get("token")
      ?.trim();
    return token !== undefined && token !== "" && token.length <= 512
      ? token
      : null;
  } catch {
    return null;
  }
}
