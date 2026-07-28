import type { AuthorizedFetch } from "../auth/AuthContext";
import type { Organization } from "./types";

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
