import { describe, expect, it } from 'vitest';
import type { MatchPoints } from '../../api/domain';
import { breakdown, decimal, method, missingNotes, signed } from './matchPoints';

const policy = {
  base: 6,
  min: 3,
  max: 10,
  pass_cap: 0.4,
  goal_authors_min: 0.8,
  points: { goal: 1, assist: 0.6, pass: 0.01, goal_conceded: -0.4 },
};
const missing = {
  goals_total: 15,
  goals_without_author: 15,
  actions_without_player: 112,
  goalkeeper_unknown: ['home', 'away'] as ('home' | 'away')[],
  without_on_court: 0,
  partial_categories: ['shots', 'passes'],
};
const view = (extra: Partial<MatchPoints> = {}): MatchPoints => ({
  model_version: 'match-points-v1',
  ready: false,
  complete: false,
  best_player_id: null,
  items: [],
  missing,
  on_court_source: 'video',
  policy,
  ...extra,
});
const team = (side: 'home' | 'away') => (side === 'home' ? 'РЕХАБ' : 'ВШЭ Ю');

describe('match rating texts', () => {
  it('formats points with a comma and a real minus', () => {
    expect([decimal(1), decimal(0.15), decimal(0.4), decimal(10)]).toEqual(['1,0', '0,15', '0,4', '10,0']);
    expect([signed(1), signed(-0.4), signed(0.02)]).toEqual(['+1,0', '−0,4', '+0,02']);
  });
  it('lists the parts of a player rating', () => {
    const item = {
      player_id: 'p',
      side: 'home' as const,
      display_name: 'Игрок',
      goalkeeper: false,
      rating: 7.4,
      parts: [
        { key: 'goal', count: 1, points: 1 },
        { key: 'pass', count: 50, points: 0.4 },
      ],
    };
    expect(breakdown(item)).toEqual(['Гол ×1 +1,0', 'Передачи ×50 +0,4']);
  });
  it('explains the method from the policy', () => {
    expect(method(view())).toBe(
      '6,0 + очки за действия: гол +1,0, ассист +0,6, передача +0,01 (не больше +0,4), пропущенный гол −0,4; итог от 3,0 до 10,0.',
    );
  });
  it('says what is missing before the rating can be shown', () => {
    expect(missingNotes(view(), team)).toEqual([
      'Рейтинг матча появится, когда у голов будут указаны авторы — хотя бы у 80%. Сейчас указаны у 0 из 15.',
      'У 112 отметок разметки не выбран игрок — они в рейтинг не вошли.',
      'Не указан вратарь: РЕХАБ, ВШЭ Ю. Сейвы и пропущенные голы без вратаря не учтены.',
      'Время на площадке — по фрагментам видео: на трансляции это время в кадре.',
      'Размечено не всё: удары, передачи — рейтинг неполный.',
    ]);
    const done = view({
      ready: true,
      complete: true,
      on_court_source: 'manual',
      missing: {
        ...missing,
        goals_without_author: 0,
        actions_without_player: 0,
        goalkeeper_unknown: [],
        partial_categories: [],
      },
    });
    expect(missingNotes(done, team)).toEqual([]);
  });
});
