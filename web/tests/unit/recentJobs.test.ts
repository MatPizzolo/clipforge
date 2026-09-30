import { expect, test } from "vitest";
import { addRecent, readRecent } from "@/lib/recentJobs";

function memory(): Storage {
  const data = new Map<string, string>();
  return {
    get length() { return data.size; },
    clear: () => data.clear(),
    getItem: (k) => data.get(k) ?? null,
    key: (i) => [...data.keys()][i] ?? null,
    removeItem: (k) => void data.delete(k),
    setItem: (k, v) => void data.set(k, v),
  };
}

const broken = {
  getItem() { throw new Error("SecurityError"); },
  setItem() { throw new Error("QuotaExceededError"); },
} as unknown as Storage;

const id = (n: number) => `20260929-3fa9c1d2-${n.toString(16).padStart(4, "0")}`;
const ids = (list: { id: string }[]) => list.map((r) => r.id);

test("newest first, deduplicated, capped at 10, with the time each was opened", () => {
  const s = memory();
  for (let n = 0; n < 12; n++) addRecent(id(n), s, 1_000 + n);
  addRecent(id(5), s, 9_999);
  const list = readRecent(s);
  expect(list).toHaveLength(10);
  expect(list[0]).toEqual({ id: id(5), openedAt: 9_999 });
  expect(ids(list).filter((x) => x === id(5))).toHaveLength(1);
});

test("the old format (plain ids) still reads, with no opened time", () => {
  const s = memory();
  s.setItem("clipforge.recentJobs", JSON.stringify([id(1), id(2)]));
  expect(readRecent(s)).toEqual([{ id: id(1), openedAt: null }, { id: id(2), openedAt: null }]);
});

test("invalid ids and junk JSON are ignored", () => {
  const s = memory();
  s.setItem("clipforge.recentJobs", JSON.stringify(["../x", id(1), 7, { id: "../y", openedAt: 1 }, { id: id(2), openedAt: "x" }]));
  expect(readRecent(s)).toEqual([{ id: id(1), openedAt: null }, { id: id(2), openedAt: null }]);
  s.setItem("clipforge.recentJobs", "{not json");
  expect(readRecent(s)).toEqual([]);
  expect(addRecent("nope", s)).toEqual([]);
});

test("broken or missing storage never throws", () => {
  expect(readRecent(broken)).toEqual([]);
  expect(ids(addRecent(id(1), broken, 5))).toEqual([id(1)]);
  expect(readRecent(null)).toEqual([]);
});
