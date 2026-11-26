import type { AnalysisAssignment } from '../../api/domain';

/**
 * Отпечаток сопоставления: стороны команд и решения по фрагментам без учёта порядка строк и пустых полей.
 * По нему черновик в браузере узнаёт, что версия на сервере изменилась после того, как черновик начат.
 */
export function identityFingerprint(review: { side_map: Record<string, string>; assignments: AnalysisAssignment[] }) {
  const sides = Object.keys(review.side_map)
    .sort()
    .map((k) => [k, review.side_map[k]]);
  const rows = review.assignments
    // Сервер обрезает пробелы в причине исключения: своё сохранение не должно выглядеть чужой правкой.
    .map((a) => [a.track_id, a.player_id ?? null, a.excluded_reason?.trim() ?? null] as const)
    .sort((x, y) => x[0] - y[0]);
  const text = JSON.stringify([sides, rows]);
  // FNV-1a: короткая строка в localStorage вместо копии всей версии сервера.
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return `${rows.length}:${h.toString(16)}`;
}
