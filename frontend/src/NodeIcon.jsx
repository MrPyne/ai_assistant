import React from 'react'

function Icon({ type, size = 18 }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', xmlns: 'http://www.w3.org/2000/svg' }
  if (type === 'webhook') {
    return (
      <svg {...common} stroke="currentColor">
        <path d="M12 2v6" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M19 7l-7 7-7-7" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  }
  if (type === 'http') {
    return (
      <svg {...common} stroke="currentColor">
        <path d="M3 12h18" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M12 3v18" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  }
  if (type === 'llm') {
    return (
      <svg {...common} stroke="currentColor">
        <path d="M12 3C9.238 3 7 5.238 7 8c0 1.657.895 3.105 2.29 3.932L9 17l3.245-1.073A5.002 5.002 0 0017 8c0-2.762-2.238-5-5-5z" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  }
  // default / generic
  return (
    <svg {...common} stroke="currentColor">
      <circle cx="12" cy="12" r="9" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// extra icons
Icon.Email = function EmailIcon({ size = 18 }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', xmlns: 'http://www.w3.org/2000/svg' }
  return (
    <svg {...common} stroke="currentColor">
      <rect x="3" y="5" width="18" height="14" rx="2" strokeWidth="1.2" />
      <path d="M3 7l9 6 9-6" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

Icon.Cron = function CronIcon({ size = 18 }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', xmlns: 'http://www.w3.org/2000/svg' }
  return (
    <svg {...common} stroke="currentColor">
      <circle cx="12" cy="12" r="9" strokeWidth="1.2" />
      <path d="M12 7v5l3 3" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

Icon.Slack = function SlackIcon({ size = 18 }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', xmlns: 'http://www.w3.org/2000/svg' }
  return (
    <svg {...common} stroke="currentColor">
      <path d="M14 3h2a2 2 0 012 2v2" strokeWidth="1.2" strokeLinecap="round" />
      <path d="M10 21H8a2 2 0 01-2-2v-2" strokeWidth="1.2" strokeLinecap="round" />
      <path d="M21 14v2a2 2 0 01-2 2h-2" strokeWidth="1.2" strokeLinecap="round" />
      <path d="M3 10V8a2 2 0 012-2h2" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  )
}

Icon.DB = function DbIcon({ size = 18 }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', xmlns: 'http://www.w3.org/2000/svg' }
  return (
    <svg {...common} stroke="currentColor">
      <ellipse cx="12" cy="6" rx="8" ry="3" strokeWidth="1.2" />
      <path d="M4 6v6c0 1.657 3.582 3 8 3s8-1.343 8-3V6" strokeWidth="1.2" />
    </svg>
  )
}

Icon.S3 = function S3Icon({ size = 18 }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', xmlns: 'http://www.w3.org/2000/svg' }
  return (
    <svg {...common} stroke="currentColor">
      <rect x="3" y="7" width="18" height="10" rx="2" strokeWidth="1.2" />
      <path d="M7 11h10" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  )
}

Icon.Transform = function TransformIcon({ size = 18 }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', xmlns: 'http://www.w3.org/2000/svg' }
  return (
    <svg {...common} stroke="currentColor">
      <path d="M4 7h6l2 3 6-3" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 17h16" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  )
}

Icon.Wait = function WaitIcon({ size = 18 }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', xmlns: 'http://www.w3.org/2000/svg' }
  return (
    <svg {...common} stroke="currentColor">
      <path d="M12 7v5l3 3" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="12" cy="12" r="9" strokeWidth="1.2" />
    </svg>
  )
}

export default Icon
