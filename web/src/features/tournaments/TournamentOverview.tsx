import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../../api/client';
import { ConfirmDialog, MoreMenu } from '../../components/MoreMenu';
import { ErrorBox } from '../../components/ui';
import type { Data } from './TournamentPage';
export function nextStep(d: Data) {
  return d.t.archived
    ? null
    : !d.rules.length
      ? { label: 'Настроить регламент', href: `/tournaments/${d.t.id}/setup?step=rules` }
      : d.entries.length < 2
        ? { label: 'Добавить команды', href: `/tournaments/${d.t.id}/setup?step=teams` }
        : null;
}
const setVisibility = (d: Data, visibility: 'public' | 'draft') =>
  api(`/tournaments/${d.t.id}`, {
    method: 'PATCH',
    body: JSON.stringify({ expected_revision: d.t.revision, visibility }),
  });
// Баннер нужен, пока турнир не готов или не на сайте; опубликованный и настроенный турнир — только чип у заголовка.
export function TournamentOverview({ data: d, onSaved }: { data: Data; onSaved: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const next = nextStep(d);
  const draft = d.t.visibility !== 'public';
  if (!draft && !next) return null;
  async function publish() {
    setBusy(true);
    setError(undefined);
    try {
      await setVisibility(d, 'public');
      onSaved();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="surface tournament-readiness">
      <div className="row wrap">
        <b>{draft ? 'Черновик турнира' : 'Турнир на сайте'}</b>
        <span className="muted">
          Команд: {d.entries.length} · Матчей: {d.matches.length} ·{' '}
          {d.rules.length ? 'Регламент сохранён' : 'Нет регламента'}
        </span>
        {next && (
          <Link className="button primary" to={next.href}>
            {next.label}
          </Link>
        )}
        {draft && !d.t.archived && (
          <button className={next ? undefined : 'primary'} disabled={busy} onClick={publish}>
            Опубликовать страницу турнира
          </button>
        )}
      </div>
      {draft && (
        <p className="muted small">
          Результаты матчей, видеоаналитика и рейтинги публикуются отдельно в своих разделах.
        </p>
      )}
      <ErrorBox error={error} />
    </section>
  );
}
// Чип состояния у заголовка и редкое опасное действие «Скрыть страницу» — в меню «…» с подтверждением.
export function TournamentVisibility({ data: d, onSaved }: { data: Data; onSaved: () => void }) {
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<unknown>();
  const live = d.t.visibility === 'public';
  return (
    <>
      {live ? <span className="chip ok">На сайте</span> : <span className="chip">Черновик</span>}
      {live && !d.t.archived && (
        <MoreMenu
          label="Ещё действия с турниром"
          items={[{ label: 'Скрыть страницу турнира', danger: true, onSelect: () => setConfirm(true) }]}
        />
      )}
      {confirm && (
        <ConfirmDialog
          title="Скрыть страницу турнира?"
          confirm="Скрыть страницу"
          onClose={() => setConfirm(false)}
          onConfirm={async () => {
            try {
              await setVisibility(d, 'draft');
              setConfirm(false);
              onSaved();
            } catch (e) {
              setError(e);
            }
          }}
        >
          <p>
            Зрители перестанут видеть расписание, результаты и рейтинг этого турнира. Данные и публикации матчей
            сохранятся — страницу можно опубликовать снова.
          </p>
          <ErrorBox error={error} />
        </ConfirmDialog>
      )}
    </>
  );
}
