import type { FC } from "react";

/** Векторный логотип проекта без рамки, окрашивается через currentColor (--brand-green). */
export const Logo: FC<{ size?: number }> = ({ size }) => (
  <svg
    className="brand-logo"
    width={size}
    height={size}
    viewBox="4 4 16 16"
    fill="none"
    aria-hidden="true"
  >
    <path
      d="M6.5 12h4l3-4.5h4M10.5 12l3 4.5h4"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <circle cx="17.5" cy="7.5" r="1.4" fill="currentColor" />
    <circle cx="17.5" cy="16.5" r="1.4" fill="currentColor" />
  </svg>
);
