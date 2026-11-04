/**
 * Where the truck is `elapsedS` seconds after departure, by interpolating the
 * route path, whose vertices carry the router's elapsed time.
 */
export function positionAt(path: [number, number, number][], elapsedS: number): [number, number] | null {
  if (!path.length) return null;
  if (elapsedS <= 0) return [path[0][0], path[0][1]];
  const last = path[path.length - 1];
  if (elapsedS >= last[2]) return null; // already arrived

  // Binary search for the segment containing elapsedS.
  let lo = 0;
  let hi = path.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (path[mid][2] <= elapsedS) lo = mid;
    else hi = mid;
  }
  const [lat1, lon1, t1] = path[lo];
  const [lat2, lon2, t2] = path[hi];
  const f = t2 === t1 ? 0 : (elapsedS - t1) / (t2 - t1);
  return [lat1 + (lat2 - lat1) * f, lon1 + (lon2 - lon1) * f];
}
