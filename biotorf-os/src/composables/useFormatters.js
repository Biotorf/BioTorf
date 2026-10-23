const money = (n) =>
  new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(Number(n) || 0) + ' сом';
const num = (n) =>
  new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(Number(n) || 0);
const day = (s) =>
  s ? new Date(s + 'T12:00:00').toLocaleDateString('ru-RU') : '—';

const pillColor = (s) => {
  const t = String(s).toLowerCase();
  if (/просроч|прекращ|не подтверж|ошиб|отмен/.test(t)) return 'red';
  if (/согласован|ожида|работе|провер|чернов|отправ/.test(t)) return 'amber';
  if (/готов|достав|оплач|успеш|утверж|заверш|активн|получен/.test(t)) return '';
  return 'gray';
};

export function useFormatters() {
  return { money, num, day, pillColor };
}