function installCaeControls(root) {
  for (const section of root.querySelectorAll('[data-cae]')) {
    if (section.dataset.caeReady) continue;
    section.dataset.caeReady = '1';
    const inputs = Array.from(section.querySelectorAll('[data-cae-value]'));
    const safe = value => {
      value = String(value || '').replace(/\s+/g, ' ').trim();
      return /^[=+@-]/.test(value) ? "'" + value : value;
    };
    const line = () => inputs.map(input => safe(input.value)).join('\t');
    const fallback = section.querySelector('[data-cae-fallback]');
    const status = section.querySelector('[data-cae-status]');
    const copy = async value => {
      fallback.value = value;
      try {
        if (!navigator.clipboard?.writeText) throw new Error('Cópia manual');
        await navigator.clipboard.writeText(value);
        fallback.hidden = true;
        status.textContent = 'Copiado. Cole na primeira coluna de uma linha vazia da planilha.';
      } catch {
        fallback.hidden = false;
        fallback.focus();
        fallback.select();
        status.textContent = 'O navegador não permitiu a cópia automática. Copie o texto selecionado abaixo e cole na planilha.';
      }
    };
    section.querySelector('[data-cae-copy]').addEventListener('click', () => copy(line()));
    section.querySelector('[data-cae-headers]').addEventListener('click', () => copy(Array.from(section.querySelectorAll('[data-cae-label]')).map(label => label.textContent).join('\t')));
    for (const input of inputs) input.addEventListener('input', () => {
      fallback.value = line();
      status.textContent = 'Dados revisados nesta página. Clique em Copiar linha para planilha.';
    });
  }
}
installCaeControls(document);
