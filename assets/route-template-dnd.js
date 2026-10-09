/* Native drag payloads stay local; only a completed drop reaches Reflex. */
(() => {
  if (window.__routeTemplateDnd) return;
  window.__routeTemplateDnd = true;
  let dragging = false;
  function clearTargets() {
    document.querySelectorAll('[data-route-drop].is-drop-target').forEach(node => node.classList.remove('is-drop-target'));
  }
  document.addEventListener('dragstart', event => {
    const handle = event.target.closest?.('[data-route-drag]');
    if (!handle || !event.dataTransfer) return;
    dragging = true;
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', JSON.stringify({source: Number(handle.dataset.source), name: handle.dataset.name}));
  });
  document.addEventListener('dragover', event => {
    const target = event.target.closest?.('[data-route-drop]');
    if (!dragging || !target) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    clearTargets();
    target.classList.add('is-drop-target');
  });
  document.addEventListener('dragleave', event => {
    const target = event.target.closest?.('[data-route-drop]');
    if (target && !target.contains(event.relatedTarget)) target.classList.remove('is-drop-target');
  });
  document.addEventListener('drop', event => {
    if (dragging && event.target.closest?.('[data-route-drop]')) event.preventDefault();
    dragging = false;
    clearTargets();
  });
  document.addEventListener('dragend', () => { dragging = false; clearTargets(); });
})();
