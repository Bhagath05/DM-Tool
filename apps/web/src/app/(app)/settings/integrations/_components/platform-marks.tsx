export function MarkInstagram() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden>
      <defs>
        <linearGradient id="m-ig" x1="0" x2="1" y1="1" y2="0">
          <stop offset="0" stopColor="#F58529" />
          <stop offset="0.5" stopColor="#DD2A7B" />
          <stop offset="1" stopColor="#8134AF" />
        </linearGradient>
      </defs>
      <rect x="3" y="3" width="18" height="18" rx="5" fill="none" stroke="url(#m-ig)" strokeWidth="2" />
      <circle cx="12" cy="12" r="4" fill="none" stroke="url(#m-ig)" strokeWidth="2" />
      <circle cx="17.2" cy="6.8" r="1.2" fill="url(#m-ig)" />
    </svg>
  );
}

export function MarkFacebook() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden>
      <circle cx="12" cy="12" r="9" fill="#1877F2" />
      <path
        d="M13.5 8.5h2V6h-2c-2.2 0-3.5 1.3-3.5 3.5V12H8v2.5h2V18h2.5v-3.5H15V12h-2.5V9.5c0-.8.5-1 1-1z"
        fill="white"
      />
    </svg>
  );
}

export function MarkLinkedIn() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden>
      <rect x="3" y="3" width="18" height="18" rx="3" fill="#0A66C2" />
      <rect x="6.5" y="9" width="2.5" height="9" fill="white" />
      <circle cx="7.75" cy="6.75" r="1.5" fill="white" />
      <path
        d="M11 9h2.4v1.3c.5-.9 1.6-1.5 2.8-1.5 2 0 2.8 1.4 2.8 3.3V18h-2.5v-5c0-1.1-.5-1.7-1.4-1.7s-1.6.7-1.6 1.8V18H11z"
        fill="white"
      />
    </svg>
  );
}

export function MarkYouTube() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden>
      <rect x="2" y="6" width="20" height="12" rx="3" fill="#FF0000" />
      <path d="M10 9.5v5l5-2.5-5-2.5z" fill="white" />
    </svg>
  );
}

export function MarkPinterest() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden>
      <circle cx="12" cy="12" r="9" fill="#E60023" />
      <path
        d="M12 6.5c-2.5 0-4.5 1.8-4.5 4.2 0 1.6.9 3 2.2 3.6-.1-.7-.2-1.8.1-2.7.2-.7 1.3-4.6 1.3-4.6s-.3-.6-.3-1.5c0-1.4.8-2.5 1.9-2.5.9 0 1.3.7 1.3 1.5 0 .9-.6 2.3-.9 3.6-.3 1.1.6 2 1.7 2 2 0 3.5-2.1 3.5-5.2 0-2.7-1.9-4.6-4.7-4.6-3.2 0-5.1 2.4-5.1 4.9 0 1 .4 2 .9 2.6.1.1.1.2.1.3l-.3 1.3c0 .1-.1.2-.3.2-.1 0-.2-.1-.3-.2-.7-.9-1.1-2-1.1-3.2 0-2.6 1.9-5 5.5-5 2.9 0 5.1 2.1 5.1 4.9 0 2.9-1.8 5.2-4.4 5.2-.9 0-1.7-.5-2-.9l-.5 2c-.2.7-.7 1.6-1 2.1.8.2 1.6.4 2.4.4 3.7 0 6.5-2.5 6.5-5.8C17 9 14.8 6.5 12 6.5z"
        fill="white"
      />
    </svg>
  );
}

export function MarkGoogle() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden>
      <circle cx="12" cy="12" r="9" fill="none" stroke="#EA4335" strokeWidth="2" />
      <path d="M12 3a9 9 0 0 1 9 9h-9z" fill="#FBBC05" />
      <path d="M21 12a9 9 0 0 1-9 9v-9z" fill="#34A853" />
      <path d="M12 21a9 9 0 0 1-9-9h9z" fill="#4285F4" />
    </svg>
  );
}
