/** Shared contracts returned by the API gateway. Mirror the backend schemas. */

export type OrganizationRole = "owner" | "admin" | "member";

export interface Account {
  id: string;
  email: string;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface Organization {
  id: string;
  name: string;
  role: OrganizationRole;
  created_at: string;
}
