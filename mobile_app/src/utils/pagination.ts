export const HISTORY_PAGE_SIZE = 20;

export function getPageCount(totalItems: number, pageSize = HISTORY_PAGE_SIZE) {
  if (!Number.isFinite(totalItems) || totalItems <= 0) return 1;
  if (!Number.isFinite(pageSize) || pageSize <= 0) return 1;
  return Math.max(1, Math.ceil(totalItems / pageSize));
}

export function clampPage(page: number, totalItems: number, pageSize = HISTORY_PAGE_SIZE) {
  const safePage = Number.isFinite(page) ? Math.trunc(page) : 1;
  return Math.min(Math.max(1, safePage), getPageCount(totalItems, pageSize));
}

export function paginateItems<T>(items: readonly T[], page: number, pageSize = HISTORY_PAGE_SIZE) {
  const safePage = clampPage(page, items.length, pageSize);
  const start = (safePage - 1) * pageSize;
  return items.slice(start, start + pageSize);
}
