import type { MatchPoints } from '../../api/domain';

// Рейтинг матча по очкам за действия (как у FotMob): 6,0 + очки, итог от 3 до 10. Тексты расшифровки и того,
// чего не хватает для полного рейтинга.
export type PointsItem = MatchPoints['items'][number];

export const PART_LABEL: Record<string, string> = {
  goal: 'Гол',
  assist: 'Ассист',
  shot_on_target: 'Удар в створ',
  tackle: 'Отбор',
  interception: 'Перехват',
  shot_block: 'Блок удара',
  pass: 'Передачи',
  save: 'Сейв',
  goal_conceded: 'Пропущенный гол',
  team_goal: 'Гол команды при игроке',
  team_conceded: 'Гол соперника при игроке',
  yellow: 'Жёлтая карточка',
  red: 'Удаление',
  own_goal: 'Автогол',
};
const CATEGORY_LABEL: Record<string, string> = {
  shots: 'удары',
  saves: 'сейвы',
  shot_blocks: 'блоки',
  duels: 'единоборства',
  recoveries: 'возвраты мяча',
  passes: 'передачи',
};

// 1 → «1,0», 0.15 → «0,15», 0.4 → «0,4».
export const decimal = (v: number) => {
  const text = Math.abs(v).toFixed(2);
  return (text.endsWith('0') ? text.slice(0, -1) : text).replace('.', ',');
};
export const signed = (v: number) => `${v < 0 ? '−' : '+'}${decimal(v)}`;

export function pointsIndex(view: MatchPoints | null): Record<string, PointsItem> {
  return Object.fromEntries((view?.items ?? []).map((i) => [i.player_id, i]));
}

// «Гол ×1 +1,0», «Передачи ×50 +0,4» — построчно.
export function breakdown(item: PointsItem): string[] {
  return item.parts.map((p) => `${PART_LABEL[p.key] ?? p.key} ×${p.count} ${signed(p.points)}`);
}

// Как считается: база и очки за действия из политики сервиса.
export function method(view: MatchPoints): string {
  const { base, min, max, pass_cap, points } = view.policy;
  const parts = Object.keys(PART_LABEL)
    .filter((key) => key in points)
    .map((key) =>
      key === 'pass'
        ? `передача ${signed(points[key])} (не больше ${signed(pass_cap)})`
        : `${PART_LABEL[key].toLowerCase()} ${signed(points[key])}`,
    );
  return `${decimal(base)} + очки за действия: ${parts.join(', ')}; итог от ${decimal(min)} до ${decimal(max)}.`;
}

// Чего не хватает: авторы голов, игроки у отметок разметки, вратари, время на площадке, полнота разметки.
export function missingNotes(view: MatchPoints, teamName: (side: 'home' | 'away') => string): string[] {
  const m = view.missing;
  const notes: string[] = [];
  const authored = m.goals_total - m.goals_without_author;
  if (!view.ready)
    notes.push(
      `Рейтинг матча появится, когда у голов будут указаны авторы — хотя бы у ${Math.round(
        view.policy.goal_authors_min * 100,
      )}%. Сейчас указаны у ${authored} из ${m.goals_total}.`,
    );
  else if (m.goals_without_author) notes.push(`Без автора голов: ${m.goals_without_author} из ${m.goals_total}.`);
  if (m.actions_without_player)
    notes.push(`У ${m.actions_without_player} отметок разметки не выбран игрок — они в рейтинг не вошли.`);
  if (m.goalkeeper_unknown.length)
    notes.push(
      `Не указан вратарь: ${m.goalkeeper_unknown.map(teamName).join(', ')}. Сейвы и пропущенные голы без вратаря не учтены.`,
    );
  if (view.on_court_source == null) notes.push('Время на площадке неизвестно — голы при игроке на площадке не учтены.');
  else {
    if (view.on_court_source === 'video')
      notes.push('Время на площадке — по фрагментам видео: на трансляции это время в кадре.');
    if (m.without_on_court) notes.push(`У ${m.without_on_court} игроков неизвестно время на площадке.`);
  }
  if (m.partial_categories.length)
    notes.push(
      `Размечено не всё: ${m.partial_categories.map((c) => CATEGORY_LABEL[c] ?? c).join(', ')} — рейтинг неполный.`,
    );
  return notes;
}
