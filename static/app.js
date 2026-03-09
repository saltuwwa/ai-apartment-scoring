(function () {
  const CRITERIA = {
    cleanliness: { ru: 'Чистота', key: 'cleanliness' },
    repair_condition: { ru: 'Состояние ремонта', key: 'repair_condition' },
    modernity: { ru: 'Актуальность дизайна', key: 'modernity' },
    lighting: { ru: 'Освещённость', key: 'lighting' },
    clutter: { ru: 'Захламлённость', key: 'clutter' },
  };

  function $(sel, el = document) { return el.querySelector(sel); }
  function $$(sel, el = document) { return el.querySelectorAll(sel); }

  const loading = document.getElementById('loading');
  const error = document.getElementById('error');

  function showLoading(y) {
    loading.style.display = y ? 'block' : 'none';
  }
  function showError(msg) {
    error.textContent = msg;
    error.style.display = 'block';
    setTimeout(() => { error.style.display = 'none'; }, 5000);
  }

  // Табы
  $$('.tab').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('.tab').forEach(b => b.classList.remove('active'));
      $$('.panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('panel-' + btn.dataset.tab).classList.add('active');
    });
  });

  // Model info
  fetch('/api/model-info').then(r => r.json()).then(d => {
    const el = document.getElementById('modelInfo');
    if (el) el.textContent = `Оценивает: ${d.name} (${d.type}), ${d.provider}`;
  }).catch(() => {});

  // Upload zones
  function setupUpload(zoneId, fileId, previewId) {
    const zone = document.getElementById(zoneId);
    const file = document.getElementById(fileId);
    const preview = document.getElementById(previewId);
    zone.addEventListener('click', () => file.click());
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag'));
    zone.addEventListener('drop', e => {
      e.preventDefault();
      zone.classList.remove('drag');
      if (e.dataTransfer.files.length) {
        file.files = e.dataTransfer.files;
        showPreview(file, preview, zone);
      }
    });
    file.addEventListener('change', () => showPreview(file, preview, zone));
  }

  function showPreview(fileInput, img, zone) {
    if (!fileInput.files || !fileInput.files[0]) return;
    const fr = new FileReader();
    fr.onload = () => {
      img.src = fr.result;
      zone.classList.add('has-image');
    };
    fr.readAsDataURL(fileInput.files[0]);
  }

  setupUpload('uploadZone1', 'file1', 'preview1');
  setupUpload('uploadZone2', 'file2', 'preview2');

  // Задание 1: Оценка
  document.getElementById('btnScore').addEventListener('click', async () => {
    const fileInput = document.getElementById('file1');
    if (!fileInput.files || !fileInput.files[0]) {
      showError('Выберите фото');
      return;
    }
    showLoading(true);
    const fd = new FormData();
    fd.append('file', fileInput.files[0]);
    try {
      const res = await fetch('/api/score', { method: 'POST', body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      renderScoreResult(data);
    } catch (e) {
      showError(e.message);
    } finally {
      showLoading(false);
    }
  });

  function renderScoreResult(data) {
    const box = document.getElementById('scoreResult');
    const s = data.score || {};
    let html = '<div class="success-banner">Оценка успешно завершена!</div>';
    html += '<table class="eval-table"><thead><tr><th>Критерий</th><th>Оценка</th><th>Обоснование</th></tr></thead><tbody>';
    for (const [key, info] of Object.entries(CRITERIA)) {
      const score = s[key];
      const just = s[key + '_justification'] || s[key + 'Justification'] || '-';
      html += `<tr><td>${info.ru}</td><td class="score">${score != null ? score : '-'}</td><td class="just">${just}</td></tr>`;
    }
    html += '</tbody></table>';
    html += `<p class="overall-badge">Итого: ${data.overall ?? s.overall_score ?? '-'}/10</p>`;
    if (s.summary) html += `<p style="margin-top:8px;font-size:13px;color:#6c757d">${s.summary}</p>`;
    box.innerHTML = html;
  }

  // Задание 2: Стейджинг
  document.getElementById('btnStaging').addEventListener('click', async () => {
    const fileInput = document.getElementById('file2');
    if (!fileInput.files || !fileInput.files[0]) {
      showError('Выберите фото');
      return;
    }
    showLoading(true);
    const fd = new FormData();
    fd.append('file', fileInput.files[0]);
    fd.append('prompt', document.getElementById('stagingPrompt').value || 'Replace sofa with modern gray sofa');
    fd.append('input_fidelity', document.getElementById('inputFidelity').value);
    fd.append('quality', document.getElementById('quality').value);
    fd.append('size', document.getElementById('size').value);
    fd.append('use_db', document.getElementById('useDb').checked ? 'true' : 'false');
    try {
      const res = await fetch('/api/full-with-image', { method: 'POST', body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      renderStagingResult(data, fileInput.files[0]);
    } catch (e) {
      showError(e.message);
    } finally {
      showLoading(false);
    }
  });

  function renderStagingResult(data, file) {
    const box = document.getElementById('stagingResult');
    let html = '<div class="success-banner">Стейджинг выполнен!</div>';
    html += `<p>${(data.report || '').replace(/\n/g, '<br>')}</p>`;
    if (data.staged_image_base64) {
      const beforeUrl = URL.createObjectURL(file);
      html += '<div class="before-after">';
      html += `<div><img src="${beforeUrl}" alt="До"><p class="caption">До: ${data.overall_before ?? '-'}/10</p></div>`;
      html += `<div><img src="data:image/jpeg;base64,${data.staged_image_base64}" alt="После"><p class="caption">После: ${data.overall_after ?? '-'}/10</p></div>`;
      html += '</div>';
    } else if (data.error_staging) {
      html += `<p style="color:#c0392b">Ошибка стейджинга: ${data.error_staging}</p>`;
    }
    if (data.furniture_matches && data.furniture_matches.length) {
      html += '<div class="furniture-list"><strong>Добавленная мебель:</strong><ul>';
      data.furniture_matches.forEach(m => {
        const price = m.price_kzt != null ? `${Number(m.price_kzt).toLocaleString()} ₸` : 'не найдено';
        html += `<li>${m.model_name || m} — ${price}</li>`;
      });
      html += '</ul>';
      html += `<p class="cost-total">Примерная стоимость: ${(data.total_cost_kzt || 0).toLocaleString()} ₸</p></div>`;
    }
    box.innerHTML = html;
  }

  // Задание 3: DB status
  document.getElementById('btnDbStatus').addEventListener('click', async () => {
    const box = document.getElementById('dbStatus');
    box.innerHTML = 'Проверка…';
    try {
      const res = await fetch('/api/db-status');
      const data = await res.json();
      box.innerHTML = data.ok
        ? '<div class="success-banner">✅ ' + data.message + '</div>'
        : '<div style="color:#c0392b">❌ ' + data.message + '</div>';
    } catch (e) {
      box.innerHTML = '<div style="color:#c0392b">Ошибка: ' + e.message + '</div>';
    }
  });
})();
