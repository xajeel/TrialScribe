import type { AuthorizedFetch } from "../auth/AuthContext";
import type {
  Organization,
  OrganizationMembership,
  OrganizationRole,
} from "./types";

/** List the organizations the current account belongs to. */
export function listOrganizations(
  fetcher: AuthorizedFetch,
): Promise<Organization[]> {
  return fetcher<Organization[]>("/v1/organizations");
}

/** Create an organization owned by the current account. */
export function createOrganization(
  fetcher: AuthorizedFetch,
  name: string,
): Promise<Organization> {
  return fetcher<Organization>("/v1/organizations", {
    method: "POST",
    json: { name },
  });
}

/** List privacy-safe membership records visible to any organization member. */
export function listOrganizationMembers(
  fetcher: AuthorizedFetch,
  organizationId: string,
): Promise<OrganizationMembership[]> {
  return fetcher<OrganizationMembership[]>(
    `/v1/organizations/${organizationId}/members`,
  );
}

/** Change one member's role. Backend authorization remains authoritative. */
export function changeOrganizationMemberRole(
  fetcher: AuthorizedFetch,
  organizationId: string,
  accountId: string,
  role: OrganizationRole,
): Promise<OrganizationMembership> {
  return fetcher<OrganizationMembership>(
    `/v1/organizations/${organizationId}/members/${accountId}`,
    { method: "PATCH", json: { role } },
  );
}

/** Remove one membership. Callers must confirm this destructive action. */
export function removeOrganizationMember(
  fetcher: AuthorizedFetch,
  organizationId: string,
  accountId: string,
): Promise<void> {
  return fetcher<void>(
    `/v1/organizations/${organizationId}/members/${accountId}`,
    { method: "DELETE" },
  );
}
