import type { ReactElement, ReactNode } from "react";
import { Link } from "react-router-dom";

interface BrandLogoProps {
  ariaLabel?: string;
  className?: string;
  to?: string;
}

function BrandLogoContent(): ReactNode {
  return (
    <>
      <svg
        className="brand-logo__mark"
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden="true"
        focusable="false"
      >
        <path
          d="M6 2.75h8.35L19 7.4v13.85H6z"
          fill="currentColor"
          stroke="none"
        />
        <path
          d="M14.35 2.75V7.4H19M9 11.25h7M9 14.25h7M9 17.25h5"
          stroke="#fcfbf7"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="brand-logo__text">TrialScribe</span>
    </>
  );
}

export function BrandLogo({
  ariaLabel = "TrialScribe home",
  className,
  to,
}: BrandLogoProps): ReactElement {
  const classes =
    className === undefined ? "brand-logo" : `brand-logo ${className}`;

  if (to !== undefined) {
    return (
      <Link className={classes} to={to} aria-label={ariaLabel}>
        <BrandLogoContent />
      </Link>
    );
  }

  return (
    <span className={classes} aria-label={ariaLabel}>
      <BrandLogoContent />
    </span>
  );
}
