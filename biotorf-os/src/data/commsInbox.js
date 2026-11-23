export const INBOX_STATES = {
  new: 'Новый',
  working: 'В работе',
  waiting: 'Ждём клиента',
  closed: 'Закрыт',
};

export function isResponseOverdue(work) {
  return !!work?.responseDue && ['new', 'working'].includes(work.state) && Date.parse(work.responseDue) < Date.now();
}
