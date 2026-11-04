import { describe, expect, it } from "vitest";

import { decodePlace, encodePlace, readSharedTrip } from "./share";

describe("share links", () => {
  it("round-trips a resolved place", () => {
    const place = { label: "Denver, Colorado", lat: 39.7392, lon: -104.9903 };
    expect(decodePlace(encodePlace(place))).toEqual(place);
  });

  it("keeps free text when there are no coordinates", () => {
    expect(decodePlace("Reno, NV")).toEqual({ label: "Reno, NV" });
  });

  it("reads a full trip and ignores invalid options", () => {
    const trip = readSharedTrip("?from=A%4010,20&to=B%40-30.5,40.25&load=42000&every=15");
    expect(trip).toEqual({
      origin: { label: "A", lat: 10, lon: 20 },
      destination: { label: "B", lat: -30.5, lon: 40.25 },
      load: 42000,
      every: undefined,
      departure: undefined,
    });
  });

  it("returns null without both endpoints", () => {
    expect(readSharedTrip("?from=A")).toBeNull();
  });
});
