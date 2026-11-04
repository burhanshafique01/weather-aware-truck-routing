import { describe, expect, it } from "vitest";

import { positionAt } from "./geo";

const path: [number, number, number][] = [
  [0, 0, 0],
  [0, 1, 100],
  [0, 3, 300],
];

describe("positionAt", () => {
  it("starts at the origin", () => {
    expect(positionAt(path, 0)).toEqual([0, 0]);
  });

  it("interpolates within a segment", () => {
    expect(positionAt(path, 50)).toEqual([0, 0.5]);
    expect(positionAt(path, 200)).toEqual([0, 2]);
  });

  it("returns null once the truck has arrived", () => {
    expect(positionAt(path, 300)).toBeNull();
    expect(positionAt(path, 9999)).toBeNull();
  });

  it("handles an empty path", () => {
    expect(positionAt([], 10)).toBeNull();
  });
});
