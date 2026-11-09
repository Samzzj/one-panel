(function () {
  try {
    var saved = localStorage.getItem('rp-theme');
    document.documentElement.dataset.theme = saved === 'light' ? 'light' : 'dark';
  } catch (e) {
    document.documentElement.dataset.theme = 'dark';
  }
})();
