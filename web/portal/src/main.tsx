import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import {ErrorBoundary} from './ErrorBoundary.tsx'

// A deploy replaces the hashed chunk files. A window opened before it will ask for a chunk that
// no longer exists; Vite reports that here, and one reload picks up the new build. Without this
// the lazy-loaded page stayed blank with no message (reported 2026-11-14 on the Social tab).
window.addEventListener('vite:preloadError', () => {
  const key = 'concierge:reloaded'
  if (sessionStorage.getItem(key)) return
  sessionStorage.setItem(key, '1')
  window.location.reload()
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
