import { BrowserRouter } from 'react-router';

import { AppProviders } from './providers/AppProviders';
import { AppErrorBoundary } from './providers/AppErrorBoundary';
import { AppRouter } from './router/AppRouter';
import './styles/tokens.css';
import './styles/global.css';

export function App() {
  return (
    <AppErrorBoundary>
      <AppProviders>
        <BrowserRouter>
          <AppRouter />
        </BrowserRouter>
      </AppProviders>
    </AppErrorBoundary>
  );
}
