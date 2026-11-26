import { describe, expect, it } from 'vitest';
import { MODEL_CONFIDENCE, predict, probabilityOf, trainModel } from './matchModel';
import { decodeEmbedding } from './similar';

// Два игрока с одинаковым цветом и разным признаком SigLIP: модель матча должна их различать.
const sample = (hot: number, noise: number) => {
  const x = new Float64Array(10);
  x[hot] = 1;
  x[9] = 0.5; // «цвет» одинаковый
  x[(hot + 3) % 8] += noise;
  return x;
};
const samples = Array.from({ length: 40 }, (_, i) => ({
  x: sample(i % 2 ? 1 : 2, (i % 5) * 0.05),
  y: i % 2 ? 'p1' : 'p2',
}));

describe('match model', () => {
  it('tells apart players of the same colour and is confident', () => {
    const model = trainModel(samples);
    expect(model?.classes).toEqual(['p1', 'p2']);
    const r = model ? predict(model, sample(1, 0.02), ['p1', 'p2']) : null;
    expect(r?.playerId).toBe('p1');
    expect(r?.p).toBeGreaterThanOrEqual(MODEL_CONFIDENCE);
  });

  it('chooses only among available players', () => {
    const model = trainModel(samples);
    const r = model ? predict(model, sample(1, 0.02), ['p2']) : null;
    expect(r).toEqual({ playerId: 'p2', p: 1 });
    expect(model ? predict(model, sample(1, 0), []) : 'none').toBeNull();
  });

  it('needs at least two players and keeps learning from the previous weights', () => {
    expect(trainModel(samples.filter((s) => s.y === 'p1'))).toBeNull();
    const first = trainModel(samples);
    const again = trainModel(samples, first);
    expect(again && probabilityOf(again, sample(2, 0.02), 'p2')).toBeGreaterThan(0.9);
  });

  it('decodes a package embedding to a unit vector', () => {
    const bytes = Array.from({ length: 768 }, (_, i) => (i === 3 ? 127 : i === 4 ? 129 : 0)); // 129 = −127
    const v = decodeEmbedding(btoa(String.fromCharCode(...bytes)));
    expect(v[3]).toBeCloseTo(Math.SQRT1_2, 6);
    expect(v[4]).toBeCloseTo(-Math.SQRT1_2, 6);
  });
});
