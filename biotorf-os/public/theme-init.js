(() => {
  const storageKey = 'biotorf.theme';
  const preference = matchMedia('(prefers-color-scheme: dark)');
  const root = document.documentElement;
  const themeColor = document.querySelector('meta[name="theme-color"]');
  const valid = (value) => value === 'light' || value === 'dark';
  let selected;

  try { selected = localStorage.getItem(storageKey); } catch { /* storage disabled */ }

  function apply() {
    const theme = valid(selected) ? selected : (preference.matches ? 'dark' : 'light');
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
    themeColor?.setAttribute('content', theme === 'dark' ? '#111b17' : '#f1f6f2');
    window.dispatchEvent(new CustomEvent('biotorf:theme-changed', { detail: theme }));
  }

  window.addEventListener('biotorf:set-theme', ({ detail }) => {
    if (!valid(detail)) return;
    selected = detail;
    try { localStorage.setItem(storageKey, selected); } catch { /* storage disabled */ }
    apply();
  });
  window.addEventListener('storage', ({ key, newValue }) => {
    if (key !== null && key !== storageKey) return;
    selected = newValue;
    apply();
  });
  preference.addEventListener('change', () => { if (!valid(selected)) apply(); });
  apply();
})();
