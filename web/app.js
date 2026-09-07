(async () => {
  const [index, version] = await Promise.all([
    fetch('index.json').then(r => r.json()),
    fetch('version.json').then(r => r.json())
  ]);
  const grid = document.querySelector('#grid');
  const search = document.querySelector('#search');
  document.querySelector('#channels').textContent = index.channels.length;
  document.querySelector('#picons').textContent = version.count;
  document.querySelector('#updated').textContent = new Date(index.generated_at).toLocaleDateString('sk-SK');
  document.querySelector('#package').href = version.package;

  function render(q='') {
    const needle = q.trim().toLowerCase();
    const rows = index.channels.filter(c => !needle || c.name.toLowerCase().includes(needle) || c.service_reference.toLowerCase().includes(needle));
    grid.innerHTML = rows.map(c => {
      const primary = c.files.find(f => f.startsWith('1_0_19_')) || c.files[0];
      return `<article class="card">
        <div class="preview"><img src="picons/${primary}" alt="${c.name}"></div>
        <div class="meta">
          <h2>${c.name}</h2>
          <code>${c.service_reference}</code>
          <div class="downloads">${c.files.map(f => `<a href="picons/${f}" download>${f.split('_')[2]}</a>`).join('')}</div>
        </div>
      </article>`;
    }).join('');
  }
  search.addEventListener('input', e => render(e.target.value));
  render();
})();
