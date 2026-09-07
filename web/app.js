(async () => {
  const [index, version] = await Promise.all([
    fetch('index.json').then(r => r.json()),
    fetch('version.json').then(r => r.json())
  ]);

  const grid = document.querySelector('#grid');
  const search = document.querySelector('#search');
  const filters = document.querySelector('#filters');
  const modal = document.querySelector('#logoModal');
  const modalImage = document.querySelector('#modalImage');
  const modalTitle = document.querySelector('#modalTitle');
  const modalRef = document.querySelector('#modalRef');
  const modalGroup = document.querySelector('#modalGroup');
  const modalDownloads = document.querySelector('#modalDownloads');
  const modalClose = document.querySelector('#modalClose');
  const modalBackdrop = modal.querySelector('.modal-backdrop');

  document.querySelector('#channels').textContent = index.channels.length;
  document.querySelector('#picons').textContent = version.count;
  document.querySelector('#updated').textContent = new Date(index.generated_at).toLocaleDateString('sk-SK');
  document.querySelector('#package').href = version.package;

  let activeGroup = 'all';

  const groupLabel = c => {
    if (c.provider_group === 'skylink') return 'Skylink';
    if (c.provider_group) return c.provider_group;
    if (c.satellite_position) return c.satellite_position;
    return 'Ostatné';
  };

  const groups = [...new Set(index.channels.map(groupLabel))].sort((a,b) => a.localeCompare(b, 'sk'));

  function renderFilters() {
    const items = ['Všetky', ...groups];
    filters.innerHTML = items.map((name, i) => {
      const value = i === 0 ? 'all' : name;
      return '<button class="filter'+(activeGroup===value?' active':'')+'" data-group="'+escapeHtml(value)+'" type="button">'+escapeHtml(name)+'</button>';
    }).join('');

    filters.querySelectorAll('.filter').forEach(btn => {
      btn.addEventListener('click', () => {
        activeGroup = btn.dataset.group;
        renderFilters();
        render();
      });
    });
  }

  function primaryFile(c) {
    return c.files.find(f => f.startsWith('1_0_19_')) || c.files[0];
  }

  function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, m => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[m]));
  }

  function openModal(c) {
    const primary = primaryFile(c);
    modalImage.src = 'picons/' + primary;
    modalImage.alt = c.name;
    modalTitle.textContent = c.name;
    modalRef.textContent = c.service_reference;
    modalGroup.textContent = [groupLabel(c), c.satellite_position].filter(Boolean).join(' • ');
    modalDownloads.innerHTML = c.files.map(f =>
      '<a href="picons/'+encodeURIComponent(f)+'" download>Service type '+escapeHtml(f.split('_')[2])+'</a>'
    ).join('');
    modal.hidden = false;
    document.body.classList.add('modal-open');
  }

  function closeModal() {
    modal.hidden = true;
    modalImage.src = '';
    document.body.classList.remove('modal-open');
  }

  function render() {
    const needle = search.value.trim().toLowerCase();
    const rows = index.channels.filter(c => {
      const matchesSearch = !needle ||
        c.name.toLowerCase().includes(needle) ||
        c.service_reference.toLowerCase().includes(needle);
      const matchesGroup = activeGroup === 'all' || groupLabel(c) === activeGroup;
      return matchesSearch && matchesGroup;
    });

    if (!rows.length) {
      grid.innerHTML = '<div class="empty">Pre tento filter sa nenašli žiadne picony.</div>';
      return;
    }

    grid.innerHTML = rows.map((c, i) => {
      const primary = primaryFile(c);
      return '<article class="card" data-index="'+i+'" tabindex="0" role="button" aria-label="Otvoriť náhľad '+escapeHtml(c.name)+'">'+
        '<div class="preview"><img src="picons/'+encodeURIComponent(primary)+'" alt="'+escapeHtml(c.name)+'" loading="lazy"></div>'+
        '<div class="meta"><h2>'+escapeHtml(c.name)+'</h2><div class="card-sub">'+escapeHtml(groupLabel(c))+(c.satellite_position?' • '+escapeHtml(c.satellite_position):'')+'</div></div>'+
      '</article>';
    }).join('');

    grid.querySelectorAll('.card').forEach((card, i) => {
      const open = () => openModal(rows[i]);
      card.addEventListener('click', open);
      card.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          open();
        }
      });
    });
  }

  search.addEventListener('input', render);
  modalClose.addEventListener('click', closeModal);
  modalBackdrop.addEventListener('click', closeModal);
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !modal.hidden) closeModal();
  });

  renderFilters();
  render();
})();
