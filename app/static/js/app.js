// خفيف: تنشيط lazy loading + معالجات HTMX
document.addEventListener('htmx:responseError', e => console.warn('HTMX error', e.detail));
