import type { FC } from "react";

/** Монохромный векторный логотип проекта (адаптируется под текущую тему через currentColor). */
export const Logo: FC<{ size?: number }> = ({ size }) => (
  <svg
    className="brand-logo"
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    aria-hidden="true"
  >
    <rect
      x="2"
      y="2"
      width="20"
      height="20"
      rx="5"
      stroke="currentColor"
      strokeWidth="1.6"
    />
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
