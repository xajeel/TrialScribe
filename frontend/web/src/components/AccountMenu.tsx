import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../auth/useAuth";

/** Two-letter avatar initials from the email's local part. */
export function initialsOf(email: string): string {
  return email.slice(0, 2).toUpperCase();
}

/** Header avatar button opening the account popover: profile link + log out. */
export function AccountMenu() {
  const { account, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onPointerDown = (event: PointerEvent) => {
      if (
        rootRef.current !== null &&
        !rootRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const email = account?.email ?? "";

  return (
    <div className="account-menu" ref={rootRef}>
      <button
        type="button"
        className="avatar account-menu__trigger"
        aria-label="Account menu"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {initialsOf(email)}
      </button>
      {open && (
        <div className="account-menu__popover">
          <p className="account-menu__email">{email}</p>
          <Link
            className="account-menu__item"
            to="/profile"
            onClick={() => setOpen(false)}
          >
            Profile and settings
          </Link>
          <Link
            className="account-menu__item"
            to="/organization/members"
            onClick={() => setOpen(false)}
          >
            Organization access
          </Link>
          <button
            type="button"
            className="account-menu__item account-menu__item--danger"
            onClick={() => void signOut()}
          >
            Log out
          </button>
        </div>
      )}
    </div>
  );
}
