import { describe, expect, it } from 'vitest';
import { identityFingerprint } from './identityBase';

const base = { side_map: { A: 'home', B: 'away' }, assignments: [{ track_id: 1, player_id: 'p1' }] };

describe('identity fingerprint', () => {
  it('keeps old fingerprints when nobody is marked absent', () => {
    expect(identityFingerprint({ ...base, absent_players: [] })).toBe(identityFingerprint(base));
  });

  it('changes when a player is marked absent, regardless of order', () => {
    const a = identityFingerprint({ ...base, absent_players: ['p2', 'p3'] });
    expect(a).not.toBe(identityFingerprint(base));
    expect(identityFingerprint({ ...base, absent_players: ['p3', 'p2'] })).toBe(a);
  });
});
