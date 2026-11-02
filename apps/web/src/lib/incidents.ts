// The incident list's live behaviour: an opened or changed incident goes to the top, replacing its old row.
export type Listed = { id: string };

export function upsertTop<T extends Listed>(list: T[], incident: T): T[] {
  return [incident, ...list.filter(item => item.id !== incident.id)];
}

/** Appends a further page, dropping any incident already shown (a live update can have moved it to the top). */
export function appendPage<T extends Listed>(list: T[], page: T[]): T[] {
  const shown = new Set(list.map(item => item.id));
  return [...list, ...page.filter(item => !shown.has(item.id))];
}
