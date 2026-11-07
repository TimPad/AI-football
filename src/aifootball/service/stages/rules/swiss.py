"""Пары очередного тура швейцарской системы: по очкам, без повторных встреч."""


def swiss_pairs(ranked, played, had_bye, home_games):
    """ranked — команды по текущей таблице; played — множество frozenset уже сыгранных пар.
    Возвращает (пары (хозяин, гость), отдыхающая команда или None) либо None, если пар без повторов нет."""
    def pair(rest):
        if not rest: return []
        first, others = rest[0], rest[1:]
        for i, other in enumerate(others):
            if frozenset((first, other)) in played: continue
            tail = pair(others[:i] + others[i + 1:])
            if tail is not None:
                # Хозяин — у кого меньше домашних матчей; при равенстве — выше в таблице.
                home, away = (first, other) if home_games.get(first, 0) <= home_games.get(other, 0) else (other, first)
                return [(home, away)] + tail
        return None
    candidates = [None] if len(ranked) % 2 == 0 else [t for t in reversed(ranked) if t not in had_bye] or list(reversed(ranked))
    for bye in candidates:
        result = pair([t for t in ranked if t != bye])
        if result is not None: return result, bye
    return None
