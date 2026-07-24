import type { AuthorizedFetch } from "../auth/AuthContext";
import type { Organization } from "./types";

/** List the organizations the current account belongs to. */
export function listOrganizations(
  fetcher: AuthorizedFetch,
): Promise<Organization[]> {
  return fetcher<Organization[]>("/v1/organizations");
}
