import { describe, expect, it } from "vitest";

import {
  clampPage,
  getPageCount,
  HISTORY_PAGE_SIZE,
  paginateItems,
} from "../src/utils/pagination";

describe("paginação dos históricos", () => {
  it("mantém no máximo 20 itens por página", () => {
    const items = Array.from({ length: 45 }, (_, index) => index + 1);

    expect(HISTORY_PAGE_SIZE).toBe(20);
    expect(paginateItems(items, 1)).toEqual(items.slice(0, 20));
    expect(paginateItems(items, 2)).toEqual(items.slice(20, 40));
    expect(paginateItems(items, 3)).toEqual(items.slice(40, 45));
  });

  it("limita páginas inválidas ao intervalo disponível", () => {
    expect(getPageCount(45)).toBe(3);
    expect(clampPage(0, 45)).toBe(1);
    expect(clampPage(9, 45)).toBe(3);
    expect(getPageCount(0)).toBe(1);
  });
});
