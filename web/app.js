(async () => {
  // Always read the current deployment instead of a cached older catalogue.
  const cacheToken = Date.now();
  const [index, version, providerCatalog] = await Promise.all([
    fetch('index.json?v=' + cacheToken, { cache: 'no-store' }).then(r => r.json()),
    fetch('version.json?v=' + cacheToken, { cache: 'no-store' }).then(r => r.json()),
    fetch('providers.json?v=' + cacheToken, { cache: 'no-store' })
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

  const providers = providerCatalog.providers || [];
  const providerById = new Map(providers.map(provider => [provider.id, provider]));

  let activeProviderId =
    providers.find(provider => Number(provider.curated_channel_count || 0) > 0)?.id ||
    providers[0]?.id ||
    null;

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[char]));
  }

  function providerChannels(providerId) {
    return index.channels.filter(
      channel =>
        String(channel.provider_group || '').toLowerCase() ===
        String(providerId || '').toLowerCase()
    );
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
      operatorList.innerHTML = '<div class="empty-state">Žiadni operátori.</div>';
      return;
    }

    operatorList.innerHTML = providers.map(provider => {
      const { expected, curated, complete } = providerProgress(provider);
      const state = complete ? 'complete' : (curated > 0 ? 'progress' : '');
      return (
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
    const { expected, curated, complete } = providerProgress(provider);

    if (complete && provider.package) {
      operatorPackageArea.innerHTML =
        '<a class="package-download" href="'+escapeHtml(provider.package)+'" download>'+
          'Stiahnuť kompletný ZIP · '+curated+' staníc'+
        '</a>';
      return;
    }

    operatorPackageArea.innerHTML =
      '<div class="package-waiting">'+
        'Kompletný ZIP až po dokončení · chýba '+
        Math.max(0, expected - curated)+' staníc'+
      '</div>';
  }

  function renderActiveProvider() {
    const provider = providerById.get(activeProviderId);
    if (!provider) {
      operatorTitle.textContent = 'Žiadny operátor';
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
        ? 'Pre toto vyhľadávanie sa nenašlo žiadne logo.'
        : 'Tento operátor zatiaľ nemá žiadne hotové logá.';
      return;
    }

    logoGrid.innerHTML = rows.map(channel => {
      const primary = primaryFile(channel);
      if (!primary) return '';
      return (
        '<article class="logo-card" tabindex="0" role="button" '+
          'aria-label="Otvoriť '+escapeHtml(channel.name)+'">'+
          '<div class="logo-preview">'+
            '<img src="picons/'+encodeURIComponent(primary)+'?v='+piconVersion+'" '+
              'alt="'+escapeHtml(channel.name)+'" loading="lazy">'+
          '</div>'+
          '<div class="logo-meta">'+
            '<h3>'+escapeHtml(channel.name)+'</h3>'+
            '<span>'+escapeHtml(channel.satellite_position || '')+'</span>'+
          '</div>'+
        '</article>'
      );
    }).join('');

    const renderedRows = rows.filter(primaryFile);
    logoGrid.querySelectorAll('.logo-card').forEach((card, index) => {
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
    modalGroup.textContent = providerById.get(channel.provider_group)?.name || channel.provider_group || '';

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
})();
