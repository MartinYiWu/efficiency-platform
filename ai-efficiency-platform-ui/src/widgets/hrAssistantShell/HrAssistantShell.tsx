import type { ReactNode } from 'react';

import { PlatformShell } from '../platform-shell';

export function HrAssistantShell({ children }: { children: ReactNode }) {
  return <PlatformShell>{children}</PlatformShell>;
}
