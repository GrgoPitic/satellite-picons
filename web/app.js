(async () => {
  const [index, version, providerCatalog] = await Promise.all([
    fetch('index.json').then(r => r.json()),
    fetch('version.json').then(r => r.json()),
    fetch('providers.json')
      .then(r => r.ok ? r.json() : { providers: [] })
      .catch(() => ({ providers: [] }))
  ]);

  const grid = document.querySelector('#grid');
  const providerGrid = document.querySelector('#providerGrid');
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

  const providerModal = document.querySelector('#providerModal');
  const providerModalTitle = document.querySelector('#providerModalTitle');
  const providerModalDescription = document.querySelector('#providerModalDescription');
  const providerModalStats = document.querySelector('#providerModalStats');
  const providerModalClose = document.querySelector('#providerModalClose');
  const providerModalBackdrop = providerModal.querySelector('.modal-backdrop');
  const providerFullPackage = document.querySelector('#providerFullPackage');
  const providerBouquetButton = document.querySelector('#providerBouquetButton');
  const bouquetFiles = document.querySelector('#bouquetFiles');
  const bouquetResult = document.querySelector('#bouquetResult');

  document.querySelector('#channels').textContent = index.channels.length;
  document.querySelector('#picons').textContent = version.count;
  document.querySelector('#updated').textContent = new Date(index.generated_at).toLocaleDateString('sk-SK');
  document.querySelector('#package').href = version.package;

  const providerById = new Map(
    (providerCatalog.providers || []).map(provider => [provider.id, provider])
  );

  let activeGroup = 'all';
  let activeProvider = null;
  let pendingCustomBundle = null;

  function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, m => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[m]));
  }

  function providerLabel(id) {
    if (!id) return '';
    return providerById.get(id)?.name || id;
  }

  const groupLabel = c => {
    if (c.provider_group) return providerLabel(c.provider_group);
    if (c.satellite_position) return c.satellite_position;
    return 'Ostatné';
  };

  function serviceIdentity(reference) {
    const parts = String(reference || '').trim().replace(/:$/, '').split(':');
    if (parts.length < 7) return null;
    return parts.slice(3, 7).map(part => part.toUpperCase()).join('_');
  }

  function parseBouquetText(text) {
    const identities = new Set();

    String(text || '').split(/\r?\n/).forEach(line => {
      if (!line.startsWith('#SERVICE ')) return;

      const reference = line.slice('#SERVICE '.length).trim();
      if (!reference || reference.includes('://')) return;

      const parts = reference.replace(/:$/, '').split(':');
      if (parts.length < 7) return;

      // Enigma2 DVB services are normally 1:0:...
      // Skip markers/directories and IPTV references.
      if (parts[0] !== '1' || parts[1] !== '0') return;

      const identity = parts.slice(3, 7).map(part => part.toUpperCase()).join('_');
      identities.add(identity);
    });

    return identities;
  }

  function providerChannels(providerId) {
    return index.channels.filter(
      channel => String(channel.provider_group || '').toLowerCase() === String(providerId || '').toLowerCase()
    );
  }

  function renderProviders() {
    const providers = providerCatalog.providers || [];

    if (!providers.length) {
      providerGrid.innerHTML = '<div class="provider-empty">Balíky podľa operátora zatiaľ nie sú dostupné.</div>';
      return;
    }

    providerGrid.innerHTML = providers.map(provider => {
      const meta = [
        ...(provider.countries || []),
        ...(provider.positions || [])
      ].map(value => '<span>'+escapeHtml(value)+'</span>').join('');

      const counts = provider.available
        ? '<strong>'+escapeHtml(provider.channel_count)+'</strong> kanálov · <strong>'+escapeHtml(provider.picon_count)+'</strong> piconov'
        : 'Balík sa sprístupní po doplnení kanálov';

      const inner =
        '<div class="provider-top">'+
          '<div>'+
            '<p class="provider-status '+(provider.available ? 'online' : 'pending')+'">'+
              (provider.available ? 'DOSTUPNÉ' : 'PRIPRAVUJEME')+
            '</p>'+
            '<h3>'+escapeHtml(provider.name)+'</h3>'+
          '</div>'+
          '<span class="provider-arrow">'+(provider.available ? '→' : '·')+'</span>'+
        '</div>'+
        '<p class="provider-description">'+escapeHtml(provider.description || '')+'</p>'+
        '<div class="provider-meta">'+meta+'</div>'+
        '<div class="provider-foot">'+
          '<span>'+counts+'</span>'+
          '<span class="provider-action">'+(provider.available ? 'Možnosti stiahnutia' : 'Zatiaľ nedostupné')+'</span>'+
        '</div>';

      if (provider.available && provider.package) {
        return '<button class="provider-card available" type="button" data-provider="'+escapeHtml(provider.id)+'">'+inner+'</button>';
      }

      return '<article class="provider-card unavailable" aria-disabled="true">'+inner+'</article>';
    }).join('');

    providerGrid.querySelectorAll('.provider-card.available').forEach(card => {
      card.addEventListener('click', () => {
        const provider = providerById.get(card.dataset.provider);
        if (provider) openProviderModal(provider);
      });
    });
  }

  function openProviderModal(provider) {
    activeProvider = provider;
    pendingCustomBundle = null;
    bouquetFiles.value = '';
    bouquetResult.hidden = true;
    bouquetResult.innerHTML = '';

    providerModalTitle.textContent = provider.name || provider.id;
    providerModalDescription.textContent = provider.description || '';
    providerModalStats.innerHTML =
      '<span><strong>'+escapeHtml(provider.channel_count || 0)+'</strong> kanálov</span>'+
      '<span><strong>'+escapeHtml(provider.picon_count || 0)+'</strong> piconov</span>'+
      ((provider.positions || []).length
        ? '<span>'+provider.positions.map(escapeHtml).join(' · ')+'</span>'
        : '');

    providerFullPackage.href = provider.package;
    providerFullPackage.setAttribute(
      'download',
      'satellite-picons-' + String(provider.id || 'provider') + '.zip'
    );

    providerModal.hidden = false;
    document.body.classList.add('modal-open');
  }

  function closeProviderModal() {
    providerModal.hidden = true;
    activeProvider = null;
    pendingCustomBundle = null;
    bouquetFiles.value = '';
    bouquetResult.hidden = true;
    bouquetResult.innerHTML = '';
    document.body.classList.remove('modal-open');
  }

  function renderBouquetResult(provider, fileCount, identities, matchedChannels, piconFiles) {
    bouquetResult.hidden = false;

    if (!identities.size) {
      bouquetResult.innerHTML =
        '<strong>Nenašli sa DVB kanály.</strong>'+
        '<span>Vyber súbory <code>userbouquet*.tv</code> alebo <code>userbouquet*.radio</code> z priečinka <code>/etc/enigma2/</code>.</span>';
      return;
    }

    if (!matchedChannels.length) {
      bouquetResult.innerHTML =
        '<strong>Nenašli sa zhodné kanály pre '+escapeHtml(provider.name)+'.</strong>'+
        '<span>Načítaných bouquet súborov: '+fileCount+' · DVB služieb: '+identities.size+'.</span>';
      return;
    }

    bouquetResult.innerHTML =
      '<div class="bouquet-summary">'+
        '<div><strong>'+matchedChannels.length+'</strong><span>zhodných kanálov</span></div>'+
        '<div><strong>'+piconFiles.length+'</strong><span>piconov v ZIP</span></div>'+
        '<div><strong>'+fileCount+'</strong><span>bouquet súborov</span></div>'+
      '</div>'+
      '<button id="buildCustomZip" class="button primary bouquet-build" type="button">Vytvoriť ZIP pre moje kanály</button>'+
      '<p class="bouquet-note">Spracovanie prebieha iba v tomto prehliadači. Bouquet súbory sa nikam neodosielajú.</p>';

    document.querySelector('#buildCustomZip').addEventListener('click', buildCustomBundle);
  }

  async function analyzeBouquets(files) {
    if (!activeProvider || !files.length) return;

    bouquetResult.hidden = false;
    bouquetResult.innerHTML = '<span>Analyzujem vybrané bouquet súbory…</span>';

    const texts = await Promise.all([...files].map(file => file.text()));
    const identities = new Set();

    texts.forEach(text => {
      parseBouquetText(text).forEach(identity => identities.add(identity));
    });

    const matchedChannels = providerChannels(activeProvider.id).filter(channel => {
      const identity = serviceIdentity(channel.service_reference);
      return identity && identities.has(identity);
    });

    const piconFiles = [...new Set(
      matchedChannels.flatMap(channel => channel.files || [])
    )].sort();

    pendingCustomBundle = {
      provider: activeProvider,
      matchedChannels,
      piconFiles
    };

    renderBouquetResult(
      activeProvider,
      files.length,
      identities,
      matchedChannels,
      piconFiles
    );
  }

  function crc32(bytes) {
    let crc = 0xffffffff;

    for (let i = 0; i < bytes.length; i++) {
      crc ^= bytes[i];
      for (let bit = 0; bit < 8; bit++) {
        crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
      }
    }

    return (crc ^ 0xffffffff) >>> 0;
  }

  function dosDateTime(date = new Date()) {
    const year = Math.max(1980, date.getFullYear());
    const time =
      ((date.getHours() & 0x1f) << 11) |
      ((date.getMinutes() & 0x3f) << 5) |
      ((Math.floor(date.getSeconds() / 2)) & 0x1f);

    const day =
      (((year - 1980) & 0x7f) << 9) |
      (((date.getMonth() + 1) & 0x0f) << 5) |
      (date.getDate() & 0x1f);

    return { time, day };
  }

  function write16(view, offset, value) {
    view.setUint16(offset, value, true);
  }

  function write32(view, offset, value) {
    view.setUint32(offset, value >>> 0, true);
  }

  function makeStoredZip(files) {
    const encoder = new TextEncoder();
    const chunks = [];
    const centralChunks = [];
    const stamp = dosDateTime();
    let offset = 0;

    files.forEach(file => {
      const nameBytes = encoder.encode(file.name);
      const data = file.data;
      const checksum = crc32(data);

      const local = new Uint8Array(30 + nameBytes.length);
      const localView = new DataView(local.buffer);
      write32(localView, 0, 0x04034b50);
      write16(localView, 4, 20);
      write16(localView, 6, 0x0800);
      write16(localView, 8, 0);
      write16(localView, 10, stamp.time);
      write16(localView, 12, stamp.day);
      write32(localView, 14, checksum);
      write32(localView, 18, data.length);
      write32(localView, 22, data.length);
      write16(localView, 26, nameBytes.length);
      write16(localView, 28, 0);
      local.set(nameBytes, 30);

      const central = new Uint8Array(46 + nameBytes.length);
      const centralView = new DataView(central.buffer);
      write32(centralView, 0, 0x02014b50);
      write16(centralView, 4, 20);
      write16(centralView, 6, 20);
      write16(centralView, 8, 0x0800);
      write16(centralView, 10, 0);
      write16(centralView, 12, stamp.time);
      write16(centralView, 14, stamp.day);
      write32(centralView, 16, checksum);
      write32(centralView, 20, data.length);
      write32(centralView, 24, data.length);
      write16(centralView, 28, nameBytes.length);
      write16(centralView, 30, 0);
      write16(centralView, 32, 0);
      write16(centralView, 34, 0);
      write16(centralView, 36, 0);
      write32(centralView, 38, 0);
      write32(centralView, 42, offset);
      central.set(nameBytes, 46);

      chunks.push(local, data);
      centralChunks.push(central);
      offset += local.length + data.length;
    });

    const centralStart = offset;
    const centralSize = centralChunks.reduce((sum, chunk) => sum + chunk.length, 0);

    const end = new Uint8Array(22);
    const endView = new DataView(end.buffer);
    write32(endView, 0, 0x06054b50);
    write16(endView, 4, 0);
    write16(endView, 6, 0);
    write16(endView, 8, files.length);
    write16(endView, 10, files.length);
    write32(endView, 12, centralSize);
    write32(endView, 16, centralStart);
    write16(endView, 20, 0);

    return new Blob(
      [...chunks, ...centralChunks, end],
      { type: 'application/zip' }
    );
  }

  async function fetchPiconFiles(fileNames, onProgress) {
    const result = new Array(fileNames.length);
    let next = 0;
    let complete = 0;
    const workerCount = Math.min(8, Math.max(1, fileNames.length));

    async function worker() {
      while (true) {
        const indexToFetch = next++;
        if (indexToFetch >= fileNames.length) return;

        const fileName = fileNames[indexToFetch];
        const response = await fetch('picons/' + encodeURIComponent(fileName));
        if (!response.ok) {
          throw new Error('HTTP ' + response.status + ': ' + fileName);
        }

        result[indexToFetch] = {
          name: fileName,
          data: new Uint8Array(await response.arrayBuffer())
        };

        complete += 1;
        onProgress(complete, fileNames.length);
      }
    }

    await Promise.all(Array.from({ length: workerCount }, worker));
    return result;
  }

  async function buildCustomBundle() {
    if (!pendingCustomBundle || !pendingCustomBundle.piconFiles.length) return;

    const { provider, matchedChannels, piconFiles } = pendingCustomBundle;
    const button = document.querySelector('#buildCustomZip');
    if (button) button.disabled = true;

    bouquetResult.innerHTML =
      '<strong>Pripravujem vlastný balík…</strong>'+
      '<span id="bouquetProgress">0 / '+piconFiles.length+' piconov</span>';

    try {
      const files = await fetchPiconFiles(
        piconFiles,
        (done, total) => {
          const progress = document.querySelector('#bouquetProgress');
          if (progress) progress.textContent = done + ' / ' + total + ' piconov';
        }
      );

      const blob = makeStoredZip(files);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download =
        'satellite-picons-' +
        String(provider.id || 'provider') +
        '-moje-kanaly.zip';

      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);

      bouquetResult.innerHTML =
        '<strong>Hotovo.</strong>'+
        '<span>Vytvorený ZIP obsahuje '+piconFiles.length+' piconov pre '+matchedChannels.length+' kanálov.</span>'+
        '<button id="chooseBouquetsAgain" class="button bouquet-secondary" type="button">Vybrať iné bouquety</button>';

      document.querySelector('#chooseBouquetsAgain').addEventListener('click', () => {
        bouquetFiles.click();
      });
    } catch (error) {
      bouquetResult.innerHTML =
        '<strong>Vytvorenie ZIP zlyhalo.</strong>'+
        '<span>'+escapeHtml(error.message || error)+'</span>'+
        '<button id="retryCustomZip" class="button bouquet-secondary" type="button">Skúsiť znova</button>';

      document.querySelector('#retryCustomZip').addEventListener('click', buildCustomBundle);
    }
  }

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

    grid.innerHTML = rows.map(c => {
      const primary = primaryFile(c);
      return '<article class="card" tabindex="0" role="button" aria-label="Otvoriť náhľad '+escapeHtml(c.name)+'">'+
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

  providerModalClose.addEventListener('click', closeProviderModal);
  providerModalBackdrop.addEventListener('click', closeProviderModal);
  providerBouquetButton.addEventListener('click', () => bouquetFiles.click());
  bouquetFiles.addEventListener('change', () => analyzeBouquets(bouquetFiles.files));

  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    if (!modal.hidden) closeModal();
    if (!providerModal.hidden) closeProviderModal();
  });

  renderProviders();
  renderFilters();
  render();
})();
