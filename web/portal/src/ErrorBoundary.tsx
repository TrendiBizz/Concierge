/**
 * A page that fails to load should say so, not go blank.
 *
 * The blank-screen bug: a deploy replaces the hashed chunk files, a tab opened before the deploy
 * asks for a chunk that no longer exists, the lazy import rejects, and React unmounts the whole
 * tree — leaving an empty dark page and no explanation. Vite announces this as `vite:preloadError`,
 * so we reload once to pick up the new build; anything else gets this panel with a Reload button.
 */
import {Component, type ErrorInfo, type ReactNode} from 'react';
import {celebrate} from './celebrate';

type State = {message: string | null};

export class ErrorBoundary extends Component<{children: ReactNode}, State> {
  state: State = {message: null};

  static getDerivedStateFromError(error: unknown): State {
    return {message: error instanceof Error ? error.message : String(error)};
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    // Keep a trace in the console so support can see what happened without a repro.
    console.error('Studio page failed:', error, info.componentStack);
  }

  render() {
    if (this.state.message === null) return this.props.children;
    return (
      <div className="c-crash" role="alert">
        <strong>That page did not load.</strong>
        <p>
          Nothing has been lost. Most often this happens when the product was updated while your
          window was open.
        </p>
        <pre>{this.state.message}</pre>
        <button type="button" className="c-crash-button"
                onClick={() => {
                  celebrate(0.4);
                  window.location.reload();
                }}>
          Reload the page
        </button>
      </div>
    );
  }
}
