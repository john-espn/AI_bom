(() => {
  'use strict';

  const navToggle = document.querySelector('[data-nav-toggle]');
  const nav = document.querySelector('[data-nav]');
  if (navToggle && nav) {
    navToggle.addEventListener('click', () => {
      const open = nav.classList.toggle('is-open');
      navToggle.setAttribute('aria-expanded', String(open));
      navToggle.setAttribute('aria-label', open ? '关闭导航' : '打开导航');
    });
  }

  document.querySelectorAll('[data-dismiss]').forEach((button) => {
    button.addEventListener('click', () => button.closest('.flash')?.remove());
  });

  document.querySelectorAll('[data-file-input]').forEach((input) => {
    const root = input.closest('[data-file-drop]');
    const label = root?.querySelector('[data-file-name]');
    const update = () => {
      if (!label) return;
      label.textContent = input.files?.[0]?.name || '尚未选择文件';
      root.classList.toggle('has-file', Boolean(input.files?.length));
    };
    input.addEventListener('change', update);
    if (root) {
      ['dragenter', 'dragover'].forEach((event) => root.addEventListener(event, (e) => {
        e.preventDefault();
        root.classList.add('is-dragging');
      }));
      ['dragleave', 'drop'].forEach((event) => root.addEventListener(event, (e) => {
        e.preventDefault();
        root.classList.remove('is-dragging');
      }));
      root.addEventListener('drop', (e) => {
        if (e.dataTransfer?.files?.length) {
          input.files = e.dataTransfer.files;
          update();
        }
      });
    }
  });

  document.querySelectorAll('form[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (!window.confirm(form.dataset.confirm || '确认执行此操作？')) event.preventDefault();
    });
  });

  document.querySelectorAll('[data-filter]').forEach((input) => {
    const selector = input.dataset.filter;
    input.addEventListener('input', () => {
      const query = input.value.trim().toLocaleLowerCase('zh-CN');
      document.querySelectorAll(selector).forEach((row) => {
        row.hidden = query && !row.textContent.toLocaleLowerCase('zh-CN').includes(query);
      });
    });
  });

  document.querySelectorAll('[data-copy]').forEach((button) => {
    button.addEventListener('click', async () => {
      const text = button.dataset.copy || '';
      try {
        await navigator.clipboard.writeText(text);
        const previous = button.textContent;
        button.textContent = '已复制';
        setTimeout(() => { button.textContent = previous; }, 1400);
      } catch (_) { /* Clipboard may be unavailable on non-secure origins. */ }
    });
  });

  document.querySelectorAll('textarea[data-count]').forEach((textarea) => {
    const output = document.getElementById(textarea.dataset.count);
    const update = () => { if (output) output.textContent = String(textarea.value.length); };
    textarea.addEventListener('input', update);
    update();
  });
})();
