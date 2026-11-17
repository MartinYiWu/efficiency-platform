export function isIsolatedRequest(url: string, resourceType: string, baseURL: string) {
  const target = new URL(url);
  return (
    target.origin !== new URL(baseURL).origin ||
    /^\/(api|v1)(\/|$)/.test(target.pathname) ||
    ['fetch', 'xhr', 'eventsource'].includes(resourceType)
  );
}
