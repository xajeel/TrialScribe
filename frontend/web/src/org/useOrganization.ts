import { useContext } from "react";

import {
  OrganizationContext,
  type OrganizationContextValue,
} from "./OrganizationContext";

/** Access organization context; throws when used outside its provider. */
export function useOrganization(): OrganizationContextValue {
  const value = useContext(OrganizationContext);
  if (value === null) {
    throw new Error(
      "useOrganization must be used within an OrganizationProvider",
    );
  }
  return value;
}
