import { describe, expect, it } from "vitest";
import { GAUGE_POSITIONS, GAUGE_TICKS, fractionToRotation, pointOnArc, valueToFraction } from "./gauge";

describe("gauge scale", () => {
  it("uses exactly the brief's labels, increasing left to right", () => {
    expect([...GAUGE_TICKS]).toEqual([0, 10, 20, 30, 60, 90, 120, 150]);
    for (let i = 1; i < GAUGE_POSITIONS.length; i++) expect(GAUGE_POSITIONS[i]).toBeGreaterThan(GAUGE_POSITIONS[i - 1]);
  });

  it("puts every tick at its position", () => {
    GAUGE_TICKS.forEach((tick, i) => expect(valueToFraction(tick)).toBeCloseTo(GAUGE_POSITIONS[i]));
  });

  it("places 20 at the top centre and 150 at the far right", () => {
    expect(fractionToRotation(valueToFraction(20))).toBe(0);
    const top = pointOnArc(100, 100, 50, valueToFraction(20));
    expect(top.x).toBeCloseTo(100);
    expect(top.y).toBeCloseTo(50);
    expect(fractionToRotation(valueToFraction(150))).toBeGreaterThan(90);
  });

  it("interpolates and clamps", () => {
    expect(valueToFraction(15)).toBeCloseTo(0.375);
    expect(valueToFraction(45)).toBeCloseTo(0.65);
    expect(valueToFraction(172)).toBe(1);
    expect(valueToFraction(-5)).toBe(0);
    expect(valueToFraction(Number.NaN)).toBe(0);
  });
});
