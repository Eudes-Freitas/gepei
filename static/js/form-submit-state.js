(function () {
  'use strict';

  function fields(form) {
    return Array.from(form.elements).filter(function (field) {
      return field.matches('input, select, textarea') &&
        !['hidden', 'submit', 'button', 'reset', 'image'].includes(field.type);
    });
  }

  function snapshot(form) {
    return JSON.stringify(fields(form).filter(function (field) {
      return !field.disabled;
    }).map(function (field) {
      var value = field.value;
      if (field.type === 'checkbox' || field.type === 'radio') {
        value = field.checked;
      } else if (field.type === 'file') {
        value = Array.from(field.files).map(function (file) {
          return [file.name, file.size, file.lastModified];
        });
      } else if (field.multiple && field.options) {
        value = Array.from(field.selectedOptions).map(function (option) { return option.value; });
      } else if (typeof value === 'string' && field.type !== 'password') {
        value = value.trim();
      }
      return [field.name, value];
    }));
  }

  function bind(form) {
    if (form.method.toLowerCase() !== 'post' || !fields(form).length) { return; }
    var buttons = Array.from(form.elements).filter(function (button) {
      return form.contains(button) && button.matches('button[type="submit"], button:not([type]), input[type="submit"]') && !button.disabled;
    });
    if (!buttons.length) { return; }
    var initial = snapshot(form);

    function ready() {
      return snapshot(form) !== initial && fields(form).every(function (field) {
        return !field.willValidate || field.validity.valid;
      });
    }

    function update() {
      var disabled = !ready();
      buttons.forEach(function (button) {
        button.disabled = disabled;
        button.classList.add('form-submit-state');
      });
    }

    form.addEventListener('input', update);
    form.addEventListener('change', update);
    form.addEventListener('reset', function () { setTimeout(update, 0); });
    form.addEventListener('submit', function (event) {
      if (!ready()) {
        event.preventDefault();
        event.stopImmediatePropagation();
        update();
      }
    }, true);
    new MutationObserver(function (mutations) {
      if (mutations.some(function (mutation) {
        return mutation.type === 'childList' || mutation.target.matches('input, select, textarea, fieldset');
      })) { update(); }
    }).observe(form, {subtree:true, childList:true, attributes:true, attributeFilter:['disabled', 'required', 'min', 'max', 'pattern']});
    window.addEventListener('pageshow', update);
    update();
  }

  document.querySelectorAll('form').forEach(bind);
}());
