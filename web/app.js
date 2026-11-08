(async () => {
  try {
  // Always read the current deployment instead of a cached older catalogue.
  const cacheToken = Date.now();
  const [index, version, orbitCatalog, operatorCatalog] = await Promise.all([
    fetch('index.json?v=' + cacheToken, { cache: 'no-store' }).then(r => r.json()),
    fetch('version.json?v=' + cacheToken, { cache: 'no-store' }).then(r => r.json()),
    fetch('orbits.json?v=' + cacheToken, { cache: 'no-store' })
      .then(r => r.ok ? r.json() : { orbits: [] })
      .catch(() => ({ orbits: [] })),
    fetch('operators.json?v=' + cacheToken, { cache: 'no-store' })
      .then(r => r.ok ? r.json() : { providers: [] })
      .catch(() => ({ providers: [] }))
  ]);

  // A picon filename stays the same when the logo is replaced.
  // Tie its URL to this build so the browser fetches the updated image.
  const piconVersion = encodeURIComponent(index.generated_at || String(cacheToken));

  const operatorList = document.querySelector('#operatorList');
  const operatorTitle = document.querySelector('#operatorTitle');
  const operatorDescription = document.querySelector('#operatorDescription');
  const operatorProgressBadge = document.querySelector('#operatorProgressBadge');
  const operatorProgressText = document.querySelector('#operatorProgressText');
  const operatorProgressFill = document.querySelector('#operatorProgressFill');
  const operatorSearch = document.querySelector('#operatorSearch');
  const operatorPackageArea = document.querySelector('#operatorPackageArea');
  const logoGrid = document.querySelector('#logoGrid');
  const operatorEmpty = document.querySelector('#operatorEmpty');

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
  document.querySelector('#updated').textContent =
    new Date(index.generated_at).toLocaleDateString('sk-SK');

  const orbitProviders = (orbitCatalog.orbits || []).map(p => ({...p, group: 'orbit'}));
  const operatorProviders = (operatorCatalog.providers || []).map(p => ({...p, group: 'operator'}));
  const providers = [...orbitProviders, ...operatorProviders];
  const providerById = new Map(providers.map(provider => [provider.id, provider]));

  let activeProviderId = providers.find(p => Number(p.curated_channel_count || 0) > 0)?.id || providers[0]?.id || null;

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[char]));
  }

  function providerChannels(providerId) {
    const selected = providerById.get(providerId);
    if (selected?.group === 'operator' || selected?.group === 'orbit') {
      // Orbit and operator catalogues list EVERY channel, even without a logo.
      // Never imply an uncurated service has a downloadable picon.
      return selected.channels || [];
    }
    return [];
  }

  function primaryFile(channel) {
    return (channel.files || []).find(file => file.startsWith('1_0_19_')) ||
      (channel.files || [])[0];
  }

  function providerProgress(provider) {
    const expected = Number(provider?.channel_count || 0);
    const curated = Number(provider?.curated_channel_count || 0);
    const complete = provider?.complete === true && expected > 0 && curated === expected;
    const percent = expected > 0 ? Math.min(100, Math.round((curated / expected) * 100)) : 0;
    return { expected, curated, complete, percent };
  }

  function renderOperators() {
    if (!providers.length) {
      operatorList.innerHTML = '<div class="empty-state">Zatiaľ nie sú dostupné orbitálne katalógy.</div>';
      return;
    }

    operatorList.innerHTML = providers.map((provider, index) => {
      const previous = providers[index - 1];
      const heading = index === 0 || previous.group !== provider.group
        ? '<p class="sidebar-section-title">' + (provider.group === 'operator' ? 'OPERÁTORI · OVERENÉ ZOZNAMY' : 'ORBITÁLNE POZÍCIE') + '</p>'
        : '';
      const { expected, curated, complete } = providerProgress(provider);
      const state = complete ? 'complete' : (curated > 0 ? 'progress' : '');
      return heading + (
        '<button class="operator-item '+state+(provider.id===activeProviderId?' active':'')+'" '+
          'type="button" data-provider="'+escapeHtml(provider.id)+'">'+
          '<span>'+
            '<span class="operator-item-name">'+escapeHtml(provider.name)+'</span>'+
            '<span class="operator-item-meta">'+
              (provider.positions || []).map(escapeHtml).join(' · ')+
            '</span>'+
          '</span>'+
          '<span class="operator-item-count">'+curated+'/'+expected+'</span>'+
        '</button>'
      );
    }).join('');

    operatorList.querySelectorAll('.operator-item').forEach(button => {
      button.addEventListener('click', () => {
        activeProviderId = button.dataset.provider;
        operatorSearch.value = '';
        renderOperators();
        renderActiveProvider();
      });
    });
  }

  function renderPackage(provider) {
    const { expected, curated } = providerProgress(provider);

    if (curated > 0 && provider.package) {
      operatorPackageArea.innerHTML =
        '<a class="package-download" href="'+escapeHtml(provider.package)+'" download>'+
          'Stiahnuť picony · '+curated+' staníc'+
        '</a>';
      return;
    }

    operatorPackageArea.innerHTML =
      '<div class="package-waiting">'+
        'Picony zatiaľ nie sú pripravené · bez loga '+
        Math.max(0, expected - curated)+' staníc'+
      '</div>';
  }

  function renderActiveProvider() {
    const provider = providerById.get(activeProviderId);
    if (!provider) {
      operatorTitle.textContent = 'Žiadna kategória';
      operatorDescription.textContent = '';
      logoGrid.innerHTML = '';
      operatorEmpty.hidden = false;
      return;
    }

    const { expected, curated, complete, percent } = providerProgress(provider);
    operatorTitle.textContent = provider.name || provider.id;
    operatorDescription.textContent = provider.description || '';

    operatorProgressBadge.className =
      'progress-badge ' + (complete ? 'complete' : (curated > 0 ? 'progress' : ''));
    operatorProgressBadge.textContent =
      complete ? '100 % HOTOVÉ' : (curated > 0 ? percent+' % HOTOVÉ' : 'ČAKÁ NA LOGÁ');

    operatorProgressText.textContent = curated+' / '+expected;
    operatorProgressFill.style.width = percent+'%';
    operatorProgressFill.className = 'progress-fill'+(complete?' complete':'');
    renderPackage(provider);
    renderLogos();
  }

  function renderLogos() {
    const needle = operatorSearch.value.trim().toLowerCase();
    const rows = providerChannels(activeProviderId).filter(channel => {
      if (!needle) return true;
      return (
        String(channel.name || '').toLowerCase().includes(needle) ||
        String(channel.service_reference || '').toLowerCase().includes(needle)
      );
    });

    operatorEmpty.hidden = rows.length > 0;
    if (!rows.length) {
      logoGrid.innerHTML = '';
      operatorEmpty.textContent = needle
        ? 'Pre toto vyhľadávanie sa nenašla žiadna stanica.'
        : 'Táto kategória zatiaľ neobsahuje žiadne overené služby.';
      return;
    }

    const statusLabels = {
      missing_logo: 'Logo ešte chýba',
      unresolved: 'Stanica zatiaľ nie je spárovaná s Vhannibal',
      ambiguous: 'Nejednoznačná DVB referencia',
      unverified_frequency: 'Čaká na overenie frekvencie',
      frequency_mismatch: 'Nesúlad frekvencie – nepriraďovať'
    };
    logoGrid.innerHTML = rows.map(channel => {
      const primary = primaryFile(channel);
      const available = Boolean(primary);
      const caption = available
        ? escapeHtml(channel.satellite_position || channel.position || '')
        : escapeHtml(statusLabels[channel.status] || 'Bez hotového piconu');
      return (
        '<article class="logo-card'+(available?'':' unavailable')+'" '+
          (available ? 'tabindex="0" role="button" ' : '')+
          'aria-label="'+escapeHtml(channel.name)+(available?' – otvoriť logo':' – bez loga')+'">'+
          '<div class="logo-preview">'+
            (available
              ? '<img src="picons/'+encodeURIComponent(primary)+'?v='+piconVersion+'" '+
                  'alt="'+escapeHtml(channel.name)+'" loading="lazy">'
              : '<span class="logo-placeholder">PICON<br>NEDOSTUPNÝ</span>')+
          '</div>'+
          '<div class="logo-meta">'+
            '<h3>'+escapeHtml(channel.name)+'</h3>'+
            '<span>'+caption+'</span>'+
            (channel.fastscan ? '<span>FastScan '+Number(channel.fastscan)+'</span>' : '')+
          '</div>'+
        '</article>'
      );
    }).join('');

    const renderedRows = rows.filter(primaryFile);
    logoGrid.querySelectorAll('.logo-card[role="button"]').forEach((card, index) => {
      const channel = renderedRows[index];
      const open = () => openLogo(channel);
      card.addEventListener('click', open);
      card.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          open();
        }
      });
    });
  }

  function openLogo(channel) {
    const primary = primaryFile(channel);
    if (!primary) return;

    modalImage.src = 'picons/' + encodeURIComponent(primary) + '?v=' + piconVersion;
    modalImage.alt = channel.name || '';
    modalTitle.textContent = channel.name || '';
    modalRef.textContent = channel.service_reference || '';
    const active = providerById.get(activeProviderId);
    modalGroup.textContent = active?.group === 'operator'
      ? active.name + ' · ' + (channel.position || '')
      : channel.satellite_position || '';

    modalDownloads.innerHTML = (channel.files || []).map(file =>
      '<a href="picons/'+encodeURIComponent(file)+'" download>'+
        'Stiahnuť '+escapeHtml(file.split('_')[2] || 'picon')+
      '</a>'
    ).join('');

    modal.hidden = false;
    document.body.classList.add('modal-open');
  }

  function closeLogo() {
    modal.hidden = true;
    modalImage.src = '';
    document.body.classList.remove('modal-open');
  }

  operatorSearch.addEventListener('input', renderLogos);
  modalClose.addEventListener('click', closeLogo);
  modalBackdrop.addEventListener('click', closeLogo);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !modal.hidden) closeLogo();
  });

  renderOperators();
  renderActiveProvider();
  // The public and administrator views use the same durable history file.
  const changeList = document.querySelector('#publicChangeList');
  const changeStatus = document.querySelector('#publicChangeStatus');
  const changeProvider = document.querySelector('#publicChangeProvider');
  const changeLabels = {
    added: 'Nová stanica',
    removed: 'Odstránená služba',
    renamed: 'Premenovanie',
    tuning_changed: 'Zmena naladenia',
    metadata_changed: 'Zmena parametrov',
    catalogue_added: 'Prvý import katalógu'
  };
  fetch('catalogue-changes.json?v=' + cacheToken, { cache: 'no-store' })
    .then(response => {
      if (!response.ok) throw new Error('História nie je dostupná');
      return response.json();
    })
    .then(data => {
      const events = Array.isArray(data.events) ? data.events : [];
      const providerNames = new Map(events.map(event =>
        [event.provider, event.provider_name || event.provider]));
      [...providerNames].sort((a,b)=>String(a[1]).localeCompare(String(b[1]), 'sk'))
        .forEach(([id, name]) => changeProvider.add(new Option(name, id)));
      function renderHistory() {
        const filtered = events.filter(event =>
          !changeProvider.value || event.provider === changeProvider.value);
        changeStatus.textContent = filtered.length
          ? filtered.length + ' zmien · najnovšie záznamy navrchu'
          : 'Zatiaľ nie sú zaznamenané zmeny oproti predchádzajúcej úspešnej synchronizácii.';
        changeList.replaceChildren();
        filtered.slice(0, 60).forEach(event => {
          const card = document.createElement('article');
          card.className = 'change-history-entry';
          const kind = document.createElement('span');
          kind.textContent = changeLabels[event.kind] || event.kind;
          const heading = document.createElement('strong');
          heading.textContent = event.name || 'Stanica';
          const provider = document.createElement('span');
          provider.textContent = event.provider_name || event.provider || '';
          const detail = document.createElement('p');
          detail.textContent = event.kind === 'renamed' ? 'Pôvodne: ' + (event.old_name || '')
            : event.kind === 'catalogue_added' ? 'Načítaných staníc: ' + (event.count || 0)
            : event.kind === 'tuning_changed' ? 'Aktualizovaná service reference'
            : '';
          const time = document.createElement('time');
          time.textContent = event.at ? new Date(event.at).toLocaleString('sk-SK') : '';
          card.append(kind, heading, provider, detail, time);
          changeList.append(card);
        });
      }
      changeProvider.addEventListener('change', renderHistory);
      renderHistory();
    })
    .catch(() => { changeStatus.textContent = 'História aktualizácií momentálne nie je dostupná.'; });

  } catch (error) {
    console.error('Picon Hub: verejný katalóg sa nepodarilo načítať', error);
    const list = document.querySelector('#operatorList');
    const empty = document.querySelector('#operatorEmpty');
    const grid = document.querySelector('#logoGrid');
    if (list) list.textContent = 'Katalóg sa nepodarilo načítať. Obnov stránku alebo to skús neskôr.';
    if (grid) grid.replaceChildren();
    if (empty) {
      empty.textContent = 'Dátové súbory sú dočasne nedostupné; žiadne neoverené picony nezobrazujeme.';
      empty.hidden = false;
    }
  }
})();
