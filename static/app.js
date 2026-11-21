(() => {
  'use strict';

  const $ = (selector) => document.querySelector(selector);
  const state = { schema: {}, config: {}, project: {}, projectKey: 'default', view: 'VIS', dirty: false, ratio: 0.70, zoom: 1, selection: null, selectedRun: null, runDetailsLoaded: null };
  const viewInfo = {
    VIS: ['ACQUISITION', 'Images VIS', 'Inspectez la séquence et choisissez l’image de référence.', 'Aucune image chargée', 'Choisissez un dossier VIS dans les paramètres pour afficher la séquence.'],
    ROI: ['GÉOMÉTRIE', 'ROI / maillage', 'Définissez la région utile et contrôlez le maillage.', 'Aucun masque chargé', 'Choisissez un fichier ROI puis maillez la région sur l’image VIS.'],
    Échelle: ['ÉTALONNAGE', 'Échelle', 'Mesurez une longueur connue sur la VIS.', 'Échelle physique', 'Placez un segment sur la référence VIS.'],
    'Réglages DIC': ['CORRÉLATION', 'Réglages DIC', 'Réglez le solveur DIC.', 'Réglages DIC', 'Ajustez les paramètres dans le panneau droit.'],
    Thermique: ['CORRESPONDANCE', 'Thermique', 'Inspectez les images et la transformation VIS–TH.', 'Aucune image thermique', 'Configurez le dossier des images thermiques dans le panneau.'],
    Synchro: ['SYNCHRONISATION', 'Synchro', 'Vérifiez les temps acquis et les images thermiques associées.', 'Aucune séquence temporelle', 'Les instants réels VIS et TH seront présentés ici.'],
    'Job Manager': ['CALCUL', 'Job Manager', 'Lancez et suivez les calculs.', 'Aucun calcul pour cette étude', 'Lancez un calcul pour créer un run.'],
    Résultats: ['CHAMPS', 'Résultats', 'Explorez les champs et les historiques aux nœuds.', 'Aucun résultat disponible', 'Terminez un calcul pour explorer ses champs.'],
    Export: ['PARAVIEW', 'Export', 'Préparez les champs, unités et séries à exporter.', 'Aucun export préparé', 'Les options d’export sont disponibles dans les paramètres.']
  };
  const groups = { VIS: 'Images VIS', ROI: 'ROI / maillage', Échelle: 'Échelle', 'Réglages DIC': 'Réglages DIC', Thermique: 'Thermique', Synchro: 'Synchro', 'Job Manager': 'Job Manager', Résultats: 'Résultats', Export: 'Export' };

  function setDirty(dirty = true) {
    state.dirty = dirty;
    scheduleReadiness();
    const node = $('#save-state');
    node.classList.toggle('dirty', dirty);
    node.classList.toggle('error', false);
    node.innerHTML = `<i></i>${dirty ? 'Modifications non enregistrées' : 'Enregistré'}`;
  }
  function setError(message) {
    const node = $('#save-state'); node.classList.add('error'); node.innerHTML = `<i></i>${message}`;
  }
  function notify(title, message) {
    $('#dialog-title').textContent = title; $('#dialog-copy').textContent = message;
    $('#notice-dialog').showModal();
  }
  async function api(path, options = {}) {
    const response = await fetch(path, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || body.message || `Erreur HTTP ${response.status}`);
    return body;
  }
  function flattenSchema(payload) {
    const fields = payload.fields || payload.schema || payload;
    return Object.entries(fields).filter(([, value]) => value && typeof value === 'object' && !Array.isArray(value) && ('default' in value || 'label' in value));
  }
  function valueAt(path) { return path.split('.').reduce((obj, key) => obj && obj[key], state.config); }
  function putValue(path, value) {
    const parts = path.split('.'); let target = state.config;
    for (const part of parts.slice(0, -1)) target = target[part] ||= {};
    target[parts.at(-1)] = value;
  }
  function htmlEscape(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  const explorer = { options: null, data: null, selected: null, resolve: null, requestId: 0 };
  function explorerUpdateChoice() {
    const mode = explorer.options.mode;
    const data = explorer.data;
    const validName = /^[^/\\]+$/.test($('#file-name').value.trim()) && !['.', '..'].includes($('#file-name').value.trim());
    const canChoose = mode === 'new_directory' ? Boolean(data && validName) :
      mode === 'study' ? Boolean(explorer.selected?.is_study || explorer.selected?.is_study_config || (!explorer.selected && data?.is_study)) :
      mode === 'directory' ? Boolean(data && (!explorer.selected || explorer.selected.is_dir)) :
      Boolean(explorer.selected && !explorer.selected.is_dir);
    $('#file-choose').disabled = !canChoose;
    $('#file-selection').textContent = mode === 'new_directory'
      ? (data?.path || 'Choisissez un dossier parent.')
      : explorer.selected?.path || data?.path || 'Choisissez un élément.';
  }
  async function explorerLoad(path, append = false) {
    const mode = explorer.options.mode;
    const kind = explorer.options.kind || (mode === 'study' ? 'study' : 'directory');
    const offset = append ? explorer.data.entries.length : 0;
    const params = new URLSearchParams({ path: path || '', kind, query: $('#file-search').value, offset: String(offset) });
    const requestId = ++explorer.requestId;
    try {
      const data = await api('/api/filesystem?' + params);
      if (requestId !== explorer.requestId) return;
      if (append) data.entries = [...explorer.data.entries, ...data.entries];
      explorer.data = data;
      explorer.selected = null;
      $('#file-path').value = data.path;
      $('#file-up').disabled = !data.parent;
      const list = $('#file-list'); list.replaceChildren();
      for (const entry of data.entries) {
        const button = document.createElement('button');
        button.type = 'button'; button.className = 'file-entry';
        button.setAttribute('role', 'option'); button.setAttribute('aria-selected', 'false');
        button.innerHTML = '<span class="file-entry-icon">' + (entry.is_dir ? '▤' : '▧') +
          '</span><span class="file-entry-name"></span><span class="file-entry-type">' +
          (entry.is_study ? 'Étude' : entry.is_study_config ? 'Configuration d’étude' : entry.is_dir ? 'Dossier' : 'Fichier') + '</span>';
        button.querySelector('.file-entry-name').textContent = entry.name;
        button.addEventListener('click', () => {
          explorer.selected = entry;
          list.querySelectorAll('.file-entry').forEach(node => node.setAttribute('aria-selected', String(node === button)));
          explorerUpdateChoice();
        });
        button.addEventListener('dblclick', () => { if (entry.is_study && mode === 'study') { explorer.selected = entry; explorerUpdateChoice(); explorerChoose(); } else if (entry.is_dir) explorerLoad(entry.path); else if (mode === 'study' && entry.is_study_config) { explorer.selected = entry; explorerUpdateChoice(); explorerChoose(); } else if (mode !== 'directory' && mode !== 'study' && mode !== 'new_directory') explorerChoose(); });
        button.addEventListener('keydown', event => {
          if (event.key !== 'Enter' && event.key !== 'ArrowRight') return;
          if (entry.is_dir && !(mode === 'study' && entry.is_study && event.key === 'Enter')) { event.preventDefault(); explorerLoad(entry.path); }
          else if (event.key === 'Enter' && ((mode === 'study' && (entry.is_study || entry.is_study_config)) || (mode !== 'directory' && mode !== 'study' && mode !== 'new_directory'))) {
            event.preventDefault(); explorer.selected = entry; explorerUpdateChoice(); explorerChoose();
          }
        });
        list.append(button);
      }
      if (!data.entries.length) list.innerHTML = '<div class="file-empty">Aucun élément correspondant.</div>';
      $('#file-more').hidden = !data.has_more;
      $('#file-more').textContent = 'Afficher la suite (' + data.entries.length + ' / ' + data.total + ')';
      explorerUpdateChoice();
    } catch (error) {
      if (requestId !== explorer.requestId) return;
      explorer.data = null; explorer.selected = null;
      $('#file-choose').disabled = true; $('#file-more').hidden = true;
      $('#file-selection').textContent = error.message;
      $('#file-list').replaceChildren();
    }
  }
  function explorerChoose() {
    if ($('#file-choose').disabled) return;
    const mode = explorer.options.mode;
    const path = mode === 'new_directory'
      ? explorer.data.path.replace(/\/$/, '') + '/' + $('#file-name').value.trim()
      : explorer.selected?.is_study_config ? explorer.data.path : explorer.selected?.path || explorer.data.path;
    explorer.result = path;
    $('#file-dialog').close();
  }
  function openExplorer(options) {
    return new Promise(resolve => {
      clearTimeout(searchTimer);
      explorer.options = options; explorer.data = null; explorer.selected = null; explorer.result = null; explorer.resolve = resolve;
      $('#file-dialog-title').textContent = options.title || 'Choisir un fichier';
      $('#file-choose').disabled = true; $('#file-more').hidden = true;
      $('#file-list').replaceChildren(); $('#file-selection').textContent = 'Chargement du dossier…';
      $('#file-search').value = ''; $('#file-name').value = options.suggestedName || '';
      $('#file-name-row').hidden = options.mode !== 'new_directory';
      $('#file-choose').textContent = options.mode === 'new_directory' ? 'Créer ici' : options.mode === 'directory' ? 'Utiliser ce dossier' : 'Sélectionner';
      $('#file-dialog').showModal();
      explorerLoad(options.initialPath || state.project.folder || '');
    });
  }
  $('#file-dialog').addEventListener('close', () => { clearTimeout(searchTimer); explorer.requestId++; const resolve = explorer.resolve; explorer.resolve = null; resolve?.(explorer.result); });
  $('#file-close').addEventListener('click', () => $('#file-dialog').close());
  $('#file-cancel').addEventListener('click', () => $('#file-dialog').close());
  $('#file-choose').addEventListener('click', explorerChoose);
  $('#file-up').addEventListener('click', () => explorer.data?.parent && explorerLoad(explorer.data.parent));
  $('#file-go').addEventListener('click', () => explorerLoad($('#file-path').value));
  $('#file-path').addEventListener('keydown', event => { if (event.key === 'Enter') explorerLoad(event.target.value); });
  $('#file-name').addEventListener('input', explorerUpdateChoice);
  $('#file-more').addEventListener('click', () => explorerLoad(explorer.data.path, true));
  let searchTimer;
  $('#file-search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => explorerLoad(explorer.data?.path || ''), 250); });
  async function browseField(path) {
    const meta = state.schema.fields[path];
    const mode = meta.picker || meta.type;
    const title = meta.label;
    const current = valueAt(path);
    const initialPath = path === 'paths.reference_image'
      ? (valueAt('paths.visible_dir') || state.project.folder)
      : mode !== 'directory' && current && current.includes('/')
        ? current.slice(0, current.lastIndexOf('/')) || '/'
        : current || state.project.folder;
    const result = await openExplorer({ mode: mode === 'directory' ? 'directory' : 'file',
      kind: mode === 'file' ? 'any' : mode, title, initialPath });
    if (!result) return;
    if (path === 'paths.reference_image') {
      const slash = result.lastIndexOf('/');
      const oldDirectory = valueAt('paths.visible_dir');
      const newDirectory = result.slice(0, slash) || '/';
      putValue('paths.visible_dir', newDirectory);
      putValue(path, result.slice(slash + 1));
      reflectField('paths.visible_dir', newDirectory);
      if (oldDirectory !== newDirectory) {
        putValue('paths.excluded_images', []);
        putValue('paths.visible_pattern', '');
        reflectField('paths.visible_pattern', '');
      }
    } else {
      putValue(path, result);
    }
    if (path === 'registration.file') { putValue('registration.approved', false); reflectField('registration.approved', false); }
    if (path === 'paths.visible_dir') {
      putValue('paths.excluded_images', []);
      putValue('paths.visible_pattern', ''); reflectField('paths.visible_pattern', '');
      putValue('paths.reference_image', ''); reflectField('paths.reference_image', '');
    }
    reflectField(path, valueAt(path)); setDirty();
    if (path === 'paths.visible_dir') renderVisibleSeries(true);
    if (path === 'thermal.image_dir') { putValue('thermal.excluded_images', []); putValue('thermal.image_pattern', ''); reflectField('thermal.image_pattern', ''); renderThermalSeries(true); loadThermal(); }
    if (path === 'roi.initial_mask') loadROI();
    if (path === 'paths.reference_image') { renderVisibleSeries(); loadVisible(); }
    $('#config-message').textContent = 'Chemin sélectionné. L’aperçu VIS se met à jour automatiquement ; enregistrez pour conserver ce choix.';
  }
  function controlFor(path, meta, value) {
    const attrs = `data-path="${htmlEscape(path)}" ${meta.readonly ? 'disabled' : ''} aria-label="${htmlEscape(meta.label || path)}"`;
    if (Array.isArray(meta.choices) && meta.choices.length) {
      const multiple = meta.type === 'array';
      return `<select ${attrs} ${multiple ? 'multiple' : ''}>${meta.choices.map(option => `<option value="${htmlEscape(option)}" ${(multiple ? value.includes(option) : option === value) ? 'selected' : ''}>${htmlEscape(option)}</option>`).join('')}</select>`;
    }
    if (meta.type === 'boolean') return `<input type="checkbox" ${attrs} ${value ? 'checked' : ''}>`;
    if (meta.type === 'integer' || meta.type === 'float') return `<input type="number" ${attrs} value="${htmlEscape(value)}" ${meta.minimum != null ? `min="${htmlEscape(meta.minimum)}"` : ''} step="${meta.type === 'integer' ? '1' : 'any'}">`;
    return `<input type="text" ${attrs} value="${htmlEscape(meta.type === 'array' ? JSON.stringify(value) : value)}">`;
  }
  function fieldView(path, meta) {
    if (meta.hidden) return null;
    return state.config.project?.mode === 'dic' && meta.view_dic ? meta.view_dic : meta.view;
  }
  function readControl(input, meta) {
    if (meta.type === 'boolean') return input.checked;
    if (meta.type === 'integer' || meta.type === 'float') return input.value === '' ? '' : Number(input.value);
    if (meta.type === 'array') {
      if (input.multiple) return Array.from(input.selectedOptions, option => option.value);
      try { return JSON.parse(input.value); } catch { return input.value; }
    }
    return input.value;
  }
  let seriesRequestId = 0;
  function applyVisibleSeries(series) {
    putValue('paths.excluded_images', []);
    putValue('paths.visible_pattern', series.pattern);
    putValue('paths.reference_image', series.first_image);
    if (series.frame_regex) putValue('time.visible_frame_regex', series.frame_regex);
    if (!/\.tiff?$/i.test(series.first_image)) putValue('time.visible_source', 'filename');
    reflectField('paths.visible_pattern', series.pattern);
    reflectField('paths.reference_image', series.first_image);
    setDirty();
    $('#config-message').textContent = 'Série et référence sélectionnées. La séquence s’affiche ; enregistrez pour conserver ce choix.';
    renderVisibleSeries();
    loadVisible();
  }
  async function renderVisibleSeries(autoSelect = false) {
    const panel = $('#visible-series');
    if (!panel || state.view !== 'VIS') return;
    const directory = valueAt('paths.visible_dir');
    const requestId = ++seriesRequestId;
    if (!directory) { panel.innerHTML = '<p class="loading-state">Choisissez un dossier VIS pour détecter les séries.</p>'; return; }
    panel.innerHTML = '<p class="loading-state">Recherche des séries d’images…</p>';
    try {
      const data = await api('/api/visible/series?directory=' + encodeURIComponent(directory));
      if (requestId !== seriesRequestId || state.view !== 'VIS') return;
      if (autoSelect && data.series.length === 1) {
        const candidate = data.series[0];
        putValue('paths.excluded_images', []);
        putValue('paths.visible_pattern', candidate.pattern);
        putValue('paths.reference_image', candidate.first_image);
        if (candidate.frame_regex) putValue('time.visible_frame_regex', candidate.frame_regex);
        if (!/\.tiff?$/i.test(candidate.first_image)) putValue('time.visible_source', 'filename');
        reflectField('paths.visible_pattern', candidate.pattern);
        reflectField('paths.reference_image', candidate.first_image);
        setDirty();
        loadVisible();
      }
      panel.replaceChildren();
      const heading = document.createElement('div');
      heading.className = 'series-heading';
      heading.innerHTML = '<strong>Séries détectées</strong><span>' + data.image_count + ' image(s) dans le dossier</span>';
      panel.append(heading);
      if (data.series.length > 1 && !data.series.some(series => series.pattern === valueAt('paths.visible_pattern'))) {
        const guidance = document.createElement('p'); guidance.className = 'series-guidance';
        guidance.textContent = 'Plusieurs séries trouvées : choisissez celle à analyser.';
        panel.append(guidance);
      }
      if (!data.series.length) {
        const empty = document.createElement('p'); empty.className = 'loading-state';
        empty.textContent = 'Aucune image prise en charge dans ce dossier.'; panel.append(empty); return;
      }
      for (const series of data.series) {
        const button = document.createElement('button'); button.type = 'button';
        button.className = 'series-option';
        button.classList.toggle('selected', series.pattern === valueAt('paths.visible_pattern'));
        const label = document.createElement('span');
        const count = document.createElement('strong'); count.textContent = series.count + ' image(s)';
        const pattern = document.createElement('code'); pattern.textContent = series.pattern;
        label.append(count, pattern);
        const sample = document.createElement('small'); sample.textContent = 'Référence proposée : ' + series.first_image;
        button.append(label, sample);
        button.addEventListener('click', () => applyVisibleSeries(series));
        panel.append(button);
      }
    } catch (error) {
      if (requestId === seriesRequestId) panel.textContent = 'Détection impossible : ' + error.message;
    }
  }
  let thermalSeriesRequestId=0;
  function applyThermalSeries(series){
    putValue('thermal.excluded_images', []);
    putValue('thermal.image_pattern', series.pattern);
    if(series.frame_regex)putValue('thermal.frame_regex',series.frame_regex);
    reflectField('thermal.image_pattern',series.pattern);
    reflectField('thermal.frame_regex',valueAt('thermal.frame_regex'));
    setDirty();
    $('#config-message').textContent='Série thermique sélectionnée. Enregistrez pour conserver ce choix.';
    renderThermalSeries();loadThermal();
  }
  async function renderThermalSeries(autoSelect=false){
    const panel=$('#thermal-series');if(!panel||state.view!=='Thermique')return;
    const directory=valueAt('thermal.image_dir'),requestId=++thermalSeriesRequestId;
    if(!directory){panel.innerHTML='<p class="loading-state">Choisissez un dossier TH pour détecter les séries TIFF.</p>';return;}
    panel.innerHTML='<p class="loading-state">Recherche des séries thermiques…</p>';
    try{
      const data=await api('/api/thermal/series?directory='+encodeURIComponent(directory));
      if(requestId!==thermalSeriesRequestId||state.view!=='Thermique')return;
      if(autoSelect&&data.series.length===1){
        const candidate=data.series[0];
        putValue('thermal.excluded_images',[]);
        putValue('thermal.image_pattern',candidate.pattern);
        if(candidate.frame_regex)putValue('thermal.frame_regex',candidate.frame_regex);
        reflectField('thermal.image_pattern',candidate.pattern);
        reflectField('thermal.frame_regex',valueAt('thermal.frame_regex'));
        setDirty();loadThermal();
      }
      panel.replaceChildren();
      const heading=document.createElement('div');heading.className='series-heading';
      heading.innerHTML='<strong>Séries TH détectées</strong><span>'+data.image_count+' TIFF dans le dossier</span>';
      panel.append(heading);
      if(data.series.length>1&&!data.series.some(series=>series.pattern===valueAt('thermal.image_pattern'))){
        const guidance=document.createElement('p');guidance.className='series-guidance';
        guidance.textContent='Plusieurs séries trouvées : choisissez celle à utiliser pour la fusion.';panel.append(guidance);
      }
      if(!data.series.length){const empty=document.createElement('p');empty.className='loading-state';empty.textContent='Aucun TIFF thermique dans ce dossier.';panel.append(empty);return;}
      for(const series of data.series){
        const button=document.createElement('button');button.type='button';button.className='series-option';
        button.classList.toggle('selected',series.pattern===valueAt('thermal.image_pattern'));
        const label=document.createElement('span'),count=document.createElement('strong'),pattern=document.createElement('code');
        count.textContent=series.count+' image(s)';pattern.textContent=series.pattern;label.append(count,pattern);
        const sample=document.createElement('small');sample.textContent='Première acquisition : '+series.first_image;
        button.append(label,sample);button.addEventListener('click',()=>applyThermalSeries(series));panel.append(button);
      }
    }catch(error){if(requestId===thermalSeriesRequestId)panel.textContent='Détection impossible : '+error.message;}
  }
  function renderFields() {
    const host = $('#field-groups'); host.replaceChildren();
    const entries = flattenSchema(state.schema);
    if (!entries.length) { host.innerHTML = '<p class="loading-state">Le schéma de configuration n’est pas disponible.</p>'; return; }
    const byView = new Map();
    for (const [path, meta] of entries) {
      const view = fieldView(path, meta);
      if (!view || view !== state.view) continue;
      if ((state.schema.thermal_sections || []).includes(path.split('.')[0]) && state.config.project?.mode !== 'dic_thermal') continue;
      const group = meta.group || view;
      if (!byView.has(group)) byView.set(group, []);
      byView.get(group).push([path, meta]);
    }
    for (const [view, fields] of byView) {
      fields.sort((a, b) => (a[1].order || 0) - (b[1].order || 0));
      const section = document.createElement('section'); section.className = 'field-group'; section.dataset.group = view;
      section.innerHTML = `<h3 class="group-title">${htmlEscape(view)}</h3>`;
      for (const [path, meta] of fields) {
        const value = valueAt(path) ?? meta.default ?? '';
        const card = document.createElement('article'); card.className = 'field-card';
        card.innerHTML = `<div class="field-label-row"><label class="field-label" for="field-${path.replace(/[^a-z0-9]/gi,'-')}">${htmlEscape(meta.label || path)}</label><span class="field-help" tabindex="0" data-help="${htmlEscape(`${meta.help || 'Aide non renseignée.'} Clé TOML : ${path}.`)}" aria-label="Aide pour ${htmlEscape(meta.label || path)}">i</span><span class="field-default">Défaut : ${htmlEscape(Array.isArray(meta.default) ? JSON.stringify(meta.default) : (meta.default ?? 'à renseigner'))}</span></div><div class="field-control">${controlFor(path, meta, value)}</div><div class="field-meta"><span>${htmlEscape(meta.unit || path)}</span><button class="field-reset" type="button" data-reset="${htmlEscape(path)}" ${meta.readonly ? 'disabled' : ''}>Réinitialiser</button></div>`;
        const input = card.querySelector('[data-path]'); if (input) input.id = `field-${path.replace(/[^a-z0-9]/gi,'-')}`;
        if (path === 'dic.roi_erosion_px') {
          const note = document.createElement('p');
          note.className = 'inline-status';
          note.textContent = 'Exclut une bande aux bords et aux trous du critère photométrique. Maillage inchangé. 0 = désactivé ; par exemple 3 px VIS d’origine.';
          card.append(note);
        }
        if (meta.type === 'directory' || meta.type === 'file') {
          const browse = document.createElement('button');
          browse.type = 'button'; browse.className = 'field-browse'; browse.disabled = Boolean(meta.readonly);
          browse.textContent = 'Parcourir…'; browse.setAttribute('aria-label', 'Parcourir : ' + (meta.label || path));
          browse.addEventListener('click', () => browseField(path));
          card.querySelector('.field-control').append(browse);
        }
        section.append(card);
      }
      host.append(section);
    }
    if (state.view === 'Thermique') {
      const panel = document.createElement('section');
      panel.id = 'thermal-series'; panel.className = 'visible-series';
      const folderCard = host.querySelector('[data-path="thermal.image_dir"]')?.closest('.field-card');
      if (folderCard) folderCard.after(panel); else host.prepend(panel);
      renderThermalSeries(!valueAt('thermal.image_pattern'));
    }
    if (state.view === 'VIS') {
      const panel = document.createElement('section');
      panel.id = 'visible-series'; panel.className = 'visible-series';
      const folderCard = host.querySelector('[data-path="paths.visible_dir"]')?.closest('.field-card');
      if (folderCard) folderCard.after(panel);
      else host.prepend(panel);
      renderVisibleSeries(!valueAt('paths.reference_image'));
    }
    host.querySelectorAll('[data-path]').forEach(input => input.addEventListener('change', () => {
      const path = input.dataset.path;
      const val = readControl(input, state.schema.fields[path]);
      putValue(path, val); setDirty();
      if (path === 'paths.visible_dir') {
        putValue('paths.excluded_images', []);
        putValue('paths.visible_pattern', ''); reflectField('paths.visible_pattern', '');
        putValue('paths.reference_image', ''); reflectField('paths.reference_image', '');
        renderVisibleSeries(true);
        loadVisible();
      } else if (path === 'paths.visible_pattern' || path === 'paths.reference_image') {
        if (path === 'paths.visible_pattern') putValue('paths.excluded_images', []);
        loadVisible();
      } else if (path === 'thermal.image_dir') {
        putValue('thermal.excluded_images', []);
        putValue('thermal.image_pattern', ''); reflectField('thermal.image_pattern', '');
        renderThermalSeries(true); loadThermal();
      } else if (path === 'thermal.image_pattern') {
        putValue('thermal.excluded_images', []); renderThermalSeries(); loadThermal();
      } else if (state.view === 'Synchro' && (path.startsWith('synchronization.') || path === 'time.visible_fps' || path === 'thermal.thermal_fps')) {
        loadSynchronization();
      } else if (path.startsWith('thermal.')) {
        loadThermal();
      } else if (path === 'dic.roi_erosion_px') {
        updatePhotometricROI();
      } else if (path === 'roi.initial_mask') {
        loadROI();
      } else if (state.view === 'Échelle' && path.startsWith('scale.')) {
        if (path === 'scale.segment_length_mm') {
          const length = $('#segment-length-mm'); if (length) length.value = val;
          state.config.scale.confirmed = false;
          reflectField('scale.confirmed', false);
        }
        if (path === 'scale.segment_xy_px') loadDicView();
        else updateScalePreview();
      }
    }));
    host.querySelectorAll('[data-reset]').forEach(button => button.addEventListener('click', () => {
      const meta = new Map(entries).get(button.dataset.reset); if (!meta) return;
      const path = button.dataset.reset;
      putValue(path, structuredClone(meta.default));
      if (path === 'thermal.image_dir') { putValue('thermal.excluded_images', []); putValue('thermal.image_pattern', ''); }
      if (path === 'thermal.image_pattern') putValue('thermal.excluded_images', []);
      renderFields(); setDirty();
      if (path === 'dic.roi_erosion_px') updatePhotometricROI();
      if (state.view === 'Thermique' && path.startsWith('thermal.')) {
        if (path === 'thermal.image_dir') renderThermalSeries(true);
        loadThermal();
      }
      if (state.view === 'Synchro') loadSynchronization();
      if (state.view === 'Échelle' && path.startsWith('scale.')) {
        const length = $('#segment-length-mm');
        if (length) length.value = state.config.scale.segment_length_mm;
        if (path === 'scale.segment_xy_px') loadDicView();
        else updateScalePreview();
      }
    }));
  }
  function normalizeProject(payload) {
    state.project = payload || {};
    state.projectKey = payload.folder || payload.path || payload.name || 'default';
    state.selectedRun = null;
    resultNodes.clear(); historyCache.clear(); colorBounds.clear(); resultSections.clear(); historyRequest++; sectionRequest++;
    state.config = structuredClone(payload.config || payload.settings || payload);
    if (!state.config.project) state.config.project = { mode: 'dic', name: 'Nouvelle étude' };
    $('#project-name').textContent = payload.name || state.config.project.name || 'Nouvelle étude';
    $('#project-mode').value = state.config.project.mode || 'dic';
  }
  async function load() {
    try {
      const [schema, project] = await Promise.all([api('/api/schema'), api('/api/project')]);
      state.schema = schema; normalizeProject(project); renderFields(); setDirty(false);
    } catch (error) {
      setError('Serveur indisponible');
      $('#field-groups').innerHTML = `<div class="loading-state">Impossible de charger le projet : ${htmlEscape(error.message)}.<br><br>Vérifiez que le serveur D2IC local est démarré.</div>`;
    }
  }
  async function save() {
    try {
      const result = await api('/api/project/config', { method: 'PUT', body: JSON.stringify(state.config) });
      if (result.config) state.config = result.config;
      setDirty(false); $('#config-message').textContent = 'Configuration enregistrée.';
      $('#project-name').textContent = state.config.project.name || 'Nouvelle étude';
      if (state.view === 'VIS') loadVisible();
      if (state.view === 'Thermique') loadThermal();
      if (state.view === 'Synchro') loadSynchronization();
      return true;
    } catch (error) { setError('Erreur de sauvegarde'); $('#config-message').textContent = error.message; return false; }
  }
  function selectView(view) {
    if (view !== 'ROI') { roiEditor?.destroy(); roiEditor = null; }
    state.view = view;
    if (view !== 'Échelle') scaleResizeObserver?.disconnect();
    renderFields();
    document.querySelectorAll('.nav-item').forEach(item => { const active = item.dataset.view === view; item.classList.toggle('active', active); active ? item.setAttribute('aria-current','page') : item.removeAttribute('aria-current'); });
    const [, , , stageTitle, stageCopy] = viewInfo[view];
    $('#canvas-pane').setAttribute('aria-label', groups[view] || view);
    $('#settings-title').textContent = groups[view] || view;
    if ($('#stage-title')) $('#stage-title').textContent = stageTitle;
    if ($('#stage-copy')) $('#stage-copy').textContent = stageCopy;
    document.querySelectorAll('.thermal-nav').forEach(item => item.hidden = false);
    document.body.classList.remove('settings-open'); document.body.classList.remove('nav-open');
    loadViewContent(view);
  }
  function recordsFrom(payload) {
    if (Array.isArray(payload)) return payload;
    for (const key of ['images', 'files', 'items', 'frames', 'visible', 'thermal', 'entries', 'runs']) if (Array.isArray(payload?.[key])) return payload[key];
    return [];
  }
  function recordPath(item) { return typeof item === 'string' ? item : item.path || item.absolute_path || item.visible_path || item.file || item.filename || item.name || ''; }
  function resolveSource(path, directory) { return path && !path.startsWith('/') && !/^[A-Za-z]:[\\/]/.test(path) && directory ? `${directory.replace(/[\\/]$/, '')}/${path}` : path; }
  function imageUrl(path, full = false, visible = false, thermal = false) {
    const params = new URLSearchParams({ path });
    if (full) params.set('full', '1');
    if (visible && state.config.paths?.visible_dir) params.set('visible_dir', state.config.paths.visible_dir);
    if (thermal && state.config.thermal?.image_dir) params.set('thermal_dir', state.config.thermal.image_dir);
    return '/api/image?' + params;
  }
  function imageMarkup(path, label = 'Aperçu image', full = false, visible = false, thermal = false, id = '') {
    return path
      ? '<img class="preview-image"' + (id ? ' id="' + htmlEscape(id) + '"' : '') + ' alt="' + htmlEscape(label) + '" src="' +
        htmlEscape(imageUrl(path, full, visible, thermal)) + '">'
      : '<div class="empty-inline">Aucune image disponible</div>';
  }
  function tableMarkup(items, thermal = false, synchronization = false) {
    if (!items.length) return '<div class="empty-inline">Aucune image trouvée. Vérifiez le dossier et le motif dans les paramètres.</div>';
    const head=synchronization?'<th>#</th><th>VIS</th><th>Temps VIS (s)</th><th>TH précédente</th><th>TH suivante</th><th>α</th><th>État / cause</th>':`<th>#</th><th>Fichier</th><th>Dimensions</th><th>Temps (${thermal?'s':'s'})</th>${thermal?'<th>Trame</th>':''}`;
    const rows=items.map((it,i)=>{
      if(synchronization){const valid=it.valid?'Valide':`Absent${it.reason?` · ${it.reason}`:''}`;return `<tr data-image-path="${htmlEscape(recordPath(it))}" tabindex="0"><td>${i+1}</td><td title="${htmlEscape(it.visible_path||'')}">${htmlEscape((it.visible_path||'').split(/[\\/]/).pop()||'VIS')}</td><td>${htmlEscape(it.time_s ?? '—')}</td><td title="${htmlEscape(it.thermal_left||'')}">${htmlEscape((it.thermal_left||'—').split(/[\\/]/).pop())}</td><td title="${htmlEscape(it.thermal_right||'')}">${htmlEscape((it.thermal_right||'—').split(/[\\/]/).pop())}</td><td>${htmlEscape(it.alpha ?? '—')}</td><td>${htmlEscape(valid)}</td></tr>`;}
      return `<tr data-image-path="${htmlEscape(recordPath(it))}" tabindex="0"><td>${htmlEscape(it.frame ?? i+1)}</td><td title="${htmlEscape(recordPath(it))}">${htmlEscape((recordPath(it).split(/[\\/]/).pop()) || 'Image')}</td><td>${htmlEscape(Array.isArray(it.shape)?it.shape.join(' × '):(it.width&&it.height?`${it.width} × ${it.height}`:'—'))}</td><td>${htmlEscape(it.time_s ?? it.timestamp ?? '—')}</td>${thermal?`<td>${htmlEscape(it.frame ?? '—')}</td>`:''}</tr>`;
    }).join('');
    return `<div class="data-table-wrap"><table class="data-table"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>`;
  }
  function visibleSelectionMarkup(items, referenceName) {
    const excluded = new Set(state.config.paths?.excluded_images || []);
    const reference = referenceName.split(/[\\/]/).pop();
    const rows = items.map((it, i) => {
      const path = recordPath(it), name = path.split(/[\\/]/).pop();
      const isReference = name === reference;
      const checked = isReference || !excluded.has(name);
      return `<tr data-image-path="${htmlEscape(path)}" data-visible-index="${i}" tabindex="0" class="${checked ? '' : 'vis-excluded'}"><td><input type="checkbox" class="vis-active" data-visible-index="${i}" aria-label="Analyser ${htmlEscape(name)}" ${checked ? 'checked' : ''} ${isReference ? 'disabled title="Référence toujours requise"' : ''}></td><td>${i + 1}</td><td title="${htmlEscape(path)}">${htmlEscape(name)}${isReference ? ' · réf.' : ''}</td><td>${htmlEscape(Array.isArray(it.shape) ? it.shape.join(' × ') : '—')}</td><td>${htmlEscape(it.time_s ?? it.timestamp ?? '—')}</td></tr>`;
    }).join('');
    return `<div class="data-table-wrap"><table class="data-table"><thead><tr><th>Analyse</th><th>I</th><th>Fichier</th><th>Dimensions</th><th>Temps (s)</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }
  function attachVisibleSelection(items, referenceName) {
    const nameAt = index => recordPath(items[index]).split(/[\\/]/).pop();
    const reference = referenceName.split(/[\\/]/).pop();
    const current = () => new Set(state.config.paths?.excluded_images || []);
    const refresh = excluded => {
      excluded.delete(reference);
      putValue('paths.excluded_images', items.map((_, i) => nameAt(i)).filter(name => excluded.has(name)));
      putValue('dic.image_stride', 1);
      reflectField('dic.image_stride', 1);
      document.querySelectorAll('.vis-active').forEach(box => {
        const active = !excluded.has(nameAt(Number(box.dataset.visibleIndex)));
        box.checked = active;
        box.closest('tr').classList.toggle('vis-excluded', !active);
      });
      const selected = items.length - state.config.paths.excluded_images.length;
      $('#visible-selection-count').textContent = `${selected} / ${items.length} images actives pour l’analyse`;
      setDirty();
    };
    document.querySelectorAll('.vis-active').forEach(box => {
      box.addEventListener('click', event => event.stopPropagation());
      box.addEventListener('change', () => {
        const excluded = current(), name = nameAt(Number(box.dataset.visibleIndex));
        if (box.checked) excluded.delete(name); else excluded.add(name);
        refresh(excluded);
      });
    });
    const indexInput = $('#vis-index');
    document.querySelectorAll('[data-visible-index]').forEach(row => {
      if (row.tagName === 'TR') row.addEventListener('click', () => { indexInput.value = String(Number(row.dataset.visibleIndex) + 1); });
    });
    $('#vis-select-all').addEventListener('click', () => refresh(new Set()));
    $('#vis-one-in-n').addEventListener('click', () => {
      const n = Number($('#vis-step').value);
      if (!Number.isInteger(n) || n < 1) { $('#vis-step').reportValidity(); return; }
      refresh(new Set(items.map((_, i) => i % n ? nameAt(i) : null).filter(Boolean)));
    });
    for (const [id, before] of [['vis-before', true], ['vis-after', false]]) {
      $('#' + id).addEventListener('click', () => {
        const index = Number(indexInput.value);
        if (!Number.isInteger(index) || index < 1 || index > items.length) { indexInput.reportValidity(); return; }
        const excluded = current();
        items.forEach((_, i) => { if (before ? i < index - 1 : i > index - 1) excluded.add(nameAt(i)); });
        refresh(excluded);
      });
    }
  }
  function setStage(markup) { $('#stage-content').innerHTML = markup; }
  const imageViews = new Map();
  function setupImageViews() {
    for (const [frame, controller] of imageViews) {
      if (!frame.isConnected) { controller.destroy(); imageViews.delete(frame); }
    }
    $('#stage-content').querySelectorAll('.preview-frame, .roi-canvas-wrap, .dic-preview, .point-frame, .sync-preview-image, .run-field-frame, .dic-settings-preview').forEach(frame => {
      if (imageViews.has(frame) || !frame.querySelector('img')) return;
      const stack = frame.querySelector('[data-image-stack]');
      const layers = stack ? [stack] : [...frame.querySelectorAll('img')];
      frame.classList.add('scientific-image-frame');
      layers.forEach(layer => layer.classList.add('scientific-image-content'));
      imageViews.set(frame, window.D2ICImageZoom.attach(frame, {
        layers,
        interactive: frame.matches('.dic-preview, .point-frame, .run-field-frame, .roi-canvas-wrap')
      }));
    });
  }
  function attachImageRows(visible = false, thermal = false) {
    document.querySelectorAll('[data-image-path]').forEach(row => {
      const show = () => {
        const path = row.dataset.imagePath;
        state.selection = path;
        const img = $('#main-preview');
        if (img) {
          img.src = imageUrl(path, true, visible, thermal);
          const frame = img.closest('.preview-frame');
          frame?.__d2icZoomController?.reset();
        }
        document.querySelectorAll('[data-image-path]').forEach(el => el.classList.toggle('selected', el === row));
      };
      row.addEventListener('click', show);
      row.addEventListener('keydown', event => { if (event.key === 'Enter') show(); });
    });
  }
  let visibleRequestId = 0;
  async function loadVisible() {
    const requestId = ++visibleRequestId;
    setStage('<div class="loading-state" role="status">Chargement de la série VIS…</div>');
    try {
      const paths = state.config.paths || {}, time = state.config.time || {};
      if (!paths.visible_dir || !paths.visible_pattern) throw new Error('Choisissez un dossier et une série VIS.');
      const params = new URLSearchParams({
        directory: paths.visible_dir, pattern: paths.visible_pattern,
        source: time.visible_source || 'filename',
        frame_regex: time.visible_frame_regex || '(\\d+)',
        fps: String(time.visible_fps || 10)
      });
      const data = await api('/api/visible/inspect?' + params);
      if (requestId !== visibleRequestId || state.view !== 'VIS') return;
      const items = recordsFrom(data);
      const timingWarning = data.warnings?.find(warning => warning.kind === 'preview_only')?.message;
      const warningMarkup = timingWarning
        ? '<div class="inline-status">Images lisibles. Temps à corriger dans DIC : ' + htmlEscape(timingWarning) + '</div>'
        : '';
      const referenceName = state.config.paths?.reference_image || '';
      const reference = items.find(item => recordPath(item).split(/[\\/]/).pop() === referenceName.split(/[\\/]/).pop());
      const first = reference || items[0];
      state.selection = recordPath(first);
      $('#image-count').textContent = items.length + ' image' + (items.length === 1 ? '' : 's');
      setStage('<div class="sequence-layout"><div class="preview-frame" id="preview-frame">' +
        imageMarkup(recordPath(first), 'Image VIS sélectionnée', true, true) +
        '</div><div class="sequence-info"><span class="eyebrow">SÉRIE VIS RETENUE</span><strong>' +
        '<span id="visible-selection-count"></span></strong><p>' +
        htmlEscape(data.directory || data.visible_dir || state.config.paths?.visible_dir || 'Dossier non défini') +
        '</p><div class="visible-reference">Référence : <strong id="visible-reference-name">' +
        htmlEscape(referenceName || 'non définie') +
        '</strong><button type="button" class="button outline" id="set-visible-reference">Définir l’image affichée comme référence</button></div>' +
        warningMarkup + '<div class="vis-selection-tools"><button type="button" class="button outline" id="vis-select-all">Tout activer</button><label>1 image sur <input id="vis-step" type="number" min="1" step="1" value="2"></label><button type="button" class="button outline" id="vis-one-in-n">Appliquer</button><label>Image I <input id="vis-index" type="number" min="1" max="' + items.length + '" step="1" value="1"></label><button type="button" class="button outline" id="vis-before">Désélectionner avant I</button><button type="button" class="button outline" id="vis-after">Désélectionner après I</button></div>' + visibleSelectionMarkup(items, referenceName) + '</div></div>');
      const image = document.querySelector('.preview-image');
      if (image) image.id = 'main-preview';
      attachImageRows(true);
      attachVisibleSelection(items, referenceName);
      $('#visible-selection-count').textContent = `${items.filter(it => !new Set(state.config.paths?.excluded_images || []).has(recordPath(it).split(/[\\/]/).pop())).length} / ${items.length} images actives pour l’analyse`;
      $('#set-visible-reference')?.addEventListener('click', () => {
        const selected = state.selection;
        if (!selected) return;
        const name = selected.split(/[\\/]/).pop();
        putValue('paths.reference_image', name);
        const excluded = new Set(state.config.paths?.excluded_images || []); excluded.delete(name);
        putValue('paths.excluded_images', [...excluded]);
        reflectField('paths.reference_image', name);
        loadVisible();
        setDirty();
        $('#config-message').textContent = 'Référence sélectionnée. Enregistrez les réglages.';
      });
    } catch (error) {
      if (requestId !== visibleRequestId || state.view !== 'VIS') return;
      setStage('<div class="empty-visual"><div class="image-glyph">▧</div><span class="eyebrow">SÉQUENCE VIS</span><h2>Impossible de lire les images</h2><p>' +
        htmlEscape(error.message) + '</p><button class="button outline" data-settings>Vérifier les paramètres</button></div>');
      document.querySelector('[data-settings]')?.addEventListener('click', () => document.body.classList.add('settings-open'));
    }
  }
  function thermalSelectionMarkup(items){
    const excluded=new Set(state.config.thermal?.excluded_images||[]);
    const rows=items.map((item,index)=>{
      const path=recordPath(item),name=path.split(/[\\/]/).pop(),active=!excluded.has(name);
      return `<tr data-image-path="${htmlEscape(path)}" data-thermal-index="${index}" tabindex="0" class="${active?'':'vis-excluded'}"><td><input type="checkbox" class="th-active" data-thermal-index="${index}" aria-label="Utiliser ${htmlEscape(name)}" ${active?'checked':''}></td><td>${index+1}</td><td title="${htmlEscape(path)}">${htmlEscape(name)}</td><td>${htmlEscape(Array.isArray(item.shape)?item.shape.join(' × '):'—')}</td><td>${htmlEscape(item.time_s??'—')}</td><td>${htmlEscape(item.frame??'—')}</td></tr>`;
    }).join('');
    return `<div class="data-table-wrap"><table class="data-table"><thead><tr><th>Fusion</th><th>I</th><th>Fichier</th><th>Dimensions</th><th>Temps (s)</th><th>Trame</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }
  function attachThermalSelection(items){
    const nameAt=index=>recordPath(items[index]).split(/[\\/]/).pop();
    const current=()=>new Set(state.config.thermal?.excluded_images||[]);
    const refresh=excluded=>{
      putValue('thermal.excluded_images',items.map((_,index)=>nameAt(index)).filter(name=>excluded.has(name)));
      document.querySelectorAll('.th-active').forEach(box=>{
        const active=!excluded.has(nameAt(Number(box.dataset.thermalIndex)));
        box.checked=active;box.closest('tr').classList.toggle('vis-excluded',!active);
      });
      $('#thermal-selection-count').textContent=`${items.length-state.config.thermal.excluded_images.length} / ${items.length} images actives pour la fusion`;
      setDirty();
    };
    document.querySelectorAll('.th-active').forEach(box=>{
      box.addEventListener('click',event=>event.stopPropagation());
      box.addEventListener('change',()=>{
        const excluded=current(),name=nameAt(Number(box.dataset.thermalIndex));
        if(box.checked)excluded.delete(name);else excluded.add(name);refresh(excluded);
      });
    });
    const indexInput=$('#th-index');
    document.querySelectorAll('[data-thermal-index]').forEach(row=>{
      if(row.tagName==='TR')row.addEventListener('click',()=>{indexInput.value=String(Number(row.dataset.thermalIndex)+1);});
    });
    $('#th-select-all').addEventListener('click',()=>refresh(new Set()));
    $('#th-one-in-n').addEventListener('click',()=>{
      const n=Number($('#th-step').value);
      if(!Number.isInteger(n)||n<1){$('#th-step').reportValidity();return;}
      refresh(new Set(items.map((_,index)=>index%n?nameAt(index):null).filter(Boolean)));
    });
    for(const [id,before] of [['th-before',true],['th-after',false]]){
      $('#'+id).addEventListener('click',()=>{
        const index=Number(indexInput.value);
        if(!Number.isInteger(index)||index<1||index>items.length){indexInput.reportValidity();return;}
        const excluded=current();
        items.forEach((_,i)=>{if(before?i<index-1:i>index-1)excluded.add(nameAt(i));});
        refresh(excluded);
      });
    }
  }
  let thermalRequestId=0;
  async function loadThermal(){
    const requestId=++thermalRequestId;
    setStage('<div class="loading-state" role="status">Chargement de la série thermique…</div>');
    try{
      const th=state.config.thermal||{};
      if(!th.image_dir||!th.image_pattern)throw new Error('Choisissez un dossier et une série TH.');
      const params=new URLSearchParams({directory:th.image_dir,pattern:th.image_pattern,
        source:th.time_source||'filename',frame_regex:th.frame_regex||'(\\d+)',fps:String(th.thermal_fps||50)});
      const data=await api('/api/thermal/inspect?'+params);
      if(requestId!==thermalRequestId||state.view!=='Thermique')return;
      const items=recordsFrom(data),excluded=new Set(th.excluded_images||[]);
      const first=items.find(item=>!excluded.has(recordPath(item).split(/[\\/]/).pop()))||items[0];
      state.selection=recordPath(first);
      $('#image-count').textContent=`${items.length} image${items.length===1?'':'s'}`;
      const warning=data.warnings?.find(item=>item.kind==='preview_only')?.message;
      const warningMarkup=warning?`<div class="inline-status">Images lisibles. Temps à corriger : ${htmlEscape(warning)}</div>`:'';
      setStage(`<div class="sequence-layout"><div class="preview-frame">${imageMarkup(recordPath(first),'Image thermique sélectionnée',true,false,true)}</div><div class="sequence-info"><span class="eyebrow">SÉRIE TH RETENUE</span><strong id="thermal-selection-count"></strong><p>${htmlEscape(data.directory||th.image_dir)}</p><p>TIFF de température · ${htmlEscape(th.unit||'unité non renseignée')} · T_ref est calculée au temps de la première VIS.</p><p>Une trame TH désactivée ne peut plus encadrer un instant VIS ; les trames retenues doivent être successives pour interpoler.</p>${warningMarkup}<div class="vis-selection-tools"><button type="button" class="button outline" id="th-select-all">Tout activer</button><label>1 image sur <input id="th-step" type="number" min="1" step="1" value="2"></label><button type="button" class="button outline" id="th-one-in-n">Appliquer</button><label>Image I <input id="th-index" type="number" min="1" max="${items.length}" step="1" value="1"></label><button type="button" class="button outline" id="th-before">Désélectionner avant I</button><button type="button" class="button outline" id="th-after">Désélectionner après I</button></div>${thermalSelectionMarkup(items)}</div></div>`);
      const image=$('.preview-image');if(image)image.id='main-preview';
      attachImageRows(false,true);attachThermalSelection(items);
      $('#thermal-selection-count').textContent=`${items.filter(item=>!excluded.has(recordPath(item).split(/[\\/]/).pop())).length} / ${items.length} images actives pour la fusion`;
    }catch(error){
      if(requestId!==thermalRequestId||state.view!=='Thermique')return;
      setStage(`<div class="empty-visual"><div class="image-glyph">♨</div><span class="eyebrow">THERMIQUE</span><h2>Séquence indisponible</h2><p>${htmlEscape(error.message)}</p></div>`);
    }
  }
  const roiShapeDrafts = new Map();
  let roiEditor = null;
  function updatePhotometricROI() {
    if (roiEditor?.isActive()) { roiEditor.preview(); return; }
    const layer = $('#photometric-layer-image');
    if (!layer) return;
    const radius = Number(state.config.dic?.roi_erosion_px ?? 0);
    const status = $('#photometric-status');
    layer.dataset.ready = 'false';
    layer.hidden = true;
    if (!Number.isFinite(radius) || radius < 0) {
      status.textContent = 'Le rayon d’érosion doit être un nombre fini positif ou nul.';
      return;
    }
    const paths = state.config.paths || {};
    status.textContent = 'Actualisation de la zone photométrique…';
    layer.src = '/api/roi/vector-layer?' + new URLSearchParams({
      mask_path: state.config.roi?.initial_mask || '',
      visible_dir: paths.visible_dir || '', reference_image: paths.reference_image || '',
      kind: 'photometric', roi_erosion_px: radius,
      image_binning: state.config.dic?.image_binning || 1,
      operation: state.config.roi?.operation || 'none', radius_px: state.config.roi?.radius_px || 0,
      remove_islands: state.config.mesh?.remove_islands ?? true,
      min_island_area_px: state.config.mesh?.min_island_area_px ?? 64
    });
  }
  async function loadROI() {
    roiEditor?.destroy(); roiEditor = null;
    const roi = state.config.roi || {}, paths = state.config.paths || {};
    const maskPath = roi.initial_mask || '';
    const hasReference = Boolean(paths.visible_dir && paths.reference_image);
    const hasMask = Boolean(maskPath);
    const reference = resolveSource(paths.reference_image || '', paths.visible_dir || '');
    const draftKey = `${state.projectKey}\n${reference}\n${maskPath}`;
    if (!roiShapeDrafts.has(draftKey)) roiShapeDrafts.set(draftKey, { active: false, shapes: [] });
    const draft = roiShapeDrafts.get(draftKey);
    const roiParams = new URLSearchParams({
      mask_path: maskPath, visible_dir: paths.visible_dir || '',
      reference_image: paths.reference_image || '',
      operation: roi.operation || 'none', radius_px: roi.radius_px || 0
    });
    const roiLayerUrl = '/api/roi/vector-layer?' + roiParams;
    const message = !hasReference ? 'Choisissez d’abord une image de référence dans VIS.' :
      !hasMask ? 'Choisissez un fichier ROI TIFF ou PNG dans les paramètres.' :
      'ROI sur la référence VIS. Réglez la taille de maille puis cliquez sur Mailler.';
    setStage('<div class="roi-work"><div class="roi-toolbar">' +
      '<button class="button primary" id="mesh-build">Mailler</button>' +
      '<label class="roi-layer-toggle"><input id="show-roi" type="checkbox"' +
      (hasMask ? ' checked' : ' disabled') + '> ROI en filigrane</label>' +
      '<label class="roi-layer-toggle"><input id="show-photometric" type="checkbox"' +
      (hasMask ? ' checked' : ' disabled') + '> Photométrie (bleu)</label>' +
      '<label class="roi-layer-toggle"><input id="show-mesh" type="checkbox"' +
      (hasReference && hasMask && !state.dirty ? ' checked' : ' disabled') + '> Maillage</label></div>' +
      '<div class="roi-draw-toolbar"><span>Dessiner un nouveau masque</span>' +
      '<button type="button" class="button outline" id="roi-rectangle">Rectangle</button>' +
      '<button type="button" class="button outline" id="roi-ellipse">Ellipse</button>' +
      '<label>Action <select id="roi-shape-operation"><option value="add">Ajouter</option><option value="subtract">Retirer</option></select></label>' +
      '<button type="button" class="button quiet" id="roi-undo">Annuler la dernière forme</button>' +
      '<button type="button" class="button quiet" id="roi-new">Nouveau dessin</button>' +
      '<button type="button" class="button quiet" id="roi-discard">Abandonner le dessin</button>' +
      '<button type="button" class="button primary" id="roi-generate" disabled>Créer l’image ROI</button></div>' +
      '<div class="roi-canvas-wrap"><div class="roi-image-stack" data-image-stack>' +
      (hasReference ? imageMarkup(reference, 'Référence VIS', true, true, false, 'roi-base-image') : '') +
      (hasReference ? '<img id="roi-layer-image" alt=""' + (hasMask ? ' src="' +
        htmlEscape(roiLayerUrl) + '"' : ' hidden') + '>' : '') +
      (hasReference ? '<img id="photometric-layer-image" alt="Zone photométrique après érosion" hidden>' : '') +
      '</div><svg id="mesh-layer-image" class="roi-mesh-overlay" aria-label="Arêtes du maillage" hidden></svg>' +
      '<canvas id="roi-shape-canvas" aria-label="Tracer un rectangle ou une ellipse pour créer une image ROI"></canvas></div>' +
      '<div id="roi-draw-status" class="inline-status" role="status">Choisir Rectangle ou Ellipse, glisser sur la VIS, puis créer l’image ROI. Le TIFF créé sera sélectionné dans Fichier ROI avant de mailler.</div>' +
      '<div id="roi-status" class="inline-status" role="status">' +
      htmlEscape(message) + '</div><div id="photometric-status" class="inline-status" role="status">' +
      'ROI géométrique en vert · zone photométrique en bleu · maillage inchangé.</div></div>');
    const roiFrame = $('.roi-canvas-wrap');
    const roiImage = $('#roi-layer-image'), meshImage = $('#mesh-layer-image');
    const roiToggle = $('#show-roi'), meshToggle = $('#show-mesh');
    const photoImage = $('#photometric-layer-image'), photoToggle = $('#show-photometric');
    const status = $('#roi-status');
    const meshController = hasReference ? window.D2ICROIMesh.attach(roiFrame, $('#roi-base-image'), meshImage) : null;
    const loadMesh = async url => {
      try { await meshController.load(url); }
      catch { if (meshImage.isConnected) meshImage.dispatchEvent(new Event('error')); }
    };
    const updateLayers = () => {
      if (roiImage) roiImage.hidden = !roiToggle.checked;
      if (photoImage) photoImage.hidden = !photoToggle.checked || photoImage.dataset.ready !== 'true';
      meshImage.toggleAttribute('hidden', !meshToggle.checked || meshToggle.disabled);
    };
    roiToggle.addEventListener('change', updateLayers);
    photoToggle.addEventListener('change', updateLayers);
    photoImage?.addEventListener('load', () => {
      if (!photoImage.isConnected) return;
      photoImage.dataset.ready = 'true';
      updateLayers();
      $('#photometric-status').textContent = 'Vert : ROI géométrique · bleu : pixels photométriques retenus · érosion ' +
        (state.config.dic?.roi_erosion_px ?? 0) + ' px VIS d’origine · maillage inchangé.';
    });
    photoImage?.addEventListener('error', () => {
      if (!photoImage.isConnected) return;
      photoImage.dataset.ready = 'false';
      updateLayers();
      $('#photometric-status').textContent = 'Zone photométrique indisponible : vérifiez le masque, le binning et le rayon ; une érosion trop forte peut exclure tous les pixels.';
    });
    meshToggle.addEventListener('change', updateLayers);
    $('#roi-base-image')?.addEventListener('error', () => {
      status.textContent = 'Image VIS indisponible : vérifiez la référence.';
    });
    roiImage?.addEventListener('error', () => {
      status.textContent = 'ROI indisponible : vérifiez le fichier et ses dimensions.';
    });
    meshImage.addEventListener('load', () => {
      if (draft.active) return;
      meshToggle.disabled = false;
      updateLayers();
      if (meshToggle.checked) status.textContent = 'Maillage superposé à l’image VIS.';
    });
    meshImage.addEventListener('error', () => {
      meshToggle.checked = false;
      meshToggle.disabled = true;
      updateLayers();
      if (hasReference && hasMask) status.textContent = 'Maillage absent ou périmé : cliquez sur Mailler.';
    });
    updateLayers();
    if (hasReference && hasMask && !state.dirty) loadMesh('/api/mesh/vector-layer');
    if (hasReference) {
      const baseImage = $('#roi-base-image');
      const drawStatus = $('#roi-draw-status'), generate = $('#roi-generate');
      let revision = 0, currentTool = null, generating = false;
      const parameters = () => ({
        shapes: draft.shapes, visible_dir: paths.visible_dir, reference_image: paths.reference_image,
        roi_erosion_px: state.config.dic?.roi_erosion_px ?? 0,
        image_binning: state.config.dic?.image_binning ?? 1,
        remove_islands: state.config.mesh?.remove_islands ?? true,
        min_island_area_px: state.config.mesh?.min_island_area_px ?? 64
      });
      const disableOldMesh = () => {
        meshToggle.checked = false; meshToggle.disabled = true;
        meshImage.setAttribute('hidden', '');
      };
      const preview = async () => {
        if (generating) return;
        scheduleReadiness();
        const request = ++revision;
        generate.disabled = true;
        $('#mesh-build').disabled = true;
        disableOldMesh();
        drawStatus.textContent = 'Aperçu du dessin…';
        try {
          const result = await api('/api/roi/shapes/preview', { method: 'POST', body: JSON.stringify(parameters()) });
          if (!roiFrame.isConnected || request !== revision || !draft.active) return;
          roiToggle.disabled = false; roiToggle.checked = true;
          roiImage.src = result.roi_data_url;
          photoImage.dataset.ready = 'false'; photoImage.hidden = true;
          if (result.photometric_data_url) {
            photoToggle.disabled = false; photoToggle.checked = true;
            photoImage.src = result.photometric_data_url;
          } else {
            $('#photometric-status').textContent = result.photometric_error || 'Dessin vide : ajouter une forme.';
          }
          generate.disabled = result.area_px <= 0;
          $('#roi-undo').disabled = draft.shapes.length === 0;
          drawStatus.textContent = `${draft.shapes.length} forme(s) · ${result.area_px} pixels ROI · dessin non enregistré. Créer l’image ROI avant de mailler.`;
          updateLayers();
        } catch (error) {
          if (roiFrame.isConnected && request === revision) drawStatus.textContent = 'Aperçu du dessin impossible : ' + error.message;
        }
      };
      const controller = window.D2ICROIShapes.attach(roiFrame, baseImage, $('#roi-shape-canvas'), {
        geometry: fieldImageGeometry, draft, changed: preview
      });
      const choose = kind => {
        if (generating) return;
        draft.active = true; currentTool = kind;
        imageViews.get(roiFrame)?.setInteractive(false);
        controller.setTool(kind, $('#roi-shape-operation').value);
        $('#roi-rectangle').setAttribute('aria-pressed', String(kind === 'rectangle'));
        $('#roi-ellipse').setAttribute('aria-pressed', String(kind === 'ellipse'));
        preview();
      };
      $('#roi-rectangle').addEventListener('click', () => choose('rectangle'));
      $('#roi-ellipse').addEventListener('click', () => choose('ellipse'));
      $('#roi-shape-operation').addEventListener('change', () => {
        controller.setTool(currentTool, $('#roi-shape-operation').value);
      });
      $('#roi-undo').disabled = !draft.shapes.length;
      $('#roi-undo').addEventListener('click', () => {
        draft.active = true; controller.undo(); choose(currentTool || 'rectangle');
      });
      $('#roi-new').addEventListener('click', () => {
        draft.active = true; controller.clear(); choose(currentTool || 'rectangle');
      });
      $('#roi-discard').addEventListener('click', () => {
        ++revision; draft.active = false; draft.shapes = [];
        scheduleReadiness(); loadROI();
      });
      generate.addEventListener('click', async () => {
        if (generating) return;
        generating = true; ++revision;
        controller.setTool(null);
        document.querySelectorAll('.roi-draw-toolbar button, .roi-draw-toolbar select').forEach(control => control.disabled = true);
        generate.disabled = true;
        try {
          const result = await api('/api/roi/shapes/save', { method: 'POST', body: JSON.stringify(parameters()) });
          if (!roiFrame.isConnected) return;
          ++revision; draft.active = false; currentTool = null; controller.setTool(null);
          putValue('roi.initial_mask', result.initial_mask_path);
          putValue('roi.operation', 'none'); putValue('roi.radius_px', 0);
          reflectField('roi.initial_mask', result.initial_mask_path);
          setDirty();
          $('#roi-rectangle').setAttribute('aria-pressed', 'false');
          $('#roi-ellipse').setAttribute('aria-pressed', 'false');
          roiImage.src = '/api/roi/vector-layer?' + new URLSearchParams({
            mask_path: result.initial_mask_path, visible_dir: paths.visible_dir, reference_image: paths.reference_image
          });
          updatePhotometricROI();
          $('#mesh-build').disabled = false;
          drawStatus.textContent = 'Image ROI créée : ' + result.initial_mask_path + '. Cliquez sur Mailler pour poursuivre.';
        } catch (error) {
          if (roiFrame.isConnected) { drawStatus.textContent = 'Création du fichier ROI impossible : ' + error.message; generate.disabled = false; }
        } finally {
          generating = false;
          if (roiFrame.isConnected) {
            document.querySelectorAll('.roi-draw-toolbar button, .roi-draw-toolbar select').forEach(control => control.disabled = false);
            $('#roi-undo').disabled = !draft.shapes.length;
            generate.disabled = !draft.active;
            controller.setTool(currentTool, $('#roi-shape-operation').value);
          }
        }
      });
      roiEditor = { isActive: () => draft.active, preview,
        destroy() { ++revision; controller.destroy(); meshController?.destroy(); } };
      if (draft.active) preview();
    } else {
      document.querySelectorAll('.roi-draw-toolbar button, .roi-draw-toolbar select').forEach(control => control.disabled = true);
    }
    if (hasReference && hasMask && !draft.active) updatePhotometricROI();
    $('#mesh-build').addEventListener('click', async () => {
      const button = $('#mesh-build');
      if (draft.active) { status.textContent = 'Créer l’image ROI dessinée avant de mailler.'; return; }
      if (!hasReference || !state.config.roi?.initial_mask) { status.textContent = message; return; }
      const size = Number(state.config.mesh?.element_size_px);
      if (!Number.isFinite(size) || size <= 0) {
        status.textContent = 'La taille de maille doit être positive.'; return;
      }
      button.disabled = true;
      status.textContent = 'Génération du maillage…';
      try {
        if (!await save()) throw new Error('Enregistrement de l’étude impossible.');
        const saved = await api('/api/roi/save', {
          method: 'POST', body: JSON.stringify({
            operation: state.config.roi?.operation || 'none',
            radius_px: state.config.roi?.radius_px || 0
          })
        });
        putValue('roi.initial_mask', saved.initial_mask_path);
        putValue('roi.final_mask', saved.final_mask_path);
        reflectField('roi.initial_mask', saved.initial_mask_path);
        setDirty(false);
        const mesh = await api('/api/mesh/preview', { method: 'POST', body: '{}' });
        scheduleReadiness();
        if (state.view !== 'ROI' || !meshImage.isConnected) return;
        meshToggle.disabled = false;
        meshToggle.checked = true;
        await loadMesh((mesh.vector_url || '/api/mesh/vector-layer') + '?v=' + Date.now());
        roiImage.src = '/api/roi/vector-layer?' + new URLSearchParams({
          mask_path: saved.initial_mask_path, visible_dir: paths.visible_dir,
          reference_image: paths.reference_image,
          operation: state.config.roi?.operation || 'none',
          radius_px: state.config.roi?.radius_px || 0
        });
        updatePhotometricROI();
        updateLayers();
        status.textContent = mesh.nodes + ' nœuds · ' + mesh.elements +
          ' éléments · taille ' + mesh.element_size_px + ' px';
      } catch (error) { status.textContent = 'Maillage impossible : ' + error.message; }
      finally { button.disabled = false; }
    });
  }
  async function loadRegistration() {
    pairs.length=0;let currentH=null;
    let ref=resolveSource(state.config.paths?.reference_image||'',state.config.paths?.visible_dir||''), therm='';
    try { const [visData,thData]=await Promise.all([api('/api/visible'),api('/api/thermal')]); const visList=recordsFrom(visData),thList=recordsFrom(thData); if(!ref)ref=recordPath(visList[0]); therm=recordPath(thList[0]); } catch {}
    setStage(`<div class="registration-layout"><div class="pair-instructions">Cliquez un point dans VIS puis le point correspondant dans TH. Chaque paire est conservée en pixels d’origine.</div><div class="pair-views"><div><label>VIS · référence</label><div class="point-frame" data-camera="visible">${imageMarkup(ref,'Référence VIS',true)}<canvas class="point-canvas"></canvas></div></div><div><label>THERMIQUE</label><div class="point-frame" data-camera="thermal">${imageMarkup(therm,'Référence thermique',true)}<canvas class="point-canvas"></canvas></div></div></div><div class="roi-toolbar"><label>Modèle <select id="registration-model"><option value="affine">Affine</option><option value="projective">Projectif</option></select></label><button class="button outline" id="fit-registration">Ajuster H</button><button class="button outline" id="approve-registration">Valider cette correspondance</button></div><div id="pair-status" class="inline-status">0 paire définie · au moins 3 sont nécessaires pour un ajustement affine.</div><div id="residuals"></div></div>`);
    const views = [...document.querySelectorAll('.point-frame')];
    views.forEach(frame => {
      const canvas = frame.querySelector('canvas'), ctx = canvas.getContext('2d');
      const resize = () => {
        const ratio = window.devicePixelRatio || 1;
        canvas.width = Math.max(1, frame.clientWidth * ratio);
        canvas.height = Math.max(1, frame.clientHeight * ratio);
        ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
        drawPoints();
      };
      resize(); new ResizeObserver(resize).observe(frame);
      frame.querySelector('img')?.addEventListener('load', drawPoints);
      frame.addEventListener('imageviewchange', drawPoints);
      canvas.addEventListener('click', event => {
        const image = frame.querySelector('img'), g = fieldImageGeometry(frame, image);
        if (!g) return;
        const r = frame.getBoundingClientRect();
        const x = event.clientX - r.left - frame.clientLeft - g.left;
        const y = event.clientY - r.top - frame.clientTop - g.top;
        if (x < 0 || y < 0 || x > g.width || y > g.height) return;
        const p = [x * image.naturalWidth / g.width, y * image.naturalHeight / g.height];
        if (frame.dataset.camera === 'visible') activePair = { visible: p };
        else if (activePair.visible) {
          activePair.thermal = p; pairs.push(activePair); activePair = {}; currentH = null;
          $('#residuals').replaceChildren(); drawPoints();
          $('#pair-status').textContent = `${pairs.length} paire${pairs.length === 1 ? '' : 's'} définie.`;
        }
      });
    });
    function showResiduals(result){
      const residuals=result.residuals||[];
      const rows=pairs.map((pair,i)=>`<tr><td>${i+1}</td><td>${pair.visible.map(v=>Number(v).toFixed(1)).join(', ')}</td><td>${pair.thermal.map(v=>Number(v).toFixed(1)).join(', ')}</td><td>${Number(residuals[i]).toFixed(3)}</td></tr>`).join('');
      $('#residuals').innerHTML=`<div class="eyebrow">RÉSIDUS DE CORRESPONDANCE · RMS ${htmlEscape(Number(result.rms_px).toFixed(3))} px TH</div><div class="data-table-wrap"><table class="data-table"><thead><tr><th>#</th><th>VIS (px)</th><th>TH (px)</th><th>Résidu (px TH)</th></tr></thead><tbody>${rows}</tbody></table></div>`;
    }
    function drawPoints() {
      views.forEach(frame => {
        const canvas = frame.querySelector('canvas'), ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        const image = frame.querySelector('img'), g = fieldImageGeometry(frame, image);
        if (!g) return;
        const screenPoint = p => [g.left + p[0] * g.width / image.naturalWidth,
                                 g.top + p[1] * g.height / image.naturalHeight];
        pairs.forEach((pair, i) => {
          const p = pair[frame.dataset.camera]; if (!p) return;
          const [x, y] = screenPoint(p);
          ctx.fillStyle = '#e16f4f'; ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2); ctx.fill();
          ctx.fillStyle = 'white'; ctx.fillText(String(i + 1), x + 7, y - 6);
          if (frame.dataset.camera === 'thermal' && currentH) {
            const v = pair.visible, h = currentH;
            const d = h[2][0] * v[0] + h[2][1] * v[1] + h[2][2];
            if (Math.abs(d) > 1e-12) {
              const [qx, qy] = screenPoint([(h[0][0] * v[0] + h[0][1] * v[1] + h[0][2]) / d,
                                          (h[1][0] * v[0] + h[1][1] * v[1] + h[1][2]) / d]);
              ctx.strokeStyle = '#367aa8'; ctx.lineWidth = 2; ctx.beginPath();
              ctx.moveTo(x, y); ctx.lineTo(qx, qy); ctx.stroke();
              ctx.beginPath(); ctx.arc(qx, qy, 6, 0, Math.PI * 2); ctx.stroke();
            }
          }
        });
      });
    }
    $('#fit-registration').addEventListener('click',async()=>{try{const result=await api('/api/registration/fit',{method:'POST',body:JSON.stringify({points:pairs,model:$('#registration-model').value})});$('#pair-status').textContent=result.message||`Ajustement terminé · RMS ${result.rms_px ?? result.rms ?? '—'} px TH`;currentH=result.H;putValue('registration.approved', false);reflectField('registration.approved', false);scheduleReadiness();showResiduals(result);drawPoints(); }catch(e){$('#pair-status').textContent=`Ajustement impossible : ${e.message}`;}});
    $('#approve-registration').addEventListener('click',async()=>{try{const result=await api('/api/registration/approve',{method:'POST',body:JSON.stringify({points:pairs,model:$('#registration-model').value})});$('#pair-status').textContent=result.message||'Correspondance approuvée.';putValue('registration.approved', true);reflectField('registration.approved', true);scheduleReadiness();}catch(e){$('#pair-status').textContent=`Validation impossible : ${e.message}`;}});
    try{const saved=await api('/api/registration');if(saved.points?.length){pairs.push(...saved.points);currentH=saved.H;$('#registration-model').value=saved.model;showResiduals(saved);drawPoints();$('#pair-status').textContent=saved.approved?'Correspondance approuvée : inspecter les résidus ci-dessous.':'Correspondance enregistrée, validation manuelle requise.';}}catch(e){$('#pair-status').textContent=`Correspondance enregistrée indisponible : ${e.message}`;}
  }
  let synchronizationRequestId = 0;
  async function loadSynchronization() {
    const requestId = ++synchronizationRequestId;
    setStage('<div class="loading-state" role="status">Lecture des correspondances VIS–TH…</div>');
    try {
      const data = await api('/api/synchronization');
      if (requestId !== synchronizationRequestId || state.view !== 'Synchro') return;
      const rows = recordsFrom(data);
      if (!rows.length) throw new Error('Aucun instant VIS actif à synchroniser.');
      const basename = path => path ? path.split(/[\\/]/).pop() : '—';
      const number = value => value == null ? '—' : String(value);
      const table = rows.map((row, index) => {
        const status = row.valid ? 'Valide' : `Absent · ${row.reason || 'TH indisponible'}`;
        return `<tr data-sync-index="${index}" tabindex="0" ${index === 0 ? 'class="selected" aria-selected="true"' : 'aria-selected="false"'}><td>${index === 0 ? 'T_ref' : index + 1}</td><td title="${htmlEscape(row.visible_path || '')}">${htmlEscape(basename(row.visible_path))}</td><td>${htmlEscape(number(row.visible_frame))}</td><td>${htmlEscape(number(row.time_s))}</td><td title="${htmlEscape(row.thermal_left || '')}">${htmlEscape(basename(row.thermal_left))}</td><td>${htmlEscape(number(row.thermal_left_frame))}</td><td>${htmlEscape(number(row.thermal_left_time_s))}</td><td title="${htmlEscape(row.thermal_right || '')}">${htmlEscape(basename(row.thermal_right))}</td><td>${htmlEscape(number(row.thermal_right_frame))}</td><td>${htmlEscape(number(row.thermal_right_time_s))}</td><td>${htmlEscape(number(row.alpha))}</td><td>${htmlEscape(status)}</td></tr>`;
      }).join('');
      const fpsVis = data.visible_fps ?? state.config.time?.visible_fps;
      const fpsTh = data.thermal_fps ?? state.config.thermal?.thermal_fps;
      setStage(`<div class="timeline-view sync-view"><div class="sync-heading"><strong>${rows.length} instants VIS</strong><span>Cadence VIS ${htmlEscape(number(fpsVis))} Hz · TH ${htmlEscape(number(fpsTh))} Hz</span></div>${state.dirty ? '<div class="inline-status">Enregistrez les réglages pour recalculer la correspondance avec les nouvelles cadences.</div>' : ''}<div class="sync-previews" id="sync-previews"></div><div class="data-table-wrap"><table class="data-table"><thead><tr><th>Instant</th><th>VIS</th><th>N° VIS</th><th>t VIS (s)</th><th>TH précédente</th><th>N° TH</th><th>t TH (s)</th><th>TH suivante</th><th>N° TH</th><th>t TH (s)</th><th>α</th><th>État</th></tr></thead><tbody>${table}</tbody></table></div></div>`);
      const show = index => {
        const row = rows[index];
        const cards = [
          ['VIS', row.visible_path, row.visible_frame, row.time_s, false],
          ['TH précédente', row.thermal_left, row.thermal_left_frame, row.thermal_left_time_s, true],
          ['TH suivante', row.thermal_right !== row.thermal_left ? row.thermal_right : null, row.thermal_right_frame, row.thermal_right_time_s, true]
        ];
        $('#sync-previews').innerHTML = cards.map(([label, path, frame, time, thermal], cardIndex) =>
          `<div class="sync-preview"><div class="sync-preview-label"><strong>${label}</strong><span>N° ${htmlEscape(number(frame))} · ${htmlEscape(number(time))} s</span></div><div class="sync-preview-image">${path ? imageMarkup(path, `${label} · trame ${number(frame)}`, true, !thermal, thermal) : `<span>${cardIndex === 2 && row.thermal_right === row.thermal_left && row.thermal_left ? 'Même image TH' : 'Image absente'}</span>`}</div><small title="${htmlEscape(path || '')}">${htmlEscape(basename(path))}</small></div>`
        ).join('');
        document.querySelectorAll('[data-sync-index]').forEach(item => {
          const selected = Number(item.dataset.syncIndex) === index;
          item.classList.toggle('selected', selected);
          item.setAttribute('aria-selected', String(selected));
        });
      };
      document.querySelectorAll('[data-sync-index]').forEach(item => {
        const choose = () => show(Number(item.dataset.syncIndex));
        item.addEventListener('click', choose);
        item.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(); } });
      });
      show(0);
    } catch (error) {
      if (requestId !== synchronizationRequestId || state.view !== 'Synchro') return;
      setStage(`<div class="empty-visual"><h2>Synchronisation indisponible</h2><p>${htmlEscape(error.message)}</p></div>`);
    }
  }
  let readiness = null, readinessTimer = null, readinessRevision = 0, launching = false, preparingRun = false;
  const statusLabels = { inactive: 'Étape inactive', warning: 'Étape complétée', blocked: 'À compléter · obligatoire', complete: 'Étape complétée' };
  function applyReadiness(report) {
    readiness = report;
    for (const item of document.querySelectorAll('.nav-item')) {
      const step = report?.steps?.find(step => step.view === item.dataset.view);
      const status = step?.status === 'warning' ? 'complete' : step?.status || 'inactive';
      item.dataset.readiness = status;
      const messages = step?.status === 'blocked' ? step.messages : [];
      const text = `${groups[item.dataset.view]} — ${statusLabels[status]}${messages?.length ? ' : ' + messages.join(' ; ') : ''}`;
      item.title = text; item.setAttribute('aria-label', text);
      const marker = item.querySelector('.nav-state');
      if (marker) { marker.textContent = { complete: '✓', blocked: '!', warning: '!', inactive: '•' }[status]; marker.setAttribute('aria-hidden', 'true'); }
    }
    const prepare = $('#prepare-run');
    if (prepare) { prepare.disabled = preparingRun; prepare.textContent = preparingRun ? 'Préparation…' : 'Préparer le job'; }
  }
  function scheduleReadiness() {
    clearTimeout(readinessTimer); ++readinessRevision;
    applyReadiness(null);
    if (state.config.project) readinessTimer = setTimeout(refreshReadiness, 350);
  }
  async function refreshReadiness() {
    clearTimeout(readinessTimer);
    const revision = ++readinessRevision, project = state.projectKey;
    const config = JSON.stringify(state.config);
    try {
      const report = await api('/api/readiness', {method: 'POST', body: JSON.stringify({config: state.config})});
      if (revision !== readinessRevision || project !== state.projectKey || config !== JSON.stringify(state.config)) return null;
      // A shape draft is not yet the mask used by the solver, even after leaving ROI.
      const reference = resolveSource(state.config.paths?.reference_image || '', state.config.paths?.visible_dir || '');
      const draftKey = `${project}\n${reference}\n${state.config.roi?.initial_mask || ''}`;
      if (roiShapeDrafts.get(draftKey)?.active) {
        report.ready = false;
        const message = 'Créer l’image ROI du dessin en cours puis régénérer le maillage, ou abandonner le dessin.';
        const step = report.steps.find(step => step.view === 'ROI');
        if (step) { step.status = 'blocked'; step.messages.push(message); }
        report.required.push({view: 'ROI', message});
      }
      applyReadiness(report); return report;
    } catch (error) {
      if (revision === readinessRevision) {
        applyReadiness(null);
        if ($('#readiness-summary')) $('#readiness-summary').textContent = 'Vérification impossible : ' + error.message;
      }
      return null;
    }
  }
  function showReadiness(report) {
    const dialog = $('#readiness-dialog'), host = $('#readiness-details'); host.replaceChildren();
    $('#readiness-title').textContent = report?.ready ? 'Prêt au lancement' : 'Étapes à compléter';
    if (!report) { host.textContent = 'Impossible de vérifier la préparation. Réessayez après avoir vérifié la connexion au serveur local.'; }
    else {
      const issues = report.required || [];
      {
        const heading = document.createElement('h3'); heading.textContent = 'Obligatoires avant le lancement'; host.append(heading);
        if (!issues.length) { const text = document.createElement('p'); text.textContent = 'Aucune étape à compléter.'; host.append(text); }
        const list = document.createElement('ul');
        for (const issue of issues) {
          const row = document.createElement('li'), button = document.createElement('button');
          button.type = 'button'; button.className = 'readiness-link';
          button.textContent = `${groups[issue.view] || issue.view} : ${issue.message}`;
          button.addEventListener('click', () => { dialog.close(); selectView(issue.view); });
          row.append(button); list.append(row);
        }
        host.append(list);
      }
    }
    if (!dialog.open) dialog.showModal();
  }
  function selectedRunStorageKey(){return `d2ic-selected-run:${state.projectKey}`;}
  function rememberRun(id){state.selectedRun=id||null;if(id)localStorage.setItem(selectedRunStorageKey(),id);else localStorage.removeItem(selectedRunStorageKey());}
  async function prepareRun(){
    if (preparingRun) return;
    preparingRun = true; applyReadiness(readiness);
    try {
      if(state.dirty && !await save()) { notify('Job non préparé', $('#config-message').textContent); return; }
      const result=await api('/api/runs/prepare',{method:'POST',body:JSON.stringify({config:state.config})});
      const id=result.id||result.run_id; if(id)rememberRun(id);
      await populateRuns();
    } catch(e) { notify('Job non préparé', e.message); }
    finally { preparingRun = false; applyReadiness(readiness); }
  }
  async function launchRun(id){
    if (launching || !id) return;
    launching = true;
    try {
      await api(`/api/runs/${encodeURIComponent(id)}/start`,{method:'POST',body:'{}'});
      rememberRun(id); await populateRuns();
    } catch(e) { notify('Calcul non lancé', e.message); await populateRuns(); }
    finally { launching = false; }
  }
  function renderRunSummary(run){
    const host=$('#run-status');if(!host)return;
    const stateLabel={pending:'Prêt',preparing:'Préparation',blocked:'Erreur de préparation',running:'En cours',completed:'Terminé',failed:'Échec',cancelled:'Arrêté'}[run.state||run.status]||run.state||run.status||'Prêt';
    const completed=Number(run.completed_frames)||0,total=Number(run.total_frames)||0;
    const progress=total?Math.round(100*completed/total):0;
    const updated=run.updated_utc?new Date(run.updated_utc).toLocaleString('fr-FR'):'—';
    const error=run.error?`<p class="run-summary-error">${htmlEscape(run.error)}</p>`:'';
    host.innerHTML=`<div class="run-summary-top"><strong>${htmlEscape(run.run_id||run.id||state.selectedRun||'Run')}</strong><span class="run-state-badge ${htmlEscape(run.state||run.status||'pending')}">${htmlEscape(stateLabel)}</span></div><div class="run-summary-meta"><span>Images ${completed}/${total||'—'}</span><span>${progress} %</span><span>Mis à jour ${htmlEscape(updated)}</span></div><progress max="100" value="${progress}" aria-label="Progression du run"></progress>${error}`;
  }
  const kinematicFields=new Set(['u1','u2','u_norm','E11','E22','E12']);
  const nodeColors=['#cc4b3a','#237caa','#7557ac','#1f8d62','#c17b13','#bb4589','#4d6a25'];
  const resultNodes=new Map(), historyCache=new Map(), colorBounds=new Map(), resultSections=new Map();
  let analysisMode="history", sectionRequest=0;
  let historyRequest=0, fieldRequest=0, resultRefreshTimer=null, resultMetadata=null, resultDisplay=null;
  const storedFieldAlpha = Number(localStorage.getItem('d2ic-result-field-alpha') ?? '0.65');
  let resultFieldAlpha = Number.isFinite(storedFieldAlpha) ? Math.max(0, Math.min(1, storedFieldAlpha)) : 0.65;
  const fieldLabel = field => field === 'Residual' ? 'Carte de résidu' : field;
  function updateFieldAlpha() {
    const input = $('#field-alpha'), image = $('#run-field-image');
    if (!input || !image) return;
    const enabled = $('#result-background').value !== 'none';
    input.disabled = !enabled;
    image.style.opacity = enabled ? String(resultFieldAlpha) : '1';
    $('#field-alpha-value').textContent = `${Math.round(resultFieldAlpha * 100)} %`;
  }
  function selectedNodes(id){if(!resultNodes.has(id))resultNodes.set(id,new Set());return resultNodes.get(id);}
  function fieldImageGeometry(frame,image){
    if (window.D2ICImageZoom) return window.D2ICImageZoom.geometry(frame,image);
    if(!image.naturalWidth||!image.naturalHeight||!frame.clientWidth||!frame.clientHeight)return null;
    const scale=Math.min(frame.clientWidth/image.naturalWidth,frame.clientHeight/image.naturalHeight);
    const width=image.naturalWidth*scale,height=image.naturalHeight*scale;
    return {left:(frame.clientWidth-width)/2,top:(frame.clientHeight-height)/2,width,height};
  }
  function drawNodeOverlay(mesh,id){
    const svg=$('#run-node-overlay'),image=$('#run-field-image'),frame=$('.run-field-frame');
    if(!svg||!image||!frame)return;
    if (image.hidden || $('#run-field')?.value === 'Residual') { svg.replaceChildren(); return; }
    const geometry=fieldImageGeometry(frame,image);
    if(!geometry){svg.replaceChildren();return;}
    const bounds=mesh.extent;
    Object.assign(svg.style,{width:`${geometry.width}px`,height:`${geometry.height}px`,left:`${geometry.left}px`,top:`${geometry.top}px`});
    svg.setAttribute('viewBox',`${bounds[0]} ${bounds[2]} ${bounds[1]-bounds[0]} ${bounds[3]-bounds[2]}`);
    const radius=5*(bounds[1]-bounds[0])/Math.max(geometry.width,1);
    svg.innerHTML=[...selectedNodes(id)].map((node,index)=>{const p=mesh.nodes_xy[node];return p?`<circle cx="${p[0]}" cy="${p[1]}" r="${radius}" fill="${nodeColors[index%nodeColors.length]}" stroke="white" stroke-width="${radius/3}" data-node="${node}"/>`:'';}).join('');
    if(analysisMode==='section'&&resultDisplay){
      const points=(resultSections.get(id)||[]).map(point=>mapMeshPoint(point,resultDisplay.reference,mesh)).filter(Boolean);
      const referencePoints=resultSections.get(id)||[];
      if(referencePoints.length===2){
        const groups=[];let group=[];
        for(let i=0;i<=100;i++){
          const point=mapMeshPoint([0,1].map(axis=>referencePoints[0][axis]+i/100*(referencePoints[1][axis]-referencePoints[0][axis])),resultDisplay.reference,mesh);
          if(point)group.push(point.join(','));else if(group.length){groups.push(group);group=[];}
        }
        if(group.length)groups.push(group);
        svg.innerHTML+=groups.map(group=>`<polyline points="${group.join(' ')}" fill="none" stroke="#168256" stroke-width="${radius/2}"/>`).join('');
      }
      svg.innerHTML+=points.map(point=>`<circle cx="${point[0]}" cy="${point[1]}" r="${radius}" fill="#168256" stroke="white" stroke-width="${radius/3}"/>`).join('');
    }
  }
  async function renderRunField(id, metadata, display) {
    const request = ++fieldRequest;
    const image = $('#run-field-image'), background = $('#run-background-image');
    if (!image || !background) return;
    const field = $('#run-field').value;
    const residualFrames = metadata.residual_frames || metadata.times_s.map((_, index) => index).slice(1);
    const residualAvailable = new Set(residualFrames);
    if (field === 'Residual' && !residualAvailable.has(Number($('#run-frame').value))) {
      const wanted=Number($('#run-frame').value);
      $('#run-frame').value=String(residualFrames.reduce((best,index)=>Math.abs(index-wanted)<Math.abs(best-wanted)?index:best,residualFrames[0]));
    }
    const frame = Number($('#run-frame').value);
    $('#run-frame-value').textContent=`${frame===0?'Réf. · ':''}${frame+1}/${metadata.times_s.length} · ${metadata.times_s[frame]} s`;
    $('#run-frame').setAttribute('aria-valuetext',$('#run-frame-value').textContent);
    if(analysisMode==='section')updateSectionGraph(id);
    const backgroundSelect = $('#result-background');
    const hasSourceShape = Array.isArray(metadata.source_shape_hw);
    for (const option of backgroundSelect.options) {
      option.disabled = option.value !== 'none' && !hasSourceShape;
    }
    if (!hasSourceShape) backgroundSelect.value = 'none';
    const showBackground = backgroundSelect.value !== 'none';
    const overlay = hasSourceShape ? 'current' : 'none';
    image.hidden = true; background.hidden = true;
    $('#run-node-overlay').replaceChildren();
    const current = () => request === fieldRequest && image.isConnected && state.view === 'Résultats' && state.selectedRun === id;
    const key = `${id}:${field}`, bounds = colorBounds.get(key);
    const params = new URLSearchParams({field, frame: String(frame), overlay});
    if (kinematicFields.has(field) && bounds) { params.set('vmin', bounds[0]); params.set('vmax', bounds[1]); }
    if($('#color-zero').checked&&field!=='Residual')params.set('center_zero','true');
    $('#color-controls').hidden = field==='Residual';
    for(const control of ['color-min','color-max','range-image','range-sequence','range-auto'])$('#'+control).disabled=!kinematicFields.has(field);
    $('.run-field-frame').style.cursor = field === 'Residual' ? 'default' : 'crosshair';
    $('#color-min').value = bounds?.[0] ?? ''; $('#color-max').value = bounds?.[1] ?? '';
    const provenance = metadata.thermal_provenance?.[frame];
    const validity = provenance ? ` · TH : ${provenance.time_valid ? 'temps valide' : 'température absente'}` : '';
    const unit = field === 'Residual' ? 'écart d’intensité VIS' : field.startsWith('u') ? metadata.length_unit : field.startsWith('E') ? 'sans unité' : metadata.temperature_unit || '';
    const coordinates = overlay === 'current' ? ' · configuration déformée' + (field === 'Residual' ? ' · résidu transporté' : '') : ' · configuration de référence';
    $('#run-field-info').replaceChildren();
    $('#run-field-info').append(document.createTextNode(`${fieldLabel(field)} · image VIS ${frame + 1}/${metadata.times_s.length} · ${unit}${coordinates}${validity} `));
    const fieldStatus = document.createElement('span'); fieldStatus.id = 'run-field-render-status'; fieldStatus.setAttribute('role', 'status');
    const status = document.createElement('span'); status.id = 'run-background-status'; status.setAttribute('role', 'status');
    $('#run-field-info').append(fieldStatus, status);
    updateFieldAlpha();
    try {
      let mesh = display.reference;
      if (overlay !== 'none') {
        const geometryKey = `${overlay}:${frame}`;
        if (!display.cache.has(geometryKey)) display.cache.set(geometryKey, api(`/api/runs/${encodeURIComponent(id)}/mesh?${new URLSearchParams({overlay,frame:String(frame)})}`).catch(error => { display.cache.delete(geometryKey); throw error; }));
        mesh = await display.cache.get(geometryKey);
      }
      if (!current()) return;
      display.mesh = mesh;
      image.onload = () => { if (current()) { image.hidden = false; drawNodeOverlay(mesh, id); } };
      image.onerror = () => { if (current()) { image.hidden = true; fieldStatus.textContent = ' · Carte indisponible pour cet instant.'; } };
      image.src = `/api/runs/${encodeURIComponent(id)}/field-image?${params}`;
      if (showBackground) {
        background.onload = () => { if (current()) { background.hidden = false; status.textContent = ''; } };
        background.onerror = () => { if (current()) { background.hidden = true; status.textContent = ' · Image VIS source absente ou modifiée ; le champ reste disponible.'; } };
        background.src = `/api/runs/${encodeURIComponent(id)}/visible-image?frame=${frame}`;
      } else background.removeAttribute('src');
    } catch (error) {
      if (current()) fieldStatus.textContent = ` · Affichage impossible : ${error.message}`;
    }
  }
  async function updateHistoryGraph(id,field){
    const panel=$('#run-history');if(!panel)return;
    const nodes=[...selectedNodes(id)],request=++historyRequest,projectKey=state.projectKey;
    if(!nodes.length){panel.innerHTML='<div class="empty-inline">Cliquez sur la carte pour ajouter un nœud. Ctrl + clic retire un nœud.</div>';return;}
    panel.textContent='Chargement des courbes…';
    try{
      const missing=nodes.filter(node=>!historyCache.has(`${id}:${node}`));
      if(missing.length){
        const payload=await api(`/api/runs/${encodeURIComponent(id)}/histories?nodes=${missing.join(',')}`);
        if(projectKey!==state.projectKey||request!==historyRequest)return;
        for(const item of payload.histories||[])historyCache.set(`${id}:${item.node}`,item.history||[]);
      }
      const datasets=nodes.map(node=>({node,rows:historyCache.get(`${id}:${node}`)||[]}));
      if(request!==historyRequest||projectKey!==state.projectKey||state.view!=='Résultats'||state.selectedRun!==id)return;
      const series=datasets.map(({node,rows})=>({node,points:rows.map(row=>{const value=field==='u_norm'&&row.u1!=null&&row.u2!=null?Math.hypot(row.u1,row.u2):row[field];return value==null||!Number.isFinite(Number(value))?null:{x:Number(row.time_s),y:Number(value)};})}));
      const all=series.flatMap(item=>item.points.filter(point=>point&&Number.isFinite(point.x)));if(!all.length){panel.textContent='Aucune donnée finie pour ces nœuds et ce champ.';return;}
      let xmin=Infinity,xmax=-Infinity,ymin=Infinity,ymax=-Infinity;for(const point of all){xmin=Math.min(xmin,point.x);xmax=Math.max(xmax,point.x);ymin=Math.min(ymin,point.y);ymax=Math.max(ymax,point.y);}
      if(xmax===xmin)xmax=xmin+1;if(ymax===ymin){ymin-=0.5;ymax+=0.5;}
      const w=800,h=170,p=34,x=v=>p+(v-xmin)/(xmax-xmin)*(w-2*p),y=v=>h-p-(v-ymin)/(ymax-ymin)*(h-2*p);
      const lines=series.map((item,index)=>{const groups=[];let segment=[];for(const point of [...item.points,null]){if(point&&Number.isFinite(point.x))segment.push(point);else if(segment.length){groups.push(segment);segment=[];}}return groups.map(group=>`<polyline points="${group.map(q=>`${x(q.x)},${y(q.y)}`).join(' ')}" fill="none" stroke="${nodeColors[index%nodeColors.length]}" stroke-width="2" vector-effect="non-scaling-stroke"/>`).join('');}).join('');
      panel.innerHTML=`<div class="history-chart"><svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Historique de ${htmlEscape(field)} pour ${nodes.length} nœuds"><line x1="${p}" y1="${h-p}" x2="${w-p}" y2="${h-p}" stroke="#b6c4b9"/>${lines}</svg><div class="history-range"><span>${htmlEscape(xmin.toPrecision(4))}–${htmlEscape(xmax.toPrecision(4))} s</span><span>${htmlEscape(ymin.toPrecision(4))}–${htmlEscape(ymax.toPrecision(4))} ${htmlEscape(resultGraphUnit(field))}</span></div></div><div class="node-legend">${nodes.map((node,index)=>`<span><i style="background:${nodeColors[index%nodeColors.length]}"></i>Nœud ${node}</span>`).join('')}</div>`;
    }catch(error){if(request===historyRequest)panel.textContent=`Historique indisponible : ${error.message}`;}
  }
  const {mapMeshPoint} = window.D2ICResultAnalysis;
  function resultGraphUnit(field){
    return field.startsWith('u')?resultMetadata.length_unit:field.startsWith('E')?'sans unité':resultMetadata.temperature_unit||'';
  }
  function sectionParameters(id, scope = 'image') {
    return window.D2ICResultAnalysis.sectionParameters({
      points: resultSections.get(id) || [],
      samples: $('#section-samples').value,
      field: $('#history-field').value,
      frame: $('#run-frame').value,
      scope
    });
  }
  function updateAnalysisGraphs(id){
    updateHistoryGraph(id,$('#history-field').value);
    if(analysisMode==='section')updateSectionGraph(id);
  }
  async function downloadResultCSV(id,kind){
    const button=$('#'+kind+'-csv');button.disabled=true;
    try{
      let params;
      if(kind==='history'){
        const nodes=[...selectedNodes(id)];
        if(!nodes.length)throw new Error('Sélectionnez au moins un nœud.');
        params=new URLSearchParams({nodes:nodes.join(','),field:$('#history-field').value});
      }else params=sectionParameters(id,$('#section-scope').value);
      const response=await fetch(`/api/runs/${encodeURIComponent(id)}/${kind==='history'?'histories':'section'}.csv?${params}`);
      if(!response.ok){const error=await response.json();throw new Error(error.detail||'Export indisponible');}
      const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');
      link.href=url;link.download=`${id}-${kind}-${params.get('field')}.csv`;link.click();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch(error){notify('Export CSV',error.message);}finally{button.disabled=false;}
  }
  function setupResultAnalysis(id,display){
    const activate=mode=>{
      analysisMode=mode;
      for(const name of ['history','section']){
        const selected=name===mode;
        $('#tab-'+name).setAttribute('aria-selected',String(selected));
        $('#tab-'+name).tabIndex=selected?0:-1;
        $('#'+name+'-content').hidden=!selected;
      }
      drawNodeOverlay(display.mesh,id);updateAnalysisGraphs(id);
    };
    for(const name of ['history','section']){
      $('#tab-'+name).addEventListener('click',()=>activate(name));
      $('#tab-'+name).addEventListener('keydown',event=>{
        if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){
          event.preventDefault();const mode=event.key==='Home'?'history':event.key==='End'?'section':name==='history'?'section':'history';
          activate(mode);$('#tab-'+mode).focus();
        }
      });
      $('#'+name+'-csv').addEventListener('click',()=>downloadResultCSV(id,name));
    }
    $('#section-clear').addEventListener('click',()=>{resultSections.delete(id);drawNodeOverlay(display.mesh,id);updateSectionGraph(id);});
    $('#section-samples').addEventListener('change',()=>updateSectionGraph(id));
    activate(analysisMode);
  }
  async function updateSectionGraph(id){
    const panel=$('#run-section');if(!panel)return;
    const request=++sectionRequest,projectKey=state.projectKey;
    const points=resultSections.get(id)||[];
    $('#section-coordinates').textContent=points.map((p,index)=>`${index===0?'A':'B'} : (${p[0].toFixed(2)}, ${p[1].toFixed(2)}) px réf.`).join(' · ');
    let params;
    try{params=sectionParameters(id);}catch(error){panel.textContent=error.message;return;}
    panel.textContent='Chargement de la coupe…';
    try{
      const data=await api(`/api/runs/${encodeURIComponent(id)}/section?${params}`);
      if(request!==sectionRequest||projectKey!==state.projectKey||state.selectedRun!==id||!panel.isConnected)return;
      const profile=data.profiles[0],values=profile.values,distances=profile.distance;
      const finite=values.filter(value=>value!==null&&Number.isFinite(value));
      if(!finite.length){panel.textContent='Aucune valeur finie sur cette coupe.';return;}
      let low=Math.min(...finite),high=Math.max(...finite);if(high-low<1e-12*Math.max(1,Math.abs(low),Math.abs(high))){const delta=Math.max(Math.abs(low)*.01,1e-9);low-=delta;high+=delta;}
      const width=800,height=230,p=42,length=distances.at(-1)||1;
      const x=value=>p+value/length*(width-2*p),y=value=>height-p-(value-low)/(high-low)*(height-2*p);
      const groups=[];let group=[];
      for(let i=0;i<=values.length;i++){
        if(i<values.length&&values[i]!==null&&Number.isFinite(values[i]))group.push(`${x(distances[i])},${y(values[i])}`);
        else if(group.length){groups.push(group);group=[];}
      }
      panel.innerHTML=`<div class="history-chart"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Coupe de ${htmlEscape(params.get('field'))}"><line x1="${p}" y1="${height-p}" x2="${width-p}" y2="${height-p}" stroke="#b6c4b9"/>${groups.map(points=>`<polyline points="${points.join(' ')}" fill="none" stroke="#168256" stroke-width="2" vector-effect="non-scaling-stroke"/>`).join('')}</svg><div class="history-range"><span>Distance A → B : 0–${length.toPrecision(4)} ${htmlEscape(data.length_unit)}</span><span>${low.toPrecision(4)}–${high.toPrecision(4)} ${htmlEscape(resultGraphUnit(params.get('field')))}</span></div></div><p>Image ${profile.frame+1} · ${htmlEscape(profile.time_s)} s · segment en référence</p>`;
    }catch(error){if(request===sectionRequest&&panel.isConnected)panel.textContent=`Coupe indisponible : ${error.message}`;}
  }
  async function loadRunDetails(id){
    const panel=$('#run-fields');if(!panel)return;
    const projectKey=state.projectKey;
    panel.textContent='Chargement des champs…';
    try{
      const metadata=await api(`/api/runs/${encodeURIComponent(id)}/fields`);
      if(state.selectedRun!==id||state.view!=='Résultats'||projectKey!==state.projectKey)return;
      if(Number(metadata.completed_frames||0)===0&&['pending','running'].includes(metadata.state)){
        resultMetadata=metadata;
        panel.innerHTML='<div class="empty-inline" role="status">Calcul en cours. Les résultats apparaîtront dès que la première image sera validée.</div>';
        scheduleResultRefresh(id);return;
      }
      const mesh=await api(`/api/runs/${encodeURIComponent(id)}/mesh`);
      if(state.selectedRun!==id||state.view!=='Résultats'||projectKey!==state.projectKey)return;
      const fields=metadata.fields||[],times=metadata.times_s||[];let historyFields=['u1','u2','u_norm','E11','E22','E12','Temperature','Delta_temperature'].filter(name=>fields.includes(name));
      panel.innerHTML=`<div class="result-toolbar"><label>Champ<select id="run-field">${fields.map(name=>`<option value="${htmlEscape(name)}">${htmlEscape(fieldLabel(name))}</option>`).join('')}</select></label><label class="frame-slider">Instant VIS<input id="run-frame" type="range" min="0" max="${Math.max(0,times.length-1)}" step="1" value="0"><output id="run-frame-value"></output></label><span>${htmlEscape(metadata.nodes)} nœuds</span><label>Fond VIS<select id="result-background"><option value="none">Sans image</option><option value="current">VIS de l’instant choisi</option></select></label><label>Opacité du champ α<input id="field-alpha" type="range" min="0" max="1" step="0.01" value="${resultFieldAlpha}" aria-label="Opacité du champ"><output id="field-alpha-value"></output></label></div><div id="color-controls" class="color-controls"><label><input id="color-zero" type="checkbox">Centrer sur 0</label><label>Min <input id="color-min" type="number" step="any" placeholder="Auto"></label><label>Max <input id="color-max" type="number" step="any" placeholder="Auto"></label><button class="button outline" id="range-image" type="button">Min/max image</button><button class="button outline" id="range-sequence" type="button">Min/max séquence</button><button class="button quiet" id="range-auto" type="button">Auto</button><span id="color-status" role="status"></span><span class="color-gradient" aria-hidden="true"></span></div><div class="run-field-frame"><div class="result-image-stack" data-image-stack><img id="run-background-image" alt="Image VIS source du résultat" hidden><img id="run-field-image" alt="Carte du champ sélectionné" hidden></div><svg id="run-node-overlay" aria-label="Sélectionner des nœuds sur la carte"></svg></div><div id="run-field-info" class="run-field-info"></div><section class="history-panel"><div class="analysis-tabs" role="tablist" aria-label="Analyse des résultats"><button type="button" id="tab-history" role="tab" aria-controls="history-content" aria-selected="true">Suivi de points</button><button type="button" id="tab-section" role="tab" aria-controls="section-content" aria-selected="false">Coupe</button></div><div class="history-controls"><label>Grandeur <select id="history-field">${historyFields.map(name=>`<option value="${htmlEscape(name)}">${htmlEscape(name)}</option>`).join('')}</select></label></div><div id="history-content" role="tabpanel" aria-labelledby="tab-history"><div class="history-controls"><span>Clic : ajouter · Maj + clic : retirer</span><button type="button" class="button outline" id="history-csv">Exporter CSV · toutes les images</button></div><div id="run-history" class="run-history"></div></div><div id="section-content" role="tabpanel" aria-labelledby="tab-section" hidden><div class="history-controls"><span>Deux clics sur le maillage : extrémités de la coupe matérielle.</span><button type="button" class="button quiet" id="section-clear">Nouvelle coupe</button><label>Échantillons <input id="section-samples" type="number" min="2" max="2000" step="1" value="200"></label><label>Export <select id="section-scope"><option value="image">Image courante</option><option value="sequence">Toutes les images</option></select></label><button type="button" class="button outline" id="section-csv">Exporter CSV</button></div><div id="section-coordinates"></div><div id="run-section" class="run-history"></div></div></section>`;
      const display = {reference: mesh, mesh, cache: new Map(), historyFields};
      const liveMetadata={...metadata};
      resultMetadata = liveMetadata; resultDisplay = display; renderResultRunStatus(id,liveMetadata);
      const storedBackground = localStorage.getItem('d2ic-result-background') || 'current';
      $('#result-background').value = ['none','current'].includes(storedBackground) ? storedBackground : 'current';
      const refresh = () => renderRunField(id, liveMetadata, display);
      $('#result-background').addEventListener('change', () => { localStorage.setItem('d2ic-result-background', $('#result-background').value); refresh(); });
      $('#field-alpha').addEventListener('input', () => { resultFieldAlpha = Number($('#field-alpha').value); localStorage.setItem('d2ic-result-field-alpha', String(resultFieldAlpha)); updateFieldAlpha(); });
      $('#run-field').addEventListener('change',()=>{const field=$('#run-field').value;if(display.historyFields.includes(field))$('#history-field').value=field;refresh();updateAnalysisGraphs(id);});
      $('#run-frame').addEventListener('input',refresh);
      $('#color-zero').checked=localStorage.getItem('d2ic-color-zero')==='true';
      $('#color-zero').addEventListener('change',()=>{localStorage.setItem('d2ic-color-zero',String($('#color-zero').checked));refresh();});
      setupResultAnalysis(id,display);
      $('#history-field').addEventListener('change',()=>updateAnalysisGraphs(id));
      const applyBounds=()=>{const low=Number($('#color-min').value),high=Number($('#color-max').value),status=$('#color-status');if(!$('#color-min').value||!$('#color-max').value||!Number.isFinite(low)||!Number.isFinite(high)||low>=high){status.textContent='Saisissez deux bornes finies avec min < max.';return;}colorBounds.set(`${id}:${$('#run-field').value}`,[low,high]);status.textContent='';refresh();};
      $('#color-min').addEventListener('change',applyBounds);$('#color-max').addEventListener('change',applyBounds);
      $('#range-auto').addEventListener('click',()=>{colorBounds.delete(`${id}:${$('#run-field').value}`);$('#color-status').textContent='Échelle automatique';refresh();});
      for(const scope of ['image','sequence'])$('#range-'+scope).addEventListener('click',async()=>{const field=$('#run-field').value,frame=$('#run-frame').value,status=$('#color-status');status.textContent='Calcul des bornes…';try{const range=await api(`/api/runs/${encodeURIComponent(id)}/field-range?${new URLSearchParams({field,frame,scope})}`);if(state.selectedRun!==id||$('#run-field')?.value!==field||(scope==='image'&&$('#run-frame')?.value!==frame))return;let low=range.min,high=range.max;if(low===high){const delta=Math.max(Math.abs(low)*0.01,1e-9);low-=delta;high+=delta;}colorBounds.set(`${id}:${field}`,[low,high]);status.textContent=`${scope==='image'?'Image':'Séquence'} : ${range.min.toPrecision(4)} à ${range.max.toPrecision(4)}`;refresh();}catch(error){status.textContent=error.message;}});
      $('.run-field-frame').addEventListener('click',event=>{
        if($('#run-field').value==='Residual'||$('#run-field-image').hidden)return;
        const mesh = display.mesh;
        const frame=event.currentTarget,image=$('#run-field-image');
        const geometry=fieldImageGeometry(frame,image);if(!geometry)return;
        const rect=frame.getBoundingClientRect(),localX=event.clientX-rect.left-frame.clientLeft;
        const localY=event.clientY-rect.top-frame.clientTop;
        if(localX<geometry.left||localX>geometry.left+geometry.width||localY<geometry.top||localY>geometry.top+geometry.height)return;
        const extent=mesh.extent;
        const x=extent[0]+(localX-geometry.left)/geometry.width*(extent[1]-extent[0]);
        const y=extent[2]+(localY-geometry.top)/geometry.height*(extent[3]-extent[2]);
        if(analysisMode==='section'){
          const point=mapMeshPoint([x,y],mesh,display.reference);
          if(!point){$('#run-section').textContent='Choisissez une extrémité dans le maillage.';return;}
          const points=resultSections.get(id)||[];
          resultSections.set(id,points.length===2?[point]:[...points,point]);
          drawNodeOverlay(mesh,id);updateSectionGraph(id);return;
        }
        const nodes=selectedNodes(id),candidates=event.shiftKey?[...nodes]:mesh.nodes_xy.map((_,index)=>index);
        let nearest=-1,distance=Infinity;
        for(const index of candidates){const point=mesh.nodes_xy[index];const d=(point[0]-x)**2+(point[1]-y)**2;if(d<distance){nearest=index;distance=d;}}
        if(nearest<0)return;
        if(event.shiftKey)nodes.delete(nearest);else nodes.add(nearest);
        drawNodeOverlay(mesh,id);updateHistoryGraph(id,$('#history-field').value);
      });
      new ResizeObserver(()=>drawNodeOverlay(display.mesh,id)).observe($('.run-field-frame'));
      $('.run-field-frame').addEventListener('imageviewchange',()=>drawNodeOverlay(display.mesh,id));
      refresh();updateHistoryGraph(id,$('#history-field').value);
      scheduleResultRefresh(id);
    }catch(error){if(panel&&state.view==='Résultats')panel.textContent=`Champs indisponibles : ${error.message}`;}
  }
  function scheduleResultRefresh(id){
    if(resultRefreshTimer)clearTimeout(resultRefreshTimer);
    resultRefreshTimer=null;
    if(state.view!=='Résultats'||state.selectedRun!==id)return;
    const stateName=resultMetadata?.state;
    if(!['pending','running'].includes(stateName))return;
    resultRefreshTimer=setTimeout(()=>refreshRunResults(id),1500);
  }
  async function refreshRunResults(id){
    if(state.view!=='Résultats'||state.selectedRun!==id||!resultMetadata)return;
    const projectKey=state.projectKey;
    try{
      const metadata=await api(`/api/runs/${encodeURIComponent(id)}/fields`);
      if(projectKey!==state.projectKey||state.view!=='Résultats'||state.selectedRun!==id)return;
      const previous=resultMetadata, fields=$('#run-field'), frames=$('#run-frame');
      const changed=JSON.stringify(previous.times_s)!==JSON.stringify(metadata.times_s)||JSON.stringify(previous.fields)!==JSON.stringify(metadata.fields);
      Object.assign(previous,metadata);resultMetadata=previous;renderResultRunStatus(id,previous);
      if(!fields&&Number(metadata.completed_frames||0)>0){await loadRunDetails(id);return;}
      if(changed&&fields&&frames){
        const selectedField=fields.value, selectedFrame=frames.value;
        const nextFields=metadata.fields||[], nextTimes=metadata.times_s||[];
        fields.replaceChildren(...nextFields.map(name=>{const option=document.createElement('option');option.value=name;option.textContent=fieldLabel(name);return option;}));
        if(nextFields.includes(selectedField))fields.value=selectedField;
        frames.max=String(Math.max(0,nextTimes.length-1));
        if(Number(selectedFrame)<nextTimes.length)frames.value=selectedFrame;
        const historySelect=$('#history-field'),selectedHistory=historySelect?.value;
        if(historySelect){const historyFields=['u1','u2','u_norm','E11','E22','E12','Temperature','Delta_temperature'].filter(name=>nextFields.includes(name));if(resultDisplay)resultDisplay.historyFields=historyFields;historySelect.replaceChildren(...historyFields.map(name=>{const option=document.createElement('option');option.value=name;option.textContent=name;return option;}));if(historyFields.includes(selectedHistory))historySelect.value=selectedHistory;else if(historyFields.includes(fields.value))historySelect.value=fields.value;}
        for(const key of [...historyCache.keys()])if(key.startsWith(`${id}:`))historyCache.delete(key);
        historyRequest++; resultDisplay?.cache.clear();
        if(resultDisplay)renderRunField(id,metadata,resultDisplay);
        updateAnalysisGraphs(id);
      }
      if(!metadata.times_s?.length&&['pending','running'].includes(metadata.state)){
        const panel=$('#run-fields');
        if(panel&&!fields)panel.innerHTML='<div class="empty-inline" role="status">Calcul en cours. Les résultats apparaîtront dès que la première image sera validée.</div>';
      }
    }catch(error){const panel=$('#run-fields');if(panel&&state.view==='Résultats')panel.dataset.refreshError=error.message;}
    scheduleResultRefresh(id);
  }
  let runListTimer=null;
  async function runAction(id,action){
    const host=$('#run-status');
    if(action==='delete'&&!window.confirm(`Supprimer définitivement le run ${id} et ses résultats ?`))return;
    try{const route=`/api/runs/${encodeURIComponent(id)}`+(action==='restart'?'/resume':action==='stop'?'/cancel':'');await api(route,{method:action==='delete'?'DELETE':'POST',body:action==='delete'?undefined:'{}'});if(action==='delete'){resultNodes.delete(id);for(const key of [...historyCache.keys()])if(key.startsWith(`${id}:`))historyCache.delete(key);for(const key of [...colorBounds.keys()])if(key.startsWith(`${id}:`))colorBounds.delete(key);if(state.selectedRun===id)rememberRun(null);}if(action==='restart')rememberRun(id);await populateRuns();}
    catch(error){if(host)host.textContent=`Action impossible pour ${id} : ${error.message}`;}
  }
  function renderRunPreparation(run){
    const required=run.preparation?.required||[],optional=run.preparation?.optional||[];
    const runtimeError=run.error&&!required.some(item=>item.message===run.error)?`<li class="run-preparation-error">Erreur · ${htmlEscape(run.error)}</li>`:'';
    const issues=[...required.map(item=>`<li class="run-preparation-error">Erreur · ${htmlEscape(item.view)} : ${htmlEscape(item.message)}</li>`),...optional.map(item=>`<li class="run-preparation-warning">Avertissement · ${htmlEscape(item.view)} : ${htmlEscape(item.message)}</li>`),runtimeError].join('');
    return issues?`<ul class="run-preparation">${issues}</ul>`:'';
  }
  function renderRunRow(run) {
    const id = run.id || run.run_id || run.name;
    const active = id === state.selectedRun;
    const runState = run.state || run.status || 'pending';
    const labels = {
      pending: 'Prêt', preparing: 'Préparation', blocked: 'Erreur de préparation',
      running: 'En cours', completed: 'Terminé', failed: 'Échec', cancelled: 'Arrêté'
    };
    const stateLabel = labels[runState] || runState;
    const count = run.total_frames ? ` · ${run.completed_frames || 0}/${run.total_frames} images` : '';
    const available = Boolean(run.results_available || run.completed_frames > 0 || runState === 'completed');
    return `<div class="run-row ${active?'selected':''}" data-run-id="${htmlEscape(id)}"><button type="button" class="run-select" aria-pressed="${active}" aria-label="Afficher l’état du run ${htmlEscape(id)}"><strong>${htmlEscape(id)}</strong><small>${htmlEscape(stateLabel+count)} · ${htmlEscape(run.updated_utc||'')}</small></button><div class="run-actions"><button type="button" class="button primary" data-run-start ${run.can_start?'':'disabled'}>Lancer</button><button type="button" class="button outline" data-run-action="stop" ${runState==='running'?'':'disabled'}>Stop</button><button type="button" class="button outline" data-run-action="restart" ${['failed','cancelled'].includes(runState)?'':'disabled'}>Redémarrer</button><button type="button" class="button outline danger" data-run-action="delete" ${['preparing','running'].includes(runState)?'disabled':''}>Supprimer</button><button type="button" class="button outline" data-run-result ${available?'':'disabled title="Résultats disponibles après la première image validée"'}>Résultats</button></div>${renderRunPreparation(run)}</div>`;
  }
  async function populateRuns(){
    const host=$('#run-list');if(!host)return;
    if(runListTimer){clearTimeout(runListTimer);runListTimer=null;}
    try{
      const projectKey=state.projectKey,runs=recordsFrom(await api('/api/runs'));
      if(projectKey!==state.projectKey||state.view!=='Job Manager')return;
      refreshReadiness();
      if(!runs.length){host.innerHTML='<div class="empty-inline">Aucun job dans cette étude.</div>';rememberRun(null);$('#run-status').textContent='Préparez un job pour vérifier les prérequis et créer sa ligne.';return;}
      const preferred=state.selectedRun||localStorage.getItem(selectedRunStorageKey());if(preferred&&!state.selectedRun)rememberRun(preferred);
      if(preferred&&!runs.some(run=>run.id===preferred))rememberRun(null);
      host.innerHTML = runs.map(renderRunRow).join('');
      host.querySelectorAll('.run-select').forEach(button=>button.addEventListener('click',()=>{const id=button.closest('.run-row').dataset.runId;rememberRun(id);host.querySelectorAll('.run-row').forEach(row=>{row.classList.toggle('selected',row.dataset.runId===id);row.querySelector('.run-select').setAttribute('aria-pressed',String(row.dataset.runId===id));});const run=runs.find(row=>row.id===id);if(run)renderRunSummary(run);}));
      host.querySelectorAll('[data-run-result]').forEach(button=>button.addEventListener('click',()=>{rememberRun(button.closest('.run-row').dataset.runId);selectView('Résultats');}));
      host.querySelectorAll('[data-run-start]').forEach(button=>button.addEventListener('click',()=>launchRun(button.closest('.run-row').dataset.runId)));
      host.querySelectorAll('[data-run-action]').forEach(button=>button.addEventListener('click',()=>runAction(button.closest('.run-row').dataset.runId,button.dataset.runAction)));
      const selected=runs.find(run=>run.id===state.selectedRun);if(selected)renderRunSummary(selected);else $('#run-status').textContent='Sélectionnez un run pour consulter son état.';
      if(runs.some(run=>['preparing','running'].includes(run.state)))runListTimer=setTimeout(()=>{if(state.view==='Job Manager')populateRuns();},1500);
    }catch(error){host.innerHTML=`<div class="empty-inline">Liste des runs indisponible : ${htmlEscape(error.message)}</div>`;}
  }
  async function loadJobManager(){
    setStage(`<div class="results-view job-view"><div class="results-head"><span class="eyebrow">CALCULS DE L’ÉTUDE</span><div class="readiness-actions"><button class="button primary" id="prepare-run">Préparer le job</button></div></div><div id="run-status" class="run-summary">Préparez un job pour vérifier les prérequis et créer sa ligne.</div><div id="run-list" class="run-list"></div></div>`);
    $('#prepare-run').addEventListener('click',prepareRun);
    await Promise.all([refreshReadiness(), populateRuns()]);
  }
  async function loadResults(){
    setStage(`<div class="results-view result-view"><div class="result-view-head"><div><strong id="result-run-name">Résultats</strong><small id="result-run-progress"></small></div><button class="button outline" id="back-to-jobs">Job Manager</button></div><div id="run-fields" class="run-fields"></div></div>`);
    $('#back-to-jobs').addEventListener('click',()=>selectView('Job Manager'));
    if(resultRefreshTimer)clearTimeout(resultRefreshTimer);resultRefreshTimer=null;resultMetadata=null;resultDisplay=null;
    try{const projectKey=state.projectKey,runs=recordsFrom(await api('/api/runs'));if(projectKey!==state.projectKey||state.view!=='Résultats')return;let id=state.selectedRun||localStorage.getItem(selectedRunStorageKey());let run=runs.find(item=>(item.id||item.run_id)===id);if(!run||!['pending','running'].includes(run.state||run.status)&&!(run.results_available||run.completed_frames>0||run.state==='completed')){run=runs.find(item=>item.results_available||item.completed_frames>0||item.state==='completed')||runs.find(item=>['pending','running'].includes(item.state));id=run?.id||run?.run_id;}if(!id){$('#run-fields').innerHTML='<div class="empty-inline">Aucun calcul disponible. Lancez un calcul dans Job Manager.</div>';return;}rememberRun(id);$('#result-run-name').textContent='Résultats';renderResultRunStatus(id,run);if(!(run.results_available||run.completed_frames>0||run.state==='completed')){$('#run-fields').innerHTML='<div class="empty-inline" role="status">Calcul en préparation. Les résultats apparaîtront dès que le maillage sera prêt.</div>';scheduleRunAvailability(id);return;}await loadRunDetails(id);}catch(error){$('#run-fields').textContent=`Résultats indisponibles : ${error.message}`;}
  }
  function scheduleRunAvailability(id){
    if(resultRefreshTimer)clearTimeout(resultRefreshTimer);
    const projectKey=state.projectKey;
    resultRefreshTimer=setTimeout(async()=>{
      if(state.projectKey!==projectKey||state.view!=='Résultats'||state.selectedRun!==id)return;
      try{
        const runs=recordsFrom(await api('/api/runs'));
        if(state.projectKey!==projectKey||state.view!=='Résultats'||state.selectedRun!==id)return;
        const run=runs.find(item=>(item.id||item.run_id)===id);
        if(!run){$('#run-fields').innerHTML='<div class="empty-inline" role="status">Ce run n’est plus disponible.</div>';return;}
        if(['failed','cancelled'].includes(run.state||run.status)&&!run.results_available&&!run.completed_frames){renderResultRunStatus(id,run);$('#run-fields').innerHTML=`<div class="empty-inline" role="status">Calcul ${run.state==='failed'?'en échec':'arrêté'} avant la disponibilité des résultats.</div>`;return;}
        if(run.results_available||run.completed_frames>0||run.state==='completed')await loadResults();
        else scheduleRunAvailability(id);
      }catch{if(state.projectKey===projectKey&&state.view==='Résultats'&&state.selectedRun===id)scheduleRunAvailability(id);}
    },1500);
  }
  function renderResultRunStatus(id,metadata){const host=$('#result-run-progress');if(!host)return;const labels={pending:'En attente',running:'En cours',completed:'Terminé',failed:'Échec',cancelled:'Arrêté'};const stateName=metadata.state||'pending',completed=Number(metadata.completed_frames)||0,total=Number(metadata.total_frames)||0;host.textContent=`${id} · ${labels[stateName]||stateName} · ${completed}/${total||'—'} images`;}
  function reflectField(path,value){const input=document.querySelector(`[data-path="${path}"]`);if(!input)return;if(input.type==='checkbox')input.checked=Boolean(value);else if(input.multiple)Array.from(input.options).forEach(option=>{option.selected=value.includes(option.value);});else input.value=Array.isArray(value)?JSON.stringify(value):String(value??'');}
  let scaleResizeObserver = null;
  function setupScaleCanvas() {
    const image = $('#dic-image'), canvas = $('#scale-canvas');
    const magnifier = $('#scale-magnifier');
    if (!image || !canvas || !magnifier) return null;
    const frame = canvas.parentElement, ctx = canvas.getContext('2d');
    const lens = magnifier.getContext('2d');
    let ready = false, active = null, selected = null;
    const points = () => Array.isArray(state.config.scale?.segment_xy_px)
      ? state.config.scale.segment_xy_px.filter(p => Array.isArray(p) && p.length === 2 &&
          p.every(value => Number.isFinite(Number(value)))).map(p => p.map(Number)) : [];
    const clamp = (value, limit) => Math.max(0, Math.min(limit - 1, value));
    const pointAt = event => {
      const rect = canvas.getBoundingClientRect();
      return [
        Math.round(clamp((event.clientX - rect.left) * canvas.width / rect.width, canvas.width) * 10) / 10,
        Math.round(clamp((event.clientY - rect.top) * canvas.height / rect.height, canvas.height) * 10) / 10
      ];
    };
    const hitHandle = event => {
      const rect = canvas.getBoundingClientRect();
      const p = pointAt(event);
      return points().findIndex(q => Math.hypot(
        (q[0] - p[0]) * rect.width / canvas.width,
        (q[1] - p[1]) * rect.height / canvas.height
      ) <= 15);
    };
    const draw = () => {
      if (!ready) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const ps = points(), rect = canvas.getBoundingClientRect();
      const ratio = canvas.width / Math.max(rect.width, 1);
      if (ps.length === 2) {
        ctx.strokeStyle = '#f47b42';
        ctx.lineWidth = 3 * ratio;
        ctx.beginPath(); ctx.moveTo(...ps[0]); ctx.lineTo(...ps[1]); ctx.stroke();
      }
      ps.forEach((p, index) => {
        ctx.beginPath(); ctx.arc(p[0], p[1], 7 * ratio, 0, 2 * Math.PI);
        ctx.fillStyle = '#f47b42'; ctx.fill();
        ctx.strokeStyle = '#fff'; ctx.lineWidth = 2 * ratio; ctx.stroke();
        ctx.fillStyle = '#fff'; ctx.font = `bold ${12 * ratio}px sans-serif`;
        ctx.fillText(String(index + 1), p[0] + 10 * ratio, p[1] - 10 * ratio);
      });
    };
    const hideMagnifier = () => { magnifier.hidden = true; };
    const showMagnifier = index => {
      if (!ready || !points()[index]) return;
      const p = points()[index], size = magnifier.width, crop = 26;
      lens.clearRect(0, 0, size, size);
      lens.fillStyle = '#202522'; lens.fillRect(0, 0, size, size);
      lens.imageSmoothingEnabled = false;
      lens.drawImage(image, p[0] - crop / 2, p[1] - crop / 2,
                     crop, crop, 0, 0, size, size);
      const center = size / 2;
      lens.strokeStyle = '#fff'; lens.lineWidth = 3;
      lens.beginPath(); lens.moveTo(center - 17, center); lens.lineTo(center + 17, center);
      lens.moveTo(center, center - 17); lens.lineTo(center, center + 17); lens.stroke();
      lens.strokeStyle = '#f47b42'; lens.lineWidth = 1.5;
      lens.beginPath(); lens.moveTo(center - 17, center); lens.lineTo(center + 17, center);
      lens.moveTo(center, center - 17); lens.lineTo(center, center + 17); lens.stroke();
      lens.fillStyle = '#17221edb'; lens.fillRect(0, size - 23, size, 23);
      lens.fillStyle = '#fff'; lens.font = '12px sans-serif';
      lens.fillText(`x ${p[0].toFixed(1)} · y ${p[1].toFixed(1)} px`, 8, size - 7);
      const imageRect = fieldImageGeometry(frame, image), frameRect = frame.getBoundingClientRect();
      if (!imageRect) return;
      const x = imageRect.left + p[0] * imageRect.width / image.naturalWidth;
      const y = imageRect.top + p[1] * imageRect.height / image.naturalHeight;
      const width = size + 4;
      magnifier.style.left = `${Math.max(4, Math.min(frameRect.width - width - 4,
        x + width + 24 < frameRect.width ? x + 20 : x - width - 20))}px`;
      magnifier.style.top = `${Math.max(4, Math.min(frameRect.height - width - 4,
        y - width - 20 >= 0 ? y - width - 20 : y + 20))}px`;
      magnifier.hidden = false;
    };
    const layout = () => {
      if (!image.naturalWidth || !image.naturalHeight) return;
      const ir = fieldImageGeometry(frame, image);
      if (!ir) return;
      if (canvas.width !== image.naturalWidth || canvas.height !== image.naturalHeight) {
        canvas.width = image.naturalWidth; canvas.height = image.naturalHeight;
      }
      canvas.style.left = `${ir.left}px`;
      canvas.style.top = `${ir.top}px`;
      canvas.style.width = `${ir.width}px`;
      canvas.style.height = `${ir.height}px`;
      ready = true; draw();
      if (active) showMagnifier(active.index);
    };
    const commit = () => {
      state.config.scale.method = 'segment';
      state.config.scale.confirmed = false;
      reflectField('scale.segment_xy_px', points());
      reflectField('scale.method', 'segment');
      reflectField('scale.confirmed', false);
      setDirty(); updateScalePreview();
    };
    image.addEventListener('load', layout);
    frame.addEventListener('imageviewchange', layout);
    scaleResizeObserver?.disconnect();
    scaleResizeObserver = new ResizeObserver(layout);
    scaleResizeObserver.observe(frame);
    scaleResizeObserver.observe(image);
    layout();
    canvas.tabIndex = 0;
    canvas.addEventListener('pointerdown', event => {
      if (!ready) return;
      let index = hitHandle(event), added = false;
      if (index < 0) {
        if (points().length >= 2) { selected = null; hideMagnifier(); return; }
        index = points().length;
        state.config.scale.segment_xy_px = [...points(), pointAt(event)];
        added = true;
      }
      selected = index;
      active = { pointerId: event.pointerId, index, changed: added };
      canvas.setPointerCapture(event.pointerId);
      canvas.focus(); draw(); showMagnifier(index);
      updateScalePreview();
      event.preventDefault();
    });
    canvas.addEventListener('pointermove', event => {
      if (!ready) return;
      if (!active || active.pointerId !== event.pointerId) {
        canvas.style.cursor = hitHandle(event) >= 0 ? 'grab' : 'crosshair';
        return;
      }
      const p = pointAt(event), previous = points()[active.index];
      if (previous[0] !== p[0] || previous[1] !== p[1]) {
        const next = points().map(q => [...q]);
        next[active.index] = p;
        state.config.scale.segment_xy_px = next;
        active.changed = true;
        state.config.scale.confirmed = false;
        draw(); updateScalePreview();
      }
      showMagnifier(active.index);
      canvas.style.cursor = 'grabbing';
    });
    const finish = event => {
      if (!active || active.pointerId !== event.pointerId) return;
      if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
      if (active.changed) commit();
      active = null; showMagnifier(selected); canvas.style.cursor = 'crosshair';
    };
    canvas.addEventListener('pointerup', finish);
    canvas.addEventListener('pointercancel', finish);
    canvas.addEventListener('keydown', event => {
      if (selected === null || !points()[selected] || !event.key.startsWith('Arrow')) return;
      const directions = { ArrowLeft: [-1, 0], ArrowRight: [1, 0],
                           ArrowUp: [0, -1], ArrowDown: [0, 1] };
      const delta = directions[event.key]; if (!delta) return;
      event.preventDefault();
      const step = event.shiftKey ? 10 : 1;
      const next = points().map(q => [...q]);
      next[selected] = [clamp(next[selected][0] + delta[0] * step, canvas.width),
                        clamp(next[selected][1] + delta[1] * step, canvas.height)];
      state.config.scale.segment_xy_px = next;
      commit(); draw(); showMagnifier(selected);
    });
    canvas.addEventListener('blur', () => { selected = null; hideMagnifier(); });
    return { refresh: draw, hideMagnifier };
  }
  function updateScalePreview() {
    const points = Array.isArray(state.config.scale?.segment_xy_px)
      ? state.config.scale.segment_xy_px.filter(p => Array.isArray(p) && p.length === 2 &&
          p.every(value => Number.isFinite(Number(value)))).map(p => p.map(Number)) : [];
    const length = Number($('#segment-length-mm')?.value ?? state.config.scale?.segment_length_mm ?? 0);
    const pixels = points.length === 2
      ? Math.hypot(points[1][0] - points[0][0], points[1][1] - points[0][1]) : 0;
    const factor = pixels > 0 && length > 0 ? length / pixels : null;
    const coordinates = $('#scale-coordinates');
    if (coordinates) coordinates.textContent = points.map((p, i) =>
      `P${i + 1} (${Number(p[0]).toFixed(1)}, ${Number(p[1]).toFixed(1)}) px VIS`).join(' · ') ||
      'Placez la première extrémité sur l’image.';
    $('#scale-preview').textContent = factor
      ? `Distance ${pixels.toFixed(2)} px · aperçu ${factor.toPrecision(6)} mm/px${state.config.scale.confirmed ? ' · confirmé' : ' · à confirmer'}`
      : points.length < 2 ? 'Placez deux extrémités puis saisissez la longueur connue.'
      : pixels <= 0 ? 'Écartez les deux extrémités du segment.'
      : 'Saisissez une longueur réelle positive en mm.';
    const current = $('#scale-current');
    if (current) current.textContent = state.config.scale?.confirmed
      ? `Échelle confirmée : ${Number(state.config.scale.mm_per_pixel).toPrecision(6)} mm/px.`
      : factor ? `Aperçu : ${factor.toPrecision(6)} mm/px · à confirmer.`
      : `Échelle non étalonnée · facteur saisi ${Number(state.config.scale?.mm_per_pixel ?? 1).toPrecision(6)} mm/px.`;
    const confirm = $('#confirm-scale'); if (confirm) confirm.disabled = !factor;
  }
  async function loadDicView() {
    let path = resolveSource(state.config.paths?.reference_image || '',
                             state.config.paths?.visible_dir || '');
    try {
      const data = await api('/api/visible');
      if (state.view !== 'Échelle') return;
      const images = recordsFrom(data);
      if (!path) path = recordPath(images[0]);
      const active = images.length - (state.config.paths?.excluded_images || []).length;
      setStage(`<div class="dic-view"><div class="dic-preview">${imageMarkup(path, 'Référence VIS pour l’étalonnage', true, true, false, 'dic-image')}<canvas id="scale-canvas" aria-label="Tracer et retoucher le segment d’échelle. Flèches pour déplacer l’extrémité sélectionnée."></canvas><canvas id="scale-magnifier" width="156" height="156" hidden aria-hidden="true"></canvas></div><div class="dic-summary"><span class="eyebrow">PRÉPARATION DIC</span><h2>${active} images VIS actives sur ${images.length}</h2><p id="scale-current"></p><div class="scale-tool"><strong>Mesurer un segment connu</strong><p class="scale-instructions">Cliquez deux extrémités sur l’image. Glissez une poignée pour la retoucher ; la loupe reste visible tant que le point est sélectionné. Flèches : 1 px, Maj + flèches : 10 px.</p><div id="scale-coordinates" class="scale-coordinates"></div><label>Longueur réelle <input id="segment-length-mm" type="number" min="0" step="any" value="${htmlEscape(state.config.scale?.segment_length_mm ?? 0)}"> mm</label><div id="scale-preview" class="inline-status"></div><div class="scale-actions"><button class="button outline" id="clear-segment">Effacer le segment</button><button class="button primary" id="confirm-scale">Confirmer l’échelle</button></div></div><button class="button outline" id="show-dic-settings">Ouvrir les paramètres DIC</button></div></div>`);
      const scaleCanvas = setupScaleCanvas();
      $('#segment-length-mm').addEventListener('input', () => {
        const value = Number($('#segment-length-mm').value) || 0;
        state.config.scale.segment_length_mm = value;
        reflectField('scale.segment_length_mm', value);
        state.config.scale.confirmed = false;
        reflectField('scale.confirmed', false);
        setDirty(); updateScalePreview();
      });
      $('#confirm-scale').addEventListener('click', () => {
        const pts = state.config.scale.segment_xy_px || [];
        const length = Number(state.config.scale.segment_length_mm);
        if (pts.length !== 2 || length <= 0) return;
        const px = Math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]);
        if (!px) return;
        state.config.scale.method = 'segment';
        state.config.scale.mm_per_pixel = length / px;
        state.config.scale.confirmed = true;
        reflectField('scale.method', 'segment');
        reflectField('scale.mm_per_pixel', state.config.scale.mm_per_pixel);
        reflectField('scale.confirmed', true);
        setDirty(); updateScalePreview();
      });
      $('#clear-segment').addEventListener('click', () => {
        state.config.scale.segment_xy_px = [];
        state.config.scale.confirmed = false;
        reflectField('scale.segment_xy_px', []);
        reflectField('scale.confirmed', false);
        setDirty(); scaleCanvas?.hideMagnifier(); scaleCanvas?.refresh(); updateScalePreview();
      });
      $('#show-dic-settings').addEventListener('click', () => {
        selectView('Réglages DIC');
        if (window.matchMedia('(max-width:760px)').matches)
          document.body.classList.add('settings-open');
        else setSettingsExpanded(true);
        const input = document.querySelector('[data-path="dic.image_stride"]');
        if (input) { input.scrollIntoView({ block: 'center', behavior: 'smooth' }); input.focus(); }
      });
      updateScalePreview();
    } catch (error) {
      if (state.view === 'Échelle')
        setStage(`<div class="empty-visual"><h2>Aperçu d’échelle indisponible</h2><p>${htmlEscape(error.message)}</p></div>`);
    }
  }
  function loadDicSettingsView() {
    const paths = state.config.paths || {};
    const reference = resolveSource(paths.reference_image || '', paths.visible_dir || '');
    setStage('<div class="dic-settings-preview">' +
      (reference ? imageMarkup(reference, 'Référence VIS pour les réglages DIC', true, true)
        : '<div class="empty-visual"><h2>Référence VIS absente</h2><p>Choisissez-la dans VIS avant de régler la DIC.</p></div>') +
      '</div>');
  }
  async function loadExportView(){
    const unit=state.config.output?.paraview_length_unit||'px';
    setStage(`<div class="results-view"><span class="eyebrow">EXPORT PARAVIEW</span><h2>Fichiers du run</h2><p>Longueur : ${htmlEscape(unit)} · VTU ${state.config.output?.export_vtu?'activé':'désactivé'} · PVD ${state.config.output?.export_pvd?'activé':'désactivé'}. Les résultats DIC sont conservés par image ; l’archive NPZ globale est facultative.</p><div class="inline-status" id="export-status">Sélectionnez un run terminé dans Job Manager.</div><div class="scale-actions"><button class="button primary" id="export-run">Afficher les chemins ParaView</button><button class="button outline" id="export-npz">Créer une archive NPZ compatible</button></div><div id="export-paths" class="export-paths"></div></div>`);
    const show=async legacy_npz=>{
      if(!state.selectedRun){$('#export-status').textContent='Sélectionnez d’abord un run dans Job Manager.';return;}
      try{
        const result=await api(`/api/runs/${encodeURIComponent(state.selectedRun)}/export`,{method:'POST',body:JSON.stringify({legacy_npz})});
        $('#export-status').textContent=result.message||'Chemins disponibles.';
        const entries=[['Série DIC',result.dic_pvd],['Série couplée',result.coupled_pvd],['Archive NPZ',result.legacy_npz],['Manifeste',result.manifest]];
        $('#export-paths').innerHTML=entries.filter(([,path])=>path).map(([label,path])=>`<div class="export-path"><strong>${htmlEscape(label)}</strong><code>${htmlEscape(path)}</code></div>`).join('')||'<div class="empty-inline">Aucun fichier exporté avec cette configuration.</div>';
      }catch(e){$('#export-status').textContent=`Export indisponible : ${e.message}`;}
    };
    $('#export-run').addEventListener('click',()=>show(false));
    $('#export-npz').addEventListener('click',()=>show(true));
  }
  async function loadViewContent(view){if(['Thermique','Synchro'].includes(view)&&state.config.project?.mode!=='dic_thermal'){setStage('<div class="empty-visual"><h2>Étape inactive</h2><p>Choisissez le parcours DIC + thermique pour préparer les images TH et leur synchronisation.</p></div>');return;}if(view==='VIS')return loadVisible();if(view==='Thermique')return loadThermal();if(view==='ROI')return loadROI();if(view==='Synchro')return loadSynchronization();if(view==='Job Manager')return loadJobManager();if(view==='Résultats')return loadResults();if(view==='Échelle')return loadDicView();if(view==='Réglages DIC')return loadDicSettingsView();if(view==='Export')return loadExportView();}

  let applyWorkspaceColumns = null;
  function setSettingsExpanded(expanded) {
    document.body.classList.toggle('settings-collapsed', !expanded);
    const button = $('#collapse-settings');
    button.textContent = expanded ? '›' : '‹';
    button.setAttribute('aria-expanded', String(expanded));
    button.setAttribute('aria-label', expanded ? 'Replier les paramètres' : 'Développer les paramètres');
    button.title = expanded ? 'Replier les paramètres' : 'Développer les paramètres';
    localStorage.setItem('d2ic-settings-expanded', expanded ? '1' : '0');
    applyWorkspaceColumns?.();
  }
  function setupSplitter() {
    const splitter = $('#splitter'), workspace = $('#workspace');
    const stored = Number(localStorage.getItem('d2ic-panel-ratio'));
    if (stored >= .45 && stored <= .75) state.ratio = stored;
    const apply = () => {
      if (window.matchMedia('(max-width:760px)').matches) {
        workspace.style.gridTemplateColumns = 'minmax(0,1fr)';
        splitter.setAttribute('aria-valuenow', '30');
      } else if (document.body.classList.contains('settings-collapsed')) {
        workspace.style.gridTemplateColumns = 'minmax(0,1fr) 0px 44px';
        splitter.setAttribute('aria-valuenow', '0');
      } else {
        const available = Math.max(0, workspace.clientWidth - 8);
        const center = Math.max(0, Math.min(available - 320, Math.round(available * state.ratio)));
        workspace.style.gridTemplateColumns = `minmax(0,${center}px) 8px minmax(0,${available - center}px)`;
        splitter.setAttribute('aria-valuenow', String(Math.round(100 * (available - center) / Math.max(available, 1))));
      }
    };
    applyWorkspaceColumns = apply;
    let startX = 0, startRatio = 0;
    splitter.addEventListener('pointerdown', event => { if (window.matchMedia('(max-width:760px)').matches || document.body.classList.contains('settings-collapsed')) return; startX = event.clientX; startRatio = state.ratio; splitter.setPointerCapture(event.pointerId); splitter.classList.add('dragging'); });
    splitter.addEventListener('pointermove', event => { if (!splitter.hasPointerCapture(event.pointerId)) return; const bounds = workspace.getBoundingClientRect(); state.ratio = Math.max(.45, Math.min(.75, startRatio + (event.clientX - startX) / bounds.width)); apply(); });
    const finish = event => { if (!splitter.hasPointerCapture(event.pointerId)) return; splitter.releasePointerCapture(event.pointerId); splitter.classList.remove('dragging'); localStorage.setItem('d2ic-panel-ratio', String(state.ratio)); };
    splitter.addEventListener('pointerup', finish); splitter.addEventListener('pointercancel', finish);
    splitter.addEventListener('dblclick', () => { state.ratio = .70; localStorage.removeItem('d2ic-panel-ratio'); apply(); });
    splitter.addEventListener('keydown', event => { if (!['ArrowLeft','ArrowRight','Home'].includes(event.key)) return; event.preventDefault(); state.ratio = event.key === 'Home' ? .70 : Math.max(.45, Math.min(.75, state.ratio + (event.key === 'ArrowLeft' ? -.025 : .025))); apply(); localStorage.setItem('d2ic-panel-ratio', String(state.ratio)); });
    new ResizeObserver(apply).observe(workspace);
    window.addEventListener('resize', apply); apply();
  }
  document.querySelectorAll('.nav-item').forEach(item => item.addEventListener('click', () => selectView(item.dataset.view)));
  const fileMenuTrigger = $('#file-menu-trigger');
  const fileMenuPanel = $('#file-menu-panel');
  function setFileMenuOpen(open) {
    fileMenuPanel.hidden = !open;
    fileMenuTrigger.setAttribute('aria-expanded', String(open));
  }
  fileMenuTrigger.addEventListener('click', () => setFileMenuOpen(fileMenuPanel.hidden));
  fileMenuPanel.addEventListener('click', event => { if (event.target.closest('button')) setFileMenuOpen(false); });
  document.addEventListener('pointerdown', event => {
    if (!event.target.closest('.file-menu')) setFileMenuOpen(false);
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !fileMenuPanel.hidden) { setFileMenuOpen(false); fileMenuTrigger.focus(); }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); setFileMenuOpen(false); save(); }
  });
  $('#save-study').addEventListener('click', save); $('#save-config').addEventListener('click', save);
  const collapseNav = $('#collapse-nav');
  function setNavigationExpanded(expanded) {
    document.body.classList.toggle('nav-collapsed', !expanded);
    collapseNav.setAttribute('aria-expanded', String(expanded));
    collapseNav.setAttribute('aria-label', expanded ? 'Replier la navigation' : 'Développer la navigation');
    collapseNav.title = expanded ? 'Replier la navigation' : 'Développer la navigation';
    localStorage.setItem('d2ic-nav-expanded', expanded ? '1' : '0');
  }
  setNavigationExpanded(localStorage.getItem('d2ic-nav-expanded') === '1');
  collapseNav.addEventListener('click', () => setNavigationExpanded(document.body.classList.contains('nav-collapsed')));
  $('#nav-toggle').addEventListener('click', () => document.body.classList.toggle('nav-open'));
  $('#image-view').addEventListener('click', () => document.body.classList.remove('settings-open'));
  $('#parameters-view').addEventListener('click', () => document.body.classList.add('settings-open'));
  $('#close-settings').addEventListener('click', () => document.body.classList.remove('settings-open'));
  setSettingsExpanded(localStorage.getItem('d2ic-settings-expanded') !== '0');
  $('#collapse-settings').addEventListener('click', () =>
    setSettingsExpanded(document.body.classList.contains('settings-collapsed')));
  $('#scrim').addEventListener('click', () => document.body.classList.remove('nav-open'));
  $('#choose-images').addEventListener('click', () => browseField('paths.visible_dir'));
  async function switchProject(route, payload) { try { const result = await api(route,{method:'POST',body:JSON.stringify(payload)}); normalizeProject(result); renderFields(); setDirty(false); selectView('VIS'); $('#config-message').textContent = 'Étude ouverte : ' + result.folder; } catch(e) { notify('Action impossible',e.message); } }
  $('#new-study').addEventListener('click', async () => {
    const parent = state.project.folder ? state.project.folder.slice(0, state.project.folder.lastIndexOf('/')) || '/' : '';
    const folder = await openExplorer({ mode: 'new_directory', kind: 'directory', title: 'Nouvelle étude', initialPath: parent, suggestedName: 'nouvelle_etude' });
    if (folder) switchProject('/api/project/new', { folder, name: folder.split('/').pop(), mode: state.config.project?.mode || 'dic' });
  });
  $('#open-study').addEventListener('click', async () => {
    const parent = state.project.folder ? state.project.folder.slice(0, state.project.folder.lastIndexOf('/')) || '/' : '';
    const folder = await openExplorer({ mode: 'study', kind: 'study', title: 'Ouvrir une étude', initialPath: parent });
    if (folder) switchProject('/api/project/open', { folder });
  });
  $('#save-as-study').addEventListener('click', async () => {
    if (!state.project.folder) { notify('Enregistrer sous', 'Créez d’abord une étude.'); return; }
    const parent = state.project.folder.slice(0, state.project.folder.lastIndexOf('/')) || '/';
    const suggestedName = (state.config.project?.name || 'etude') + '_copie';
    const folder = await openExplorer({ mode: 'new_directory', kind: 'directory', title: 'Enregistrer l’étude sous', initialPath: parent, suggestedName });
    if (folder) switchProject('/api/project/copy', { folder, name: folder.split('/').pop(), config: state.config });
  });
  $('#copy-study').addEventListener('click', async () => {
    const parent = state.project.folder ? state.project.folder.slice(0, state.project.folder.lastIndexOf('/')) || '/' : '';
    const folder = await openExplorer({ mode: 'new_directory', kind: 'directory', title: 'Copier l’étude', initialPath: parent, suggestedName: 'copie_etude' });
    if (folder) switchProject('/api/project/copy', { folder, name: state.config.project?.name + ' copie', config: state.config });
  });
  $('#relink-study').addEventListener('click', async () => {
    if (state.dirty && !await save()) return;
    const visible_dir = await openExplorer({ mode: 'directory', kind: 'directory', title: 'Retrouver les images VIS', initialPath: state.config.paths?.visible_dir || state.project.folder });
    const thermal_dir = state.config.project?.mode === 'dic_thermal'
      ? await openExplorer({ mode: 'directory', kind: 'directory', title: 'Retrouver les images thermiques', initialPath: state.config.thermal?.image_dir || state.project.folder })
      : null;
    if (!visible_dir && !thermal_dir) return;
    try {
      const result = await api('/api/project/relink', { method: 'POST', body: JSON.stringify({ visible_dir, thermal_dir: thermal_dir || undefined }) });
      state.config = result.config; renderFields(); setDirty(false); selectView(state.view);
      $('#config-message').textContent = 'Sources relocalisées après vérification.';
    } catch (error) { $('#config-message').textContent = 'Relocalisation impossible : ' + error.message; }
  });
  $('#readiness-close').addEventListener('click', () => $('#readiness-dialog').close());
  window.addEventListener('focus', () => { if (state.config.project) scheduleReadiness(); });
  $('#recent-runs').addEventListener('click', () => selectView('Job Manager'));
  $('#project-mode').addEventListener('change', () => { state.config.project.mode=$('#project-mode').value; renderFields(); setDirty(); if(state.view==='Thermique'||state.view==='Synchro')state.view='VIS'; selectView(state.view); });
  new MutationObserver(setupImageViews).observe($('#stage-content'), { childList: true, subtree: true });
  setupSplitter(); load().then(()=>loadViewContent('VIS'));
})();
