import type { FC } from "react";

/** Фирменный векторный логотип в стиле Keitaro (адаптируется под тему через CSS-токены). */
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
      x="1.5"
      y="1.5"
      width="21"
      height="21"
      rx="5.5"
      fill="var(--accent-soft)"
      stroke="var(--accent-line)"
      strokeWidth="1.5"
    />
    <path
      d="M7.25 6.5v11M7.25 12h2.25l6.75-5.25M9.5 12l6.75 5.25"
      stroke="var(--accent)"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <circle cx="16.5" cy="6.75" r="1.45" fill="var(--accent)" />
    <circle cx="16.5" cy="17.25" r="1.45" fill="var(--accent)" />
  </svg>
);
