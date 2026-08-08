export function tickerFromPath(pathname: string): string | null {
  const match = pathname.match(/^\/stocks\/([^/]+)\/?$/i);
  if (!match) return null;
  const ticker = decodeURIComponent(match[1]).trim().toUpperCase();
  return ticker || null;
}

export function stockPath(ticker: string): string {
  return `/stocks/${encodeURIComponent(ticker.trim().toUpperCase())}`;
}
